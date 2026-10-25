#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_GUARD = 2
EXIT_NO_BASE = 3
EXIT_REPO = 4

SECRET_NAMES = (
    ".env",
    ".envrc",
    "credentials",
    "secrets",
    "kubeconfig",
    "id_rsa",
    "id_ed25519",
    "terraform.tfstate",
)
SECRET_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".tfstate",
    ".secrets.yaml",
    ".secrets.yml",
)
REGENERABLE_PREFIXES = (
    ".venv/",
    "venv/",
    "node_modules/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".cache/",
    "logs/",
    "dist/",
    "build/",
    "target/",
)


class PrepError(Exception):
    def __init__(self, message: str, code: int = EXIT_ERROR):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Repo:
    checkout: Path
    common_dir: Path
    repo_key: str
    remote_url: str | None
    main_worktree: Path
    state_dir: Path


@dataclass(frozen=True)
class BaseRef:
    ref: str
    sha: str
    default_branch: str
    stale: bool = False


@dataclass(frozen=True)
class Worktree:
    path: Path
    head: str
    branch: str | None
    locked: bool
    prunable: bool
    admin_id: str | None


@dataclass
class PrepConfig:
    protected_paths: tuple[Path, ...] = ()
    base_ref: str | None = None
    max_managed_worktrees: int = 8
    disk_budget_gib: float = 20.0
    idle_ttl_hours: float = 24.0
    worktree_root: Path | None = None
    archive_ignored: bool = False


@dataclass
class Record:
    admin_id: str
    path: str
    branch: str | None
    base_sha: str
    owner_session: str
    owner_pid: int
    pid_start: str | None
    created_at: float
    last_seen: float
    state: str
    archive_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Record":
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in data.items() if key in allowed})


class App:
    def __init__(self, json_mode: bool = False):
        self.json_mode = json_mode
        self.warnings: list[dict[str, Any]] = []

    def warn(self, code: str, **fields: Any) -> None:
        item = {"code": code, **fields}
        self.warnings.append(item)
        detail = " ".join(f"{key}={value}" for key, value in fields.items())
        print(f"{code} {detail}".rstrip(), file=sys.stderr)

    def payload(self, data: dict[str, Any]) -> dict[str, Any]:
        return {**data, "warnings": self.warnings}

    def emit(self, data: dict[str, Any]) -> None:
        print(json.dumps(self.payload(data), indent=2, sort_keys=True))


def run_git(
    path: Path,
    *args: str,
    check: bool = True,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(path), *args]
    process = subprocess.run(
        command,
        text=True,
        capture_output=True,
        env=env,
        input=input_text,
    )
    if check and process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip()
        raise PrepError(f"git {' '.join(args)} failed: {message}")
    return process


