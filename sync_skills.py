#!/usr/bin/env python3
"""Reconcile portable Agent Skills into stable editor-specific link trees."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

DEFAULT_INSTALLED = Path("~/.local/share/agent-skills/installed")
DEFAULT_EDITOR_DIRS = (
    Path("~/.cursor/skills"),
    Path("~/.agents/skills"),
    Path("~/.claude/skills"),
    Path("~/.codex/skills"),
)


class SyncError(RuntimeError):
    """Raised when the source skill set cannot be reconciled safely."""


@dataclass(frozen=True)
class Skill:
    name: str
    path: Path


def parse_name(skill_file: Path) -> str:
    """Read and validate the required `name` field from SKILL.md frontmatter."""
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SyncError(f"{skill_file}: missing YAML frontmatter")

    end = text.find("\n---", 4)
    if end == -1:
        raise SyncError(f"{skill_file}: unterminated YAML frontmatter")

    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if key.strip() == "name" and separator:
            name = value.strip().strip("'\"")
            if not NAME_RE.fullmatch(name):
                raise SyncError(f"{skill_file}: invalid skill name {name!r}")
            if name != skill_file.parent.name:
                raise SyncError(
                    f"{skill_file}: name {name!r} does not match "
                    f"directory {skill_file.parent.name!r}"
                )
            return name

    raise SyncError(f"{skill_file}: frontmatter has no name")


def discover(source: Path) -> list[Skill]:
    """Discover every skill below source, excluding VCS metadata."""
    if not source.is_dir():
        raise SyncError(f"source is not a directory: {source}")

    skills: list[Skill] = []
    for skill_file in sorted(source.rglob("SKILL.md")):
        if ".git" in skill_file.parts:
            continue
        skills.append(Skill(parse_name(skill_file), skill_file.parent))

    by_name: dict[str, list[Path]] = {}
    for skill in skills:
        by_name.setdefault(skill.name, []).append(skill.path)
    duplicates = {name: paths for name, paths in by_name.items() if len(paths) > 1}
    if duplicates:
        details = "; ".join(
            f"{name}: {', '.join(map(str, paths))}"
            for name, paths in sorted(duplicates.items())
        )
        raise SyncError(f"duplicate skill names: {details}")
    return skills


def ensure_parent(path: Path, dry_run: bool) -> None:
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)


def replace_link(link: Path, target: Path, dry_run: bool) -> None:
    """Replace only links or absent paths; never silently delete real directories."""
    if link.exists() or link.is_symlink():
        if not link.is_symlink():
            raise SyncError(
                f"refusing to replace non-symlink path {link}; "
                "move it away or remove it explicitly"
            )
        if link.resolve(strict=False) == target.resolve(strict=False):
            return

    if dry_run:
        return

    ensure_parent(link.parent, dry_run=False)
    temp = Path(
        tempfile.mkdtemp(prefix=f".{link.name}.", dir=str(link.parent))
    )
    temp_link = temp / "link"
    try:
        temp_link.symlink_to(target)
        os.replace(temp_link, link)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def prune(directory: Path, expected: set[str], dry_run: bool) -> list[str]:
    """Remove stale symlinks only; preserve all real files and directories."""
    if not directory.is_dir():
        return []
    removed: list[str] = []
    for entry in directory.iterdir():
        if entry.name in expected or not entry.is_symlink():
            continue
        if not dry_run:
            entry.unlink()
        removed.append(entry.name)
    return removed


def reconcile(
    skills: list[Skill],
    installed: Path,
    editor_dirs: list[Path],
    *,
    prune_stale: bool,
    dry_run: bool,
) -> tuple[list[str], list[str]]:
    """Build the stable namespace and point each editor at it."""
    expected = {skill.name for skill in skills}
    changed: list[str] = []
    removed: list[str] = []

    ensure_parent(installed, dry_run)
    for skill in skills:
        stable = installed / skill.name
        before = stable.resolve(strict=False) if stable.is_symlink() else None
        replace_link(stable, skill.path, dry_run)
        if before != skill.path.resolve():
            changed.append(str(stable))

    if prune_stale:
        removed.extend(f"{installed}/{name}" for name in prune(installed, expected, dry_run))

    for editor_dir in editor_dirs:
        ensure_parent(editor_dir, dry_run)
        for skill in skills:
            editor_link = editor_dir / skill.name
            stable = installed / skill.name
            before = editor_link.resolve(strict=False) if editor_link.is_symlink() else None
            replace_link(editor_link, stable, dry_run)
            if before != stable.resolve(strict=False):
                changed.append(str(editor_link))
        if prune_stale:
            removed.extend(
                f"{editor_dir}/{name}"
                for name in prune(editor_dir, expected, dry_run)
            )
    return changed, removed


def repo_source() -> Path:
    """Default skill source: `.agents/skills` next to this script."""
    return Path(__file__).resolve().parent / ".agents" / "skills"


def is_install_mode(args: argparse.Namespace) -> bool:
    if args.install:
        return True
    return args.source is None and args.installed is None and not args.editor_dir


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, list[Path], bool]:
    install_mode = is_install_mode(args)
    source = args.source or (repo_source() if install_mode else None)
    installed = args.installed or (DEFAULT_INSTALLED if install_mode else None)
    editor_dirs = args.editor_dir or (list(DEFAULT_EDITOR_DIRS) if install_mode else None)
    prune = args.prune or (install_mode and not args.no_prune)

    missing: list[str] = []
    if source is None:
        missing.append("--source")
    if installed is None:
        missing.append("--installed")
    if not editor_dirs:
        missing.append("--editor-dir")
    if missing:
        raise SyncError(
            "missing required argument(s): "
            + ", ".join(missing)
            + " (or run with no arguments / --install for defaults)"
        )

    source = source.expanduser().resolve()
    if install_mode and not source.is_dir():
        raise SyncError(
            f"skill source not found: {source}\n"
            "Run from a repo checkout that contains .agents/skills/, "
            "or pass --source explicitly."
        )

    return (
        source,
        installed.expanduser().resolve(),
        [directory.expanduser().resolve() for directory in editor_dirs],
        prune,
    )


def print_install_summary(
    skills: list[Skill],
    *,
    source: Path,
    installed: Path,
    editor_dirs: list[Path],
    dry_run: bool,
) -> None:
    verb = "Would install" if dry_run else "Installed"
    editors = ", ".join(str(path) for path in editor_dirs)

    print()
    print(f"{verb} {len(skills)} skill(s):")
    if skills:
        for skill in skills:
            print(f"  /{skill.name}")
    else:
        print("  (none)")
    print(f"  source:    {source}")
    print(f"  stable:    {installed}")
    print(f"  editors:   {editors}")
    print()
    print("Next steps:")
    print("  • Cursor — start a new chat; use /skill-name or attach the skill")
    print("  • OpenClaw — restart the gateway or start a fresh agent session")
    print("  • After git pull here, rerun: python3 sync_skills.py")
    print()
    print("If a skill path already exists as a real directory (not a symlink),")
    print("move or remove it first — this script never overwrites real paths.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile Agent Skills into stable links for multiple editors.",
        epilog=(
            "With no arguments (or --install), links this repo's .agents/skills "
            "into ~/.cursor/skills, ~/.agents/skills, and other common editor dirs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="use repo defaults (same as running with no arguments)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="plugin/source checkout (default with --install: .agents/skills in this repo)",
    )
    parser.add_argument(
        "--installed",
        type=Path,
        help="stable installed namespace (default with --install: ~/.local/share/agent-skills/installed)",
    )
    parser.add_argument(
        "--editor-dir",
        type=Path,
        action="append",
        help="editor skills directory; repeat once per editor (default with --install: common editor dirs)",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="remove stale symlinks, never real files or directories",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="with --install, do not remove stale symlinks managed by this repo",
    )
    parser.add_argument("--dry-run", action="store_true", help="show planned changes only")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)
    try:
        source, installed, editor_dirs, prune = resolve_paths(args)
        skills = discover(source)
        changed, removed = reconcile(
            skills,
            installed,
            editor_dirs,
            prune_stale=prune,
            dry_run=args.dry_run,
        )
    except (OSError, SyncError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    action = "would update" if args.dry_run else "updated"
    print(f"{action} {len(changed)} link(s); discovered {len(skills)} skill(s)")
    if removed:
        verb = "would remove" if args.dry_run else "removed"
        print(f"{verb} {len(removed)} stale link(s)")

    if is_install_mode(args):
        print_install_summary(
            skills,
            source=source,
            installed=installed,
            editor_dirs=editor_dirs,
            dry_run=args.dry_run,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
