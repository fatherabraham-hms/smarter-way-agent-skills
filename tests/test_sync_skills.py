import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "sync_skills.py"


def run_sync(source, installed, *editors, prune=False):
    command = [
        sys.executable,
        str(SCRIPT),
        "--source",
        str(source),
        "--installed",
        str(installed),
    ]
    for editor in editors:
        command.extend(["--editor-dir", str(editor)])
    if prune:
        command.append("--prune")
    return subprocess.run(command, capture_output=True, text=True)


def write_skill(source: Path, name: str, body: str = "v1") -> Path:
    path = source / name
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill.\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_reconcile_points_editors_to_stable_namespace(tmp_path):
    source = tmp_path / "plugin"
    installed = tmp_path / "installed"
    cursor = tmp_path / "cursor" / "skills"
    claude = tmp_path / "claude" / "skills"
    skill = write_skill(source, "review-code")

    result = run_sync(source, installed, cursor, claude)

    assert result.returncode == 0, result.stderr
    assert (installed / "review-code").resolve() == skill.resolve()
    assert (cursor / "review-code").resolve() == (installed / "review-code").resolve()
    assert (claude / "review-code").resolve() == (installed / "review-code").resolve()


def test_pull_and_move_skill_path_repairs_all_links(tmp_path):
    source = tmp_path / "plugin"
    installed = tmp_path / "installed"
    editor = tmp_path / "editor"
    old_skill = write_skill(source / "v1", "review-code", "old")
    run_sync(source, installed, editor)

    old_skill.rename(source / "v1" / "review-code-renamed")
    renamed = source / "v1" / "review-code-renamed"
    (renamed / "SKILL.md").write_text(
        "---\nname: review-code-renamed\ndescription: Test skill.\n---\n\nnew\n",
        encoding="utf-8",
    )
    write_skill(source / "v2", "review-code", "new")

    result = run_sync(source, installed, editor, prune=True)

    assert result.returncode == 0, result.stderr
    assert (installed / "review-code").resolve() == (source / "v2" / "review-code").resolve()
    assert (editor / "review-code").resolve() == (installed / "review-code").resolve()
    assert (installed / "review-code-renamed").exists()
    assert renamed.is_dir()


def test_prune_never_deletes_real_directories(tmp_path):
    source = tmp_path / "plugin"
    installed = tmp_path / "installed"
    editor = tmp_path / "editor"
    write_skill(source, "review-code")
    (installed / "keep-me").mkdir(parents=True)
    (editor / "keep-me").mkdir(parents=True)

    result = run_sync(source, installed, editor, prune=True)

    assert result.returncode == 0, result.stderr
    assert (installed / "keep-me").is_dir()
    assert (editor / "keep-me").is_dir()


def test_duplicate_names_fail_before_writing(tmp_path):
    source = tmp_path / "plugin"
    installed = tmp_path / "installed"
    editor = tmp_path / "editor"
    write_skill(source / "one", "same")
    write_skill(source / "two", "same")

    result = run_sync(source, installed, editor)

    assert result.returncode == 1
    assert "duplicate skill names" in result.stderr
    assert not installed.exists()