def git_output(
    path: Path,
    *args: str,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> str:
    return run_git(path, *args, env=env, input_text=input_text).stdout.strip()


def git_optional(path: Path, *args: str) -> str | None:
    process = run_git(path, *args, check=False)
    if process.returncode != 0:
        return None
    value = process.stdout.strip()
    return value or None


def resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_repo(value: str | Path | None = None) -> Repo:
    start = resolve_path(value or Path.cwd())
    if not start.exists():
        raise PrepError(f"checkout does not exist: {start}", EXIT_REPO)
    if start.is_file():
        start = start.parent
    root_text = git_optional(start, "rev-parse", "--show-toplevel")
    if not root_text:
        raise PrepError(f"not a git checkout: {start}", EXIT_REPO)
    checkout = resolve_path(root_text)
    if "prod" in checkout.parts:
        raise PrepError(f"production checkout is read-only: {checkout}", EXIT_REPO)
    common_text = git_optional(
        checkout, "rev-parse", "--path-format=absolute", "--git-common-dir"
    )
    if not common_text:
        raise PrepError(f"could not resolve git common dir: {checkout}", EXIT_REPO)
    common_dir = resolve_path(common_text)
    try:
        stat = common_dir.stat()
        repo_key = f"{stat.st_dev}:{stat.st_ino}"
    except OSError:
        repo_key = hashlib.sha256(str(common_dir).encode()).hexdigest()
    remote_url = git_optional(checkout, "remote", "get-url", "origin")
    worktree_text = git_output(checkout, "worktree", "list", "--porcelain")
    main_worktree = checkout
    for line in worktree_text.splitlines():
        if line.startswith("worktree "):
            main_worktree = resolve_path(line.removeprefix("worktree "))
            break
    return Repo(
        checkout=checkout,
        common_dir=common_dir,
        repo_key=repo_key,
        remote_url=remote_url,
        main_worktree=main_worktree,
        state_dir=common_dir / "prep-worktree",
    )


def admin_id_map(repo: Repo) -> dict[Path, str]:
    mapping: dict[Path, str] = {}
    admin_root = repo.common_dir / "worktrees"
    if not admin_root.is_dir():
        return mapping
    for gitdir_file in admin_root.glob("*/gitdir"):
        try:
            content = gitdir_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        gitdir = resolve_path(content.removeprefix("gitdir:").strip())
        mapping[gitdir.parent] = gitdir_file.parent.name
    return mapping


def admin_id_for_path(repo: Repo, path: Path) -> str | None:
    path = resolve_path(path)
    if path.exists():
        git_dir = git_optional(path, "rev-parse", "--path-format=absolute", "--git-dir")
        if git_dir:
            resolved = resolve_path(git_dir)
            if resolved == repo.common_dir:
                return "main"
            return resolved.name
    return admin_id_map(repo).get(path)


def parse_worktrees(repo: Repo) -> list[Worktree]:
    text = git_output(repo.checkout, "worktree", "list", "--porcelain")
    mapping = admin_id_map(repo)
    worktrees: list[Worktree] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        path: Path | None = None
        head = ""
        branch: str | None = None
        locked = False
        prunable = False
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = resolve_path(line.removeprefix("worktree "))
            elif line.startswith("HEAD "):
                head = line.removeprefix("HEAD ").strip()
            elif line.startswith("branch "):
                ref = line.removeprefix("branch ").strip()
                branch = ref.removeprefix("refs/heads/")
            elif line == "detached":
                branch = None
            elif line.startswith("locked"):
                locked = True
            elif line.startswith("prunable"):
                prunable = True
        if path is None:
            continue
        worktrees.append(
            Worktree(
                path=path,
                head=head,
                branch=branch,
                locked=locked,
                prunable=prunable,
                admin_id=admin_id_for_path(repo, path) or mapping.get(path),
            )
        )
    return worktrees


def shared_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "smarter-way" / "config.json"


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise PrepError(f"could not read {path}: {exc}") from exc


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def config_for_repo(repo: Repo, app: App) -> PrepConfig:
    data: dict[str, Any] = {}
    try:
        loaded = read_json(shared_config_path())
        if loaded:
            data = loaded
    except PrepError as exc:
        app.warn("CONFIG_INVALID", path=str(shared_config_path()), detail=str(exc))
    prep = data.get("prep_worktree", {}) if isinstance(data, dict) else {}
    defaults = prep.get("defaults", {}) if isinstance(prep, dict) else {}
    repos = prep.get("repos", {}) if isinstance(prep, dict) else {}
    entry = {}
    if isinstance(repos, dict):
        entry = (
            repos.get(str(repo.common_dir))
            or repos.get(str(repo.checkout))
            or repos.get(repo.remote_url or "")
            or {}
        )
    merged: dict[str, Any] = {}
    if isinstance(defaults, dict):
        merged.update(defaults)
    if isinstance(entry, dict):
        merged.update(entry)

    protected = list(merged.get("protected_paths", []) or [])
    legacy = os.environ.get("PREP_WORKTREE_PROTECTED_DEV_PATH")
    if legacy:
        legacy_path = resolve_path(legacy)
        try:
            other = resolve_repo(legacy_path)
        except PrepError:
            other = None
        if other and other.common_dir == repo.common_dir:
            protected.append(str(legacy_path))
        else:
            app.warn("LEGACY_PROTECTED_IGNORED", path=str(legacy_path))

    max_managed = merged.get("max_managed_worktrees", 8)
    env_max = os.environ.get("PREP_WORKTREE_MAX")
    if env_max:
        try:
            max_managed = int(env_max)
        except ValueError:
            app.warn("MAX_INVALID", value=env_max)
    try:
        max_managed = max(1, int(max_managed))
    except (TypeError, ValueError):
        app.warn("MAX_INVALID", value=str(max_managed))
        max_managed = 8

    try:
        disk_budget = float(merged.get("disk_budget_gib", 20.0))
    except (TypeError, ValueError):
        disk_budget = 20.0
    try:
        idle_ttl = float(merged.get("idle_ttl_hours", 24.0))
    except (TypeError, ValueError):
        idle_ttl = 24.0

    root_value = os.environ.get("PREP_WORKTREE_ROOT") or merged.get("worktree_root")
    worktree_root = resolve_path(root_value) if root_value else None
    base_ref = merged.get("base_ref")
    archive_ignored = bool(merged.get("archive_ignored", False))

    resolved_protected = []
    for item in protected:
        candidate = Path(item).expanduser()
        if not candidate.is_absolute():
            candidate = repo.checkout / candidate
        resolved_protected.append(resolve_path(candidate))

    return PrepConfig(
        protected_paths=tuple(resolved_protected),
        base_ref=str(base_ref) if base_ref else None,
        max_managed_worktrees=max_managed,
        disk_budget_gib=disk_budget,
        idle_ttl_hours=idle_ttl,
        worktree_root=worktree_root,
        archive_ignored=archive_ignored,
    )


def resolve_base(
    repo: Repo, config: PrepConfig, app: App, fetch: bool = True
) -> BaseRef:
    candidates: list[str] = []
    if config.base_ref:
        candidates.append(config.base_ref)
    if repo.remote_url:
        candidates.extend(["origin/main", "origin/master"])
    candidates.extend(["main", "master"])

    for candidate in candidates:
        stale = False
        branch = candidate.removeprefix("origin/")
        if fetch and candidate.startswith("origin/") and repo.remote_url:
            process = run_git(
                repo.checkout,
                "fetch",
                "--no-tags",
                "origin",
                branch,
                check=False,
            )
            if process.returncode != 0:
                if not git_optional(
                    repo.checkout, "rev-parse", "--verify", "--quiet", candidate
                ):
                    continue
                stale = True
                app.warn("BASE_STALE", ref=candidate)
        sha = git_optional(repo.checkout, "rev-parse", "--verify", "--quiet", candidate)
        if sha:
            return BaseRef(
                ref=candidate,
                sha=sha,
                default_branch=branch,
                stale=stale,
            )
    raise PrepError("no origin/main, origin/master, main, or master ref", EXIT_NO_BASE)


def protected_warnings(
    repo: Repo, config: PrepConfig, default_branch: str, app: App
) -> None:
    for item in config.protected_paths:
        path = resolve_path(item)
        if not path.exists():
            app.warn("PROTECTED_MISSING", path=str(path))
            continue
        if not path.is_dir():
            app.warn("PROTECTED_NOT_DIR", path=str(path))
            continue
        try:
            other = resolve_repo(path)
        except PrepError:
            app.warn("PROTECTED_NOT_GIT", path=str(path))
            continue
        if other.common_dir != repo.common_dir:
            app.warn("PROTECTED_OTHER_REPO", path=str(path))
            continue
        branch = git_optional(path, "branch", "--show-current") or "detached"
        if branch != default_branch:
            app.warn("PROTECTED_BRANCH", path=str(path), branch=branch)
        status = git_output(path, "status", "--porcelain=v1", "--untracked-files=all")
        if status:
            app.warn("PROTECTED_DIRTY", path=str(path), files=len(status.splitlines()))
        for marker in (
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "BISECT_LOG",
            "rebase-apply",
            "rebase-merge",
            "sequencer",
        ):
            marker_path = git_optional(
                path, "rev-parse", "--path-format=absolute", "--git-path", marker
            )
            if marker_path and Path(marker_path).exists():
                app.warn("PROTECTED_OPERATION", path=str(path), marker=marker)


def state_worktrees_dir(repo: Repo) -> Path:
    return repo.state_dir / "worktrees"


def safe_admin_id(admin_id: str) -> str:
    if (
        not admin_id
        or admin_id in {".", ".."}
        or "/" in admin_id
        or "\\" in admin_id
        or ".." in admin_id
        or not re.fullmatch(r"[A-Za-z0-9._-]+", admin_id)
    ):
        raise PrepError(f"invalid worktree id: {admin_id!r}", EXIT_GUARD)
    return admin_id


def record_dir(repo: Repo, admin_id: str) -> Path:
    return state_worktrees_dir(repo) / safe_admin_id(admin_id)


def read_record(repo: Repo, admin_id: str) -> Record | None:
    directory = record_dir(repo, admin_id)
    meta_path = directory / "meta.json"
    lease_path = directory / "lease.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    lease: dict[str, Any] = {}
    try:
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        pass
    merged = {**meta, **lease}
    if "admin_id" not in merged:
        merged["admin_id"] = admin_id
    try:
        return Record.from_dict(merged)
    except TypeError:
        return None


def managed_records(repo: Repo) -> list[Record]:
    root = state_worktrees_dir(repo)
    if not root.is_dir():
        return []
    records: list[Record] = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        record = read_record(repo, directory.name)
        if record:
            records.append(record)
    return sorted(records, key=lambda item: item.created_at)


def write_record(repo: Repo, record: Record) -> None:
    directory = record_dir(repo, record.admin_id)
    meta = {
        "admin_id": record.admin_id,
        "path": record.path,
        "branch": record.branch,
        "base_sha": record.base_sha,
        "created_at": record.created_at,
        "archive_ref": record.archive_ref,
    }
    lease = {
        "owner_session": record.owner_session,
        "owner_pid": record.owner_pid,
        "pid_start": record.pid_start,
        "created_at": record.created_at,
        "last_seen": record.last_seen,
        "state": record.state,
    }
    write_json_atomic(directory / "meta.json", meta)
    write_json_atomic(directory / "lease.json", lease)


def pid_start_time(pid: int) -> str | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        text = ""
    if text:
        try:
            fields = text.rsplit(")", 1)[1].split()
            return fields[19]
        except IndexError:
            return None
    process = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        text=True,
        capture_output=True,
    )
    if process.returncode != 0:
        return None
    return process.stdout.strip() or None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def active_cwd(path: Path) -> int | None:
    if not Path("/proc").is_dir():
        return None
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cwd = Path(os.readlink(entry / "cwd")).resolve(strict=False)
        except OSError:
            continue
        if is_within(cwd, path):
            return int(entry.name)
    return None


