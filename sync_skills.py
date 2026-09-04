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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile Agent Skills into stable links for multiple editors."
    )
    parser.add_argument("--source", type=Path, required=True, help="plugin/source checkout")
    parser.add_argument(
        "--installed",
        type=Path,
        required=True,
        help="stable installed namespace, e.g. ~/.local/share/agent-skills/installed",
    )
    parser.add_argument(
        "--editor-dir",
        type=Path,
        action="append",
        required=True,
        help="editor skills directory; repeat once per editor",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="remove stale symlinks, never real files or directories",
    )
    parser.add_argument("--dry-run", action="store_true", help="show planned changes only")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        skills = discover(args.source.expanduser().resolve())
        changed, removed = reconcile(
            skills,
            args.installed.expanduser().resolve(),
            [directory.expanduser().resolve() for directory in args.editor_dir],
            prune_stale=args.prune,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
