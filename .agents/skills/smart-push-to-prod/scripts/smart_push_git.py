#!/usr/bin/env python3
"""Run the deterministic git parts of smart-push-to-prod."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlparse
from pathlib import Path


SECRET_PATTERNS = (
    ".env",
    "*.env",
    ".env.*",
    "id_rsa",
    "id_ed25519",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "credentials*",
    "secrets.*",
    "*.keystore",
    "*.jks",
)
CONTENT_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    ),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp|github_pat|sk|xoxb)-[A-Za-z0-9_-]{16,}\b"),
)


class WorkflowError(RuntimeError):
    """Raised when the workflow cannot safely continue."""


def command(
    args: list[str], *, check: bool = True, capture: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=capture)
    if check and result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise WorkflowError(f"command failed ({result.returncode}): {' '.join(args)}\n{detail}")
    return result


def output(args: list[str]) -> str:
    return command(args).stdout.strip()


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return command(["git", *args], check=check)


def git_output(*args: str) -> str:
    return output(["git", *args])


def repo_toplevel() -> Path:
    try:
        return Path(git_output("rev-parse", "--show-toplevel")).resolve()
    except WorkflowError as error:
        raise WorkflowError("not a git checkout") from error


def default_branch() -> str:
    for candidate in ("main", "master"):
        result = git(
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/remotes/origin/{candidate}",
            check=False,
        )
        if result.returncode == 0:
            return candidate
    raise WorkflowError("no origin/main or origin/master ref")


def current_branch() -> str:
    return git_output("branch", "--show-current")


def git_at(path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return command(["git", "-C", str(path), *args], check=check)


def git_at_output(path: Path, *args: str) -> str:
    return git_at(path, *args).stdout.strip()


def status_lines(path: Path | None = None) -> list[str]:
    runner = git if path is None else lambda *args: git_at(path, *args)
    result = runner(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "-z",
    )
    fields = [field for field in result.stdout.split("\0") if field]
    lines: list[str] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        status, path_name = field[:2], field[3:]
        lines.append(f"{status} {path_name}")
        if "R" in status or "C" in status:
            index += 1
            if index < len(fields):
                lines.append(f"{status} {fields[index]}")
        index += 1
    return lines


def tracked_status_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line[:2] != "??"]


def secret_paths(paths: list[str]) -> list[str]:
    matches: list[str] = []
    for status in paths:
        path = status[3:].strip()
        candidates = [path, Path(path).name]
        if any(
            fnmatch.fnmatch(candidate, pattern)
            for candidate in candidates
            for pattern in SECRET_PATTERNS
        ):
            matches.append(path)
    return matches


def content_has_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in CONTENT_SECRET_PATTERNS)


def changed_paths(default: str) -> set[str]:
    paths = {line[3:].strip() for line in status_lines()}
    for args in (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("diff", f"origin/{default}..HEAD", "--name-only"),
    ):
        result = git(*args, check=False)
        if result.returncode == 0:
            paths.update(line for line in result.stdout.splitlines() if line)
    return paths


def secret_content_paths(default: str) -> list[str]:
    matches: set[str] = set()
    top = repo_toplevel()
    for relative in changed_paths(default):
        path = top / relative
        if path.is_file():
            try:
                if content_has_secret(path.read_text(encoding="utf-8")):
                    matches.add(f"content:{relative}")
            except UnicodeDecodeError:
                pass

    for args in (
        ("diff", "--no-ext-diff", "--unified=0"),
        ("diff", "--cached", "--no-ext-diff", "--unified=0"),
        ("diff", f"origin/{default}..HEAD", "--no-ext-diff", "--unified=0"),
    ):
        result = git(*args, check=False)
        if result.returncode != 0:
            continue
        current_path = ""
        for line in result.stdout.splitlines():
            if line.startswith("+++ b/"):
                current_path = line[6:]
            elif line.startswith("+") and not line.startswith("+++"):
                if current_path and content_has_secret(line[1:]):
                    matches.add(f"content:{current_path}")
    return sorted(matches)


def primary_worktree() -> Path:
    for line in git_output("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            return Path(line.removeprefix("worktree ")).resolve()
    return repo_toplevel()


def worktree_for_branch(branch: str) -> Path | None:
    current_path: Path | None = None
    for line in git_output("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree ")).resolve()
        elif line == f"branch refs/heads/{branch}" and current_path is not None:
            return current_path
    return None


def repo_id(path: Path) -> Path:
    return Path(
        output(
            [
                "git",
                "-C",
                str(path),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ]
        )
    ).resolve()


def login_environment() -> str:
    inherited = os.environ.get("SMART_PUSH_PROD_PATH")
    if inherited is not None:
        return inherited

    bashrc = Path.home() / ".bashrc"
    if not bashrc.is_file():
        return ""
    assignment = re.compile(
        r"^\s*(?:export\s+)?SMART_PUSH_PROD_PATH\s*=\s*(.*?)\s*(?:#.*)?$"
    )
    for line in bashrc.read_text(encoding="utf-8").splitlines():
        match = assignment.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if not value:
            return ""
        if value[0] in "'\"":
            quote = value[0]
            quoted = re.fullmatch(
                rf"{re.escape(quote)}(.*?){re.escape(quote)}(?:\s*#.*)?",
                value,
            )
            if not quoted:
                continue
            value = quoted.group(1)
        elif any(char in value for char in "\\$`&|<>(){}!") or any(
            char.isspace() for char in value
        ):
            continue
        if "$" in value or "`" in value:
            continue
        return value
    return ""


def resolve_prod() -> Path | None:
    mapping = login_environment()
    if not mapping:
        return None

    top = repo_toplevel()
    primary = primary_worktree()
    common = Path(git_output("rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()

    def matches(path: Path) -> bool:
        return (
            path == top
            or path == primary
            or (path.exists() and repo_id(path) == common)
        )

    develop_matches: list[Path] = []
    for raw_pair in mapping.split(";"):
        if not raw_pair:
            continue
        if "=" not in raw_pair:
            raise WorkflowError(f"invalid SMART_PUSH_PROD_PATH pair: {raw_pair!r}")
        develop_raw, prod_raw = raw_pair.split("=", 1)
        develop_input = Path(develop_raw).expanduser()
        prod_input = Path(prod_raw).expanduser()
        if not develop_input.is_absolute() or not prod_input.is_absolute():
            raise WorkflowError(f"SMART_PUSH_PROD_PATH paths must be absolute: {raw_pair!r}")
        develop = develop_input.resolve()
        prod = prod_input.resolve()
        if develop == prod:
            continue

        develop_is_current = matches(develop)
        prod_is_current = matches(prod)
        if prod_is_current:
            raise WorkflowError(
                f"current checkout is mapped as prod; use the paired develop checkout {develop}"
            )
        if develop_is_current:
            develop_matches.append(prod)

    if len(develop_matches) > 1:
        paths = ", ".join(str(path) for path in develop_matches)
        raise WorkflowError(f"multiple prod checkouts map this repository: {paths}")
    if not develop_matches:
        return None

    prod = develop_matches[0]
    try:
        command(["git", "-C", str(prod), "rev-parse", "--show-toplevel"])
    except WorkflowError as error:
        raise WorkflowError(f"mapped prod checkout is not a git checkout: {prod}") from error
    return prod


def preflight(_: argparse.Namespace) -> int:
    top = repo_toplevel()
    remotes = git_output("remote").splitlines()
    if "origin" not in remotes:
        raise WorkflowError("remote origin is not configured")
    default = default_branch()
    dirty = status_lines()
    ahead = int(git_output("rev-list", "--count", f"origin/{default}..HEAD"))
    result = {
        "toplevel": str(top),
        "branch": current_branch(),
        "default": default,
        "ahead": ahead,
        "prod": str(resolve_prod() or ""),
        "dirty": dirty,
        "secret_paths": sorted(set(secret_paths(dirty) + secret_content_paths(default))),
    }
    print(json.dumps(result, separators=(",", ":")))
    return 0


def branch_sync(args: argparse.Namespace) -> int:
    git("fetch", "origin")
    default = default_branch()
    current = current_branch()
    if not current:
        raise WorkflowError("detached HEAD; choose a feature branch before syncing")

    if current == default:
        if not args.branch:
            raise WorkflowError("--branch is required when syncing from the default branch")
        command(["git", "check-ref-format", "--branch", args.branch])
        git("pull", "--ff-only", "origin", default)
        git("switch", "-c", args.branch)
        result = {"default": default, "action": "created", "branch": args.branch}
    else:
        git("merge", "--no-edit", f"origin/{default}")
        result = {"default": default, "action": "kept", "branch": current}
    print(json.dumps(result, separators=(",", ":")))
    return 0


def gh_json(args: list[str], error_message: str) -> dict[str, object]:
    result = command(args)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise WorkflowError(error_message) from error
    if not isinstance(data, dict):
        raise WorkflowError(error_message)
    return data


def repository_name(data: dict[str, object]) -> str | None:
    repository = data.get("repository")
    if isinstance(repository, str):
        return repository
    if isinstance(repository, dict):
        name = repository.get("nameWithOwner")
        return name if isinstance(name, str) else None
    name = data.get("nameWithOwner")
    return name if isinstance(name, str) else None


def repository_from_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    path = parsed.path.strip("/")
    parts = path.removesuffix(".git").split("/")
    if parsed.netloc == "github.com" and len(parts) >= 2:
        return "/".join(parts[:2]).lower()
    return None


def current_repository() -> str:
    data = gh_json(
        ["gh", "repo", "view", "--json", "nameWithOwner"],
        "gh returned invalid repository JSON",
    )
    name = repository_name(data)
    if not name:
        raise WorkflowError("gh did not return the current repository name")
    return name


def confirm_merge(pr_url: str, default: str) -> dict[str, str]:
    current_repo = current_repository()
    data = gh_json(
        [
            "gh",
            "pr",
            "view",
            pr_url,
            "--json",
            "state,mergedAt,mergeCommit,url,baseRefName",
        ],
        "gh returned invalid PR JSON",
    )
    pr_repo = repository_from_url(data.get("url"))
    if pr_repo != current_repo.lower() or data.get("baseRefName") != default:
        raise WorkflowError(
            "PR does not target this repository and default branch; no checkout will be refreshed"
        )
    merge_commit = data.get("mergeCommit") or {}
    sha = merge_commit.get("oid") if isinstance(merge_commit, dict) else None
    if data.get("state") != "MERGED" or not data.get("mergedAt") or not sha:
        raise WorkflowError(
            "PR is not confirmed squash-merged; no checkout will be refreshed"
        )
    return {"mergedAt": str(data["mergedAt"]), "mergeCommit": str(sha)}


def run_pull(args: list[str]) -> tuple[str, str]:
    result = command(args, check=False)
    detail = (result.stderr or result.stdout or "").strip()
    return ("ok" if result.returncode == 0 else "error", detail)


def refresh(args: argparse.Namespace) -> int:
    default = default_branch()
    merge = confirm_merge(args.pr_url, default)
    prod = resolve_prod()

    if prod is not None:
        prod_branch = git_at_output(prod, "branch", "--show-current")
        if prod_branch != default:
            raise WorkflowError(
                f"prod checkout is on {prod_branch or 'detached HEAD'}; expected {default}"
            )
        if tracked_status_lines(status_lines(prod)):
            raise WorkflowError(f"prod checkout is dirty: {prod}")

    local_worktree = worktree_for_branch(default) or primary_worktree()
    if status_lines(local_worktree):
        raise WorkflowError(
            f"default refresh checkout is dirty: {local_worktree}"
        )
    git_at(local_worktree, "checkout", default)
    local_status, local_detail = run_pull(
        ["git", "-C", str(local_worktree), "pull", "--ff-only", "origin", default]
    )
    local_tree = status_lines(local_worktree)
    result: dict[str, object] = {
        "merge": merge,
        "default": default,
        "local_pull": local_status,
        "local_status": local_tree,
        "prod": str(prod or ""),
    }
    if local_detail and local_status == "error":
        result["local_error"] = local_detail

    if prod is not None:
        prod_status, prod_detail = run_pull(
            ["git", "-C", str(prod), "pull", "--ff-only", "origin", default]
        )
        result["prod_pull"] = prod_status
        prod_status_lines = command(
            ["git", "-C", str(prod), "status", "-sb"]
        ).stdout.splitlines()
        result["prod_status"] = prod_status_lines
        if prod_detail and prod_status == "error":
            result["prod_error"] = prod_detail
    else:
        result["prod_pull"] = "skipped"

    print(json.dumps(result, separators=(",", ":")))
    return 1 if result.get("prod_pull") == "error" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic git steps for smart-push-to-prod."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("preflight", help="validate the checkout and print its state")

    sync = subparsers.add_parser("branch-sync", help="fetch and sync the feature branch")
    sync.add_argument("--branch", help="new feature branch when currently on default")

    refresh_parser = subparsers.add_parser(
        "refresh", help="confirm the merge and refresh local and mapped prod checkouts"
    )
    refresh_parser.add_argument("--pr-url", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            return preflight(args)
        if args.command == "branch-sync":
            return branch_sync(args)
        return refresh(args)
    except WorkflowError as error:
        print(f"STOP: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