def record_active(record: Record) -> bool:
    if record.owner_pid and pid_alive(record.owner_pid):
        current_start = pid_start_time(record.owner_pid)
        if record.pid_start is None or current_start == record.pid_start:
            return True
    return active_cwd(resolve_path(record.path)) is not None


def session_id() -> str:
    return (
        os.environ.get("OPENCODE_SESSION_ID")
        or os.environ.get("PREP_AGENT_ID")
        or os.environ.get("PREP_WORKTREE_OWNER")
        or secrets.token_hex(16)
    )


def root_is_safe(repo: Repo, path: Path, config: PrepConfig) -> bool:
    if "prod" in path.parts:
        return False
    if is_within(path, repo.checkout) or is_within(path, repo.common_dir):
        return False
    return not any(is_within(path, resolve_path(item)) for item in config.protected_paths)


def default_worktree_root(repo: Repo, config: PrepConfig, app: App) -> Path:
    if config.worktree_root and root_is_safe(repo, config.worktree_root, config):
        config.worktree_root.mkdir(parents=True, exist_ok=True)
        return config.worktree_root
    parent = repo.main_worktree.parent
    candidate = parent / f".{repo.main_worktree.name}-prep-worktrees"
    if root_is_safe(repo, candidate, config):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            pass
    fallback = Path(tempfile.gettempdir()) / "smarter-way" / f"{repo.main_worktree.name}-prep-worktrees"
    if not root_is_safe(repo, fallback, config):
        raise PrepError(f"no safe worktree root for {repo.checkout}", EXIT_REPO)
    fallback.mkdir(parents=True, exist_ok=True)
    app.warn("WORKTREE_ROOT_FALLBACK", path=str(fallback))
    return fallback


def isolation_error(
    repo: Repo, path: Path, config: PrepConfig, worktrees: Sequence[Worktree]
) -> str | None:
    if "prod" in path.parts:
        return f"landing path is under a production directory: {path}"
    for protected in config.protected_paths:
        protected_path = resolve_path(protected)
        if is_within(path, protected_path):
            return f"landing path is inside protected checkout: {protected_path}"
    if is_within(path, repo.checkout):
        return f"landing path is inside the current checkout: {repo.checkout}"
    if is_within(path, repo.common_dir):
        return f"landing path is inside the common git directory: {repo.common_dir}"
    for worktree in worktrees:
        if is_within(path, worktree.path):
            return f"landing path is inside another worktree: {worktree.path}"
    return None


def unique_branch(repo: Repo, default_branch: str) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for _ in range(20):
        candidate = f"prep-worktree/{default_branch}-{stamp}-{secrets.token_hex(3)}"
        exists = run_git(
            repo.checkout,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{candidate}",
            check=False,
        ).returncode == 0
        if not exists:
            return candidate
    raise PrepError("could not allocate a unique prep branch")


def maybe_reap(repo: Repo, config: PrepConfig, app: App) -> None:
    records = managed_records(repo)
    over_count = len(records) >= config.max_managed_worktrees
    over_disk = managed_bytes(repo) >= config.disk_budget_gib * 1024**3
    if not over_count and not over_disk:
        return
    reap_args = argparse.Namespace(
        repo=str(repo.checkout),
        apply=True,
        include_ignored=False,
        lock_timeout=2.0,
    )
    command_reap(reap_args, app, quiet=True)


def reuse_idle(
    repo: Repo, config: PrepConfig, base: BaseRef, app: App
) -> Record | None:
    for candidate in managed_records(repo):
        if candidate.state != "idle" or record_active(candidate):
            continue
        with record_lock(repo, candidate.admin_id, timeout=0.0) as acquired:
            if not acquired:
                continue
            record = read_record(repo, candidate.admin_id)
            if not record or record.state != "idle" or record_active(record):
                continue
            path = resolve_path(record.path)
            if not path.exists():
                continue
            if isolation_error(repo, path, config, []):
                continue
            status = git_output(
                path, "status", "--porcelain=v1", "--untracked-files=all"
            )
            if status:
                record.state = "needs-cleanup"
                write_record(repo, record)
                continue
            old_branch = record.branch
            branch = unique_branch(repo, base.default_branch)
            reset = run_git(path, "reset", "--hard", base.sha, check=False)
            if reset.returncode != 0:
                record.state = "needs-cleanup"
                write_record(repo, record)
                continue
            switch = run_git(path, "switch", "-C", branch, base.sha, check=False)
            if switch.returncode != 0:
                record.state = "needs-cleanup"
                write_record(repo, record)
                continue
            if old_branch and old_branch != branch:
                deleted = run_git(
                    repo.checkout, "branch", "-d", old_branch, check=False
                )
                if deleted.returncode != 0:
                    app.warn("BRANCH_RETAINED", branch=old_branch)
            record.branch = branch
            record.base_sha = base.sha
            record.owner_session = session_id()
            record.owner_pid = os.getpid()
            record.pid_start = pid_start_time(os.getpid())
            record.created_at = time.time()
            record.last_seen = record.created_at
            record.state = "leased"
            write_record(repo, record)
            return record
    return None


def command_acquire(args: argparse.Namespace, app: App) -> int:
    repo = resolve_repo(args.repo)
    config = config_for_repo(repo, app)
    base = resolve_base(repo, config, app)
    protected_warnings(repo, config, base.default_branch, app)
    maybe_reap(repo, config, app)
    record = None if args.no_reuse else reuse_idle(repo, config, base, app)
    if record is not None:
        path = resolve_path(record.path)
        branch = record.branch or ""
        admin_id = record.admin_id
    else:
        root = default_worktree_root(repo, config, app)
        worktrees = parse_worktrees(repo)
        path = Path(tempfile.mkdtemp(prefix=f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-", dir=root))
        error = isolation_error(repo, path, config, worktrees)
        if error:
            path.rmdir()
            raise PrepError(error)
        branch = unique_branch(repo, base.default_branch)
        process = run_git(
            repo.checkout,
            "worktree",
            "add",
            "-b",
            branch,
            str(path),
            base.sha,
            check=False,
        )
        if process.returncode != 0:
            with contextlib.suppress(OSError):
                path.rmdir()
            raise PrepError(process.stderr.strip() or "git worktree add failed")
        admin_id = admin_id_for_path(repo, path)
        if not admin_id:
            raise PrepError(f"could not resolve worktree id for {path}")
        now = time.time()
        owner = session_id()
        record = Record(
            admin_id=admin_id,
            path=str(path),
            branch=branch,
            base_sha=base.sha,
            owner_session=owner,
            owner_pid=os.getpid(),
            pid_start=pid_start_time(os.getpid()),
            created_at=now,
            last_seen=now,
            state="leased",
        )
        write_record(repo, record)
    owner = record.owner_session
    invalidate_size_cache(repo)
    count = len(managed_records(repo))
    if count > config.max_managed_worktrees:
        app.warn("OVER_BUDGET", managed=count, max=config.max_managed_worktrees)
    data = {
        "id": admin_id,
        "path": str(path),
        "branch": branch,
        "base_sha": base.sha,
        "owner": owner,
        "state": "leased",
        "base_ref": base.ref,
        "managed": count,
    }
    if app.json_mode:
        app.emit(data)
    else:
        print(f"export PREP_WORKTREE_ID={shlex.quote(admin_id)}")
        print(f"export PREP_WORKTREE_PATH={shlex.quote(str(path))}")
        print(f"export PREP_WORKTREE_BRANCH={shlex.quote(branch)}")
        print(f"export PREP_WORKTREE_BASE_SHA={shlex.quote(base.sha)}")
        print(f"export PREP_WORKTREE_OWNER={shlex.quote(owner)}")
        print(f"cd {shlex.quote(str(path))}")
    return EXIT_OK


def require_record(repo: Repo, admin_id: str | None) -> Record:
    if not admin_id:
        raise PrepError("no worktree id; set PREP_WORKTREE_ID or pass --id", EXIT_GUARD)
    record = read_record(repo, admin_id)
    if not record:
        raise PrepError(f"no lease for worktree id: {admin_id}", EXIT_GUARD)
    return record


def assert_owner(record: Record) -> None:
    owner = os.environ.get("PREP_WORKTREE_OWNER") or session_id()
    if record.owner_session != owner:
        raise PrepError(
            f"owner mismatch: lease={record.owner_session} caller={owner}",
            EXIT_GUARD,
        )


def command_guard(args: argparse.Namespace, app: App) -> int:
    try:
        repo = resolve_repo(Path.cwd())
    except PrepError as exc:
        raise PrepError(f"NO_LEASE {exc}", EXIT_GUARD) from exc
    record = require_record(repo, args.id or os.environ.get("PREP_WORKTREE_ID"))
    current = repo.checkout
    if resolve_path(record.path) != current:
        raise PrepError(
            f"FOREIGN_WORKTREE lease={record.path} current={current} owner={record.owner_session}",
            EXIT_GUARD,
        )
    assert_owner(record)
    record.last_seen = time.time()
    record.state = "leased"
    write_record(repo, record)
    if app.json_mode:
        app.emit({"id": record.admin_id, "state": record.state, "path": record.path})
    else:
        print(f"GUARD_OK id={record.admin_id} path={record.path}")
    return EXIT_OK


def command_heartbeat(args: argparse.Namespace, app: App) -> int:
    repo = resolve_repo(Path.cwd())
    record = require_record(repo, args.id or os.environ.get("PREP_WORKTREE_ID"))
    assert_owner(record)
    record.last_seen = time.time()
    write_record(repo, record)
    if app.json_mode:
        app.emit({"id": record.admin_id, "last_seen": record.last_seen})
    else:
        print(f"HEARTBEAT_OK id={record.admin_id} last_seen={record.last_seen}")
    return EXIT_OK


def command_release(args: argparse.Namespace, app: App) -> int:
    repo = resolve_repo(Path.cwd())
    record = require_record(repo, args.id or os.environ.get("PREP_WORKTREE_ID"))
    assert_owner(record)
    status = git_output(record.path, "status", "--porcelain=v1", "--untracked-files=all")
    ahead = git_output(record.path, "rev-list", "--count", f"{record.base_sha}..HEAD")
    record.last_seen = time.time()
    record.state = "idle" if not status and ahead == "0" else "needs-cleanup"
    write_record(repo, record)
    if app.json_mode:
        app.emit({"id": record.admin_id, "state": record.state, "ahead": int(ahead)})
    else:
        print(f"RELEASE_OK id={record.admin_id} state={record.state} ahead={ahead}")
    return EXIT_OK


def is_secret_name(name: str) -> bool:
    return (
        name in SECRET_NAMES
        or name.startswith(".env.")
        or name.endswith(SECRET_SUFFIXES)
        or "credential" in name.lower()
        or "secret" in name.lower()
    )


def ignored_scan(path: Path) -> dict[str, Any]:
    raw = git_output(
        path, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"
    )
    files = [item for item in raw.split("\0") if item]
    untracked_raw = git_output(
        path, "ls-files", "--others", "--exclude-standard", "-z"
    )
    untracked = [item for item in untracked_raw.split("\0") if item]
    total = 0
    secret: list[str] = []
    unknown: list[str] = []
    for relative in files:
        candidate = path / relative
        if candidate.is_file() and not candidate.is_symlink():
            with contextlib.suppress(OSError):
                total += candidate.stat().st_size
        if is_secret_name(candidate.name):
            secret.append(relative)
            continue
        normalized = relative.replace(os.sep, "/")
        if not any(
            normalized.startswith(prefix) or f"/{prefix}" in f"/{normalized}"
            for prefix in REGENERABLE_PREFIXES
        ):
            unknown.append(relative)
    secret.extend(
        relative for relative in untracked if is_secret_name(Path(relative).name)
    )
    return {
        "files": files,
        "bytes": total,
        "secret": secret,
        "unknown": unknown,
    }


def du_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    process = subprocess.run(["du", "-sk", str(path)], text=True, capture_output=True)
    if process.returncode != 0:
        return 0
    try:
        return int(process.stdout.split()[0]) * 1024
    except (IndexError, ValueError):
        return 0


def size_cache_path(repo: Repo) -> Path:
    return repo.state_dir / "size.json"


def managed_bytes(repo: Repo, max_age: float = 600.0) -> int:
    cache_path = size_cache_path(repo)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if time.time() - float(cache["measured_at"]) < max_age:
            return int(cache["bytes"])
    except (FileNotFoundError, OSError, ValueError, KeyError, json.JSONDecodeError):
        pass
    total = 0
    for record in managed_records(repo):
        if record.state != "archived":
            total += du_bytes(resolve_path(record.path))
    with contextlib.suppress(OSError):
        write_json_atomic(cache_path, {"bytes": total, "measured_at": time.time()})
    return total


def invalidate_size_cache(repo: Repo) -> None:
    with contextlib.suppress(OSError):
        size_cache_path(repo).unlink()


@contextlib.contextmanager
def record_lock(repo: Repo, admin_id: str, timeout: float = 0.0) -> Iterator[bool]:
    lock_path = record_dir(repo, admin_id) / "claim.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.02)
        yield acquired
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextlib.contextmanager
def reap_lock(repo: Repo, timeout: float = 5.0) -> Iterator[bool]:
    lock_path = repo.state_dir / "reap.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
        yield acquired
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def create_archive(record: Record, include_ignored: bool) -> str:
    path = resolve_path(record.path)
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    ref = f"refs/prep-archive/{record.admin_id}/{timestamp}"
    descriptor, index_path = tempfile.mkstemp(prefix="prep-index-")
    os.close(descriptor)
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = index_path
    try:
        run_git(path, "read-tree", "HEAD", env=env)
        add_args = ["add", "-A"]
        if include_ignored:
            add_args.append("-f")
        run_git(path, *add_args, env=env)
        tree = git_output(path, "write-tree", env=env)
        commit = git_output(
            path,
            "commit-tree",
            tree,
            "-p",
            "HEAD",
            "-m",
            f"prep archive {record.admin_id}",
            env=env,
        )
        run_git(path, "update-ref", ref, commit)
        archive_entries = git_output(
            path, "ls-tree", "-r", "-z", "--full-tree", commit
        ).split("\0")
        archive_hashes: dict[str, str] = {}
        for entry in archive_entries:
            if not entry:
                continue
            metadata, relative = entry.split("\t", 1)
            mode, kind, blob = metadata.split()
            if kind == "blob":
                archive_hashes[relative] = blob
        stage_raw = git_output(path, "ls-files", "-z", "--stage")
        stage_modes: dict[str, str] = {}
        for entry in stage_raw.split("\0"):
            if not entry:
                continue
            metadata, relative = entry.split("\t", 1)
            stage_modes[relative] = metadata.split()[0]
        worktree_raw = git_output(
            path,
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        )
        worktree_paths = [item for item in worktree_raw.split("\0") if item]
        if include_ignored:
            ignored_raw = git_output(
                path, "ls-files", "-z", "--others", "--ignored", "--exclude-standard"
            )
            worktree_paths.extend(item for item in ignored_raw.split("\0") if item)
        worktree_hashes: dict[str, str] = {}
        for relative in sorted(set(worktree_paths)):
            if stage_modes.get(relative) == "160000":
                continue
            candidate = path / relative
            if not candidate.exists() and not candidate.is_symlink():
                continue
            if candidate.is_symlink():
                content = os.readlink(candidate)
                blob = git_output(path, "hash-object", "--stdin", input_text=content)
            else:
                blob = git_output(path, "hash-object", "--", str(candidate))
            worktree_hashes[relative] = blob
        if set(archive_hashes) != set(worktree_hashes):
            missing = sorted(set(worktree_hashes) - set(archive_hashes))
            extra = sorted(set(archive_hashes) - set(worktree_hashes))
            raise PrepError(
                f"archive verification failed: missing={missing} extra={extra}"
            )
        for relative, expected in worktree_hashes.items():
            if archive_hashes.get(relative) != expected:
                raise PrepError(f"archive hash mismatch: {relative}")
        return ref
    except Exception:
        with contextlib.suppress(Exception):
            run_git(path, "update-ref", "-d", ref)
        raise
    finally:
        with contextlib.suppress(OSError):
            os.unlink(index_path)


def remove_worktree(repo: Repo, record: Record, app: App) -> bool:
    path = resolve_path(record.path)
    process = run_git(repo.checkout, "worktree", "remove", str(path), check=False)
    if process.returncode != 0:
        app.warn("REMOVE_REFUSED", path=str(path), detail=process.stderr.strip())
        record.state = "needs-cleanup"
        write_record(repo, record)
        return False
    if record.branch:
        merged = run_git(
            repo.checkout,
            "merge-base",
            "--is-ancestor",
            record.branch,
            record.base_sha,
            check=False,
        ).returncode == 0
        ahead = git_output(
            repo.checkout,
            "rev-list",
            "--count",
            f"{record.base_sha}..{record.branch}",
        )
        if merged or ahead == "0":
            run_git(repo.checkout, "branch", "-d", record.branch, check=False)
        else:
            app.warn("BRANCH_RETAINED", branch=record.branch)
    record.state = "archived"
    write_record(repo, record)
    return True


def command_reap(args: argparse.Namespace, app: App, quiet: bool = False) -> int:
    repo = resolve_repo(args.repo)
    config = config_for_repo(repo, app)
    apply_changes = bool(args.apply)
    actions: list[dict[str, Any]] = []
    with reap_lock(repo, timeout=float(args.lock_timeout)) as acquired:
        if not acquired:
            app.warn("REAP_SKIPPED", reason="lock_busy")
            if app.json_mode and not quiet:
                app.emit({"actions": [], "applied": False})
            return EXIT_OK
        worktrees = {worktree.path: worktree for worktree in parse_worktrees(repo)}
        now = time.time()
        ttl_seconds = config.idle_ttl_hours * 3600
        for record in managed_records(repo):
            if record.state == "archived":
                continue
            path = resolve_path(record.path)
            action: dict[str, Any] = {
                "id": record.admin_id,
                "path": str(path),
                "state": record.state,
                "branch": record.branch,
            }
            if path == repo.checkout or any(
                is_within(path, resolve_path(item)) for item in config.protected_paths
            ):
                action["action"] = "SKIP_PROTECTED"
                actions.append(action)
                continue
            if not path.exists():
                action["action"] = "MISSING"
                if apply_changes:
                    worktree = worktrees.get(path)
                    if worktree and remove_prunable_registration(repo, worktree):
                        record.state = "archived"
                        write_record(repo, record)
                    elif worktree and worktree.prunable:
                        action["action"] = "REMOVE_REFUSED"
                    else:
                        record.state = "archived"
                        write_record(repo, record)
                actions.append(action)
                continue
            worktree = worktrees.get(path)
            if worktree and worktree.locked:
                action["action"] = "SKIP_LOCKED"
                actions.append(action)
                continue
            if record_active(record):
                action["action"] = "SKIP_ACTIVE"
                actions.append(action)
                continue
            if now - record.last_seen < ttl_seconds:
                action["action"] = "SKIP_RECENT"
                actions.append(action)
                continue
            status = git_output(
                path, "status", "--porcelain=v1", "--untracked-files=all"
            )
            ahead = git_output(path, "rev-list", "--count", f"{record.base_sha}..HEAD")
            ignored = ignored_scan(path)
            include_ignored = bool(args.include_ignored or config.archive_ignored)
            action["dirty"] = bool(status)
            action["ahead"] = int(ahead)
            action["ignored_files"] = len(ignored["files"])
            action["ignored_bytes"] = ignored["bytes"]
            if ignored["secret"]:
                action["action"] = "HUMAN_REVIEW"
                action["secret"] = ignored["secret"][:10]
                actions.append(action)
                continue
            if ignored["unknown"] and not include_ignored:
                action["action"] = "HUMAN_REVIEW"
                action["unknown"] = ignored["unknown"][:10]
                actions.append(action)
                continue
            needs_archive = (
                bool(status)
                or ahead != "0"
                or (include_ignored and bool(ignored["files"]))
            )
            if needs_archive:
                action["action"] = "ARCHIVE_REMOVE"
                action["archive_status"] = (
                    "ARCHIVE_VERIFIED" if apply_changes else "ARCHIVE_PENDING"
                )
                if apply_changes:
                    ref = create_archive(record, include_ignored=include_ignored)
                    action["archive_ref"] = ref
                    action["archive_status"] = "ARCHIVE_VERIFIED"
                    record.archive_ref = ref
                    run_git(path, "reset", "--hard", "HEAD", check=False)
                    run_git(path, "clean", "-fd", check=False)
                    if not remove_worktree(repo, record, app):
                        action["action"] = "REMOVE_REFUSED"
            else:
                action["action"] = "REMOVE"
                action["archive_status"] = "NO_ARCHIVE_NEEDED"
                if apply_changes:
                    if not remove_worktree(repo, record, app):
                        action["action"] = "REMOVE_REFUSED"
            actions.append(action)
    if apply_changes:
        invalidate_size_cache(repo)
    if quiet:
        return EXIT_OK
    if app.json_mode:
        app.emit({"actions": actions, "applied": apply_changes})
    else:
        for action in actions:
            print(
                f"{action['action']} id={action['id']} path={action['path']} "
                f"state={action.get('state')} branch={action.get('branch')} "
                f"archive_status={action.get('archive_status', '')} "
                f"ignored_files={action.get('ignored_files', 0)} "
                f"ignored_bytes={action.get('ignored_bytes', 0)}"
            )
    return EXIT_OK


def command_status(args: argparse.Namespace, app: App) -> int:
    repo = resolve_repo(args.repo)
    config = config_for_repo(repo, app)
    base = resolve_base(repo, config, app, fetch=False)
    records = managed_records(repo)
    counts: dict[str, int] = {}
    for record in records:
        counts[record.state] = counts.get(record.state, 0) + 1
    data = {
        "repo": str(repo.checkout),
        "common_dir": str(repo.common_dir),
        "repo_key": repo.repo_key,
        "base_ref": base.ref,
        "base_sha": base.sha,
        "protected_paths": [str(item) for item in config.protected_paths],
        "managed": len(records),
        "max_managed_worktrees": config.max_managed_worktrees,
        "managed_bytes": managed_bytes(repo),
        "disk_budget_gib": config.disk_budget_gib,
        "states": counts,
    }
    if app.json_mode:
        app.emit(data)
    else:
        for key, value in data.items():
            print(f"{key}={value}")
    return EXIT_OK


def command_list(args: argparse.Namespace, app: App) -> int:
    repo = resolve_repo(args.repo)
    records = managed_records(repo)
    if app.json_mode:
        app.emit({"worktrees": [record.to_dict() for record in records]})
    else:
        for record in records:
            print(
                f"{record.admin_id}\t{record.state}\t{record.branch}\t{record.path}"
            )
    return EXIT_OK


def looks_like_prep_path(repo: Repo, path: Path) -> bool:
    name = path.name
    return (
        name.startswith(f".{repo.main_worktree.name}-prep")
        or "-prep-" in name
        or name.endswith("-prep")
    )


def remove_prunable_registration(repo: Repo, worktree: Worktree) -> bool:
    if not worktree.prunable or not worktree.admin_id or worktree.admin_id == "main":
        return False
    admin_dir = repo.common_dir / "worktrees" / worktree.admin_id
    if not admin_dir.is_dir():
        return False
    shutil.rmtree(admin_dir)
    return True


def command_adopt(args: argparse.Namespace, app: App) -> int:
    repo = resolve_repo(args.repo)
    config = config_for_repo(repo, app)
    base = resolve_base(repo, config, app, fetch=False)
    apply_changes = bool(args.apply)
    existing = {resolve_path(record.path) for record in managed_records(repo)}
    parsed = parse_worktrees(repo)
    by_admin = {
        worktree.admin_id: worktree
        for worktree in parsed
        if worktree.admin_id
    }
    managed: list[dict[str, Any]] = []
    user_owned: list[str] = []
    prunable: list[dict[str, Any]] = []
    for worktree in parsed:
        path = resolve_path(worktree.path)
        if path == repo.checkout or path in existing:
            continue
        if worktree.prunable:
            prunable.append(
                {"path": str(path), "admin_id": worktree.admin_id}
            )
            continue
        branch = worktree.branch or ""
        if branch.startswith("prep-worktree/") and looks_like_prep_path(repo, path):
            managed.append(
                {
                    "path": str(path),
                    "branch": branch,
                    "head": worktree.head,
                    "admin_id": worktree.admin_id,
                }
            )
            if apply_changes and worktree.admin_id:
                now = time.time()
                merge_base = git_optional(
                    repo.checkout, "merge-base", worktree.head, base.sha
                )
                record = Record(
                    admin_id=worktree.admin_id,
                    path=str(path),
                    branch=branch or None,
                    base_sha=merge_base or base.sha,
                    owner_session="unknown",
                    owner_pid=0,
                    pid_start=None,
                    created_at=now,
                    last_seen=path.stat().st_mtime,
                    state="legacy",
                )
                write_record(repo, record)
        else:
            user_owned.append(str(path))
    if apply_changes:
        for item in prunable:
            worktree = by_admin.get(item["admin_id"])
            if worktree:
                remove_prunable_registration(repo, worktree)
    data = {
        "managed_legacy": managed,
        "user_owned": user_owned,
        "prunable": prunable,
        "applied": apply_changes,
    }
    if app.json_mode:
        app.emit(data)
    else:
        print(f"managed_legacy={len(managed)}")
        print(f"user_owned={len(user_owned)}")
        print(f"prunable={len(prunable)}")
        for item in managed:
            print(f"LEGACY {item['path']} {item['branch']}")
        for item in user_owned:
            print(f"USER_OWNED {item}")
        for item in prunable:
            print(f"PRUNABLE {item['path']}")
    return EXIT_OK


def command_doctor(args: argparse.Namespace, app: App) -> int:
    repo = resolve_repo(args.repo)
    config = config_for_repo(repo, app)
    issues: list[str] = []
    try:
        repo.state_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        issues.append(f"state dir not writable: {exc}")
    root = default_worktree_root(repo, config, app)
    if not os.access(root, os.W_OK):
        issues.append(f"worktree root not writable: {root}")
    paths: dict[Path, str] = {}
    for record in managed_records(repo):
        path = resolve_path(record.path)
        if record.state != "archived" and not path.exists():
            issues.append(f"missing worktree: {record.admin_id} {path}")
        if path in paths:
            issues.append(f"duplicate path: {path} {paths[path]} {record.admin_id}")
        paths[path] = record.admin_id
        if record.branch and record.state != "archived":
            branch_exists = run_git(
                repo.checkout,
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{record.branch}",
                check=False,
            ).returncode == 0
            if not branch_exists:
                issues.append(f"missing branch: {record.admin_id} {record.branch}")
    data = {
        "ok": not issues,
        "repo": str(repo.checkout),
        "state_dir": str(repo.state_dir),
        "worktree_root": str(root),
        "managed": len(paths),
        "issues": issues,
    }
    if app.json_mode:
        app.emit(data)
    else:
        print(f"OK={str(not issues).lower()}")
        for issue in issues:
            print(f"ISSUE {issue}")
    return EXIT_OK if not issues else EXIT_ERROR


def command_restore(args: argparse.Namespace, app: App) -> int:
    repo = resolve_repo(args.repo)
    config = config_for_repo(repo, app)
    base = resolve_base(repo, config, app, fetch=False)
    path = resolve_path(args.path)
    if path.exists():
        raise PrepError(f"restore path already exists: {path}")
    worktrees = parse_worktrees(repo)
    error = isolation_error(repo, path, config, worktrees)
    if error:
        raise PrepError(error, EXIT_REPO)
    if run_git(
        repo.checkout, "check-ref-format", args.ref, check=False
    ).returncode != 0:
        raise PrepError(f"invalid archive ref: {args.ref}", EXIT_ERROR)
    branch = unique_branch(repo, base.default_branch)
    process = run_git(
        repo.checkout,
        "worktree",
        "add",
        "-b",
        branch,
        str(path),
        args.ref,
        check=False,
    )
    if process.returncode != 0:
        raise PrepError(process.stderr.strip() or "git worktree add failed")
    admin_id = admin_id_for_path(repo, path)
    if not admin_id:
        raise PrepError(f"could not resolve worktree id for {path}")
    now = time.time()
    record = Record(
        admin_id=admin_id,
        path=str(path),
        branch=branch,
        base_sha=base.sha,
        owner_session=session_id(),
        owner_pid=os.getpid(),
        pid_start=pid_start_time(os.getpid()),
        created_at=now,
        last_seen=now,
        state="leased",
    )
    write_record(repo, record)
    if app.json_mode:
        app.emit({"id": admin_id, "path": str(path), "branch": branch, "ref": args.ref})
    else:
        print(f"RESTORE_OK id={admin_id} path={path} branch={branch} ref={args.ref}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prep-worktree")
    parser.add_argument("--version", action="version", version="prep-worktree 1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(name: str) -> argparse.ArgumentParser:
        sub = subparsers.add_parser(name)
        sub.add_argument("--json", action="store_true")
        return sub

    acquire = add_common("acquire")
    acquire.add_argument("--repo", default=None)
    acquire.add_argument("--no-reuse", action="store_true")
    acquire.set_defaults(func=command_acquire)

    guard = add_common("guard")
    guard.add_argument("--id", default=None)
    guard.set_defaults(func=command_guard)

    heartbeat = add_common("heartbeat")
    heartbeat.add_argument("--id", default=None)
    heartbeat.set_defaults(func=command_heartbeat)

    release = add_common("release")
    release.add_argument("--id", default=None)
    release.set_defaults(func=command_release)

    reap = add_common("reap")
    reap.add_argument("--repo", default=None)
    reap.add_argument("--apply", action="store_true")
    reap.add_argument("--dry-run", action="store_true")
    reap.add_argument("--include-ignored", action="store_true")
    reap.add_argument("--lock-timeout", type=float, default=5.0)
    reap.set_defaults(func=command_reap)

    status = add_common("status")
    status.add_argument("--repo", default=None)
    status.set_defaults(func=command_status)

    listing = add_common("list")
    listing.add_argument("--repo", default=None)
    listing.set_defaults(func=command_list)

    adopt = add_common("adopt")
    adopt.add_argument("--repo", default=None)
    adopt.add_argument("--apply", action="store_true")
    adopt.add_argument("--dry-run", action="store_true")
    adopt.set_defaults(func=command_adopt)

    doctor = add_common("doctor")
    doctor.add_argument("--repo", default=None)
    doctor.set_defaults(func=command_doctor)

    archive = add_common("archive")
    archive_sub = archive.add_subparsers(dest="archive_command", required=True)
    restore = archive_sub.add_parser("restore")
    restore.add_argument("--repo", default=None)
    restore.add_argument("--ref", required=True)
    restore.add_argument("--path", required=True)
    restore.add_argument("--json", action="store_true")
    restore.set_defaults(func=command_restore)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    app = App(json_mode=bool(getattr(args, "json", False)))
    try:
        return int(args.func(args, app))
    except PrepError as exc:
        if app.json_mode:
            app.emit({"error": str(exc), "exit_code": exc.code})
        else:
            print(f"ERROR {exc}", file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
