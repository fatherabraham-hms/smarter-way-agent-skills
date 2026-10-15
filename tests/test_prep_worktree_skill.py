import re
import subprocess
import tempfile
from pathlib import Path


SKILL = Path(__file__).parents[1] / ".agents/skills/prep-worktree/SKILL.md"


def test_prep_worktree_requires_configured_protected_checkout():
    text = SKILL.read_text(encoding="utf-8")

    assert "PREP_WORKTREE_PROTECTED_DEV_PATH" in text
    assert 'bins: ["bash", "git"]' in text
    assert "must be a clean checkout" in text
    assert "different repository" in text
    assert 'test "$PROTECTED_ROOT" = "$PROTECTED_DEV_PATH"' in text
    assert "protected dev checkout must be on $DEFAULT" in text
    assert "--untracked-files=all --ignored" in text
    assert "MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD" in text


def test_prep_worktree_has_no_in_place_landing_path():
    text = SKILL.read_text(encoding="utf-8")

    assert "always creates a fresh isolated prep worktree" in text
    assert "git pull --ff-only" not in text
    assert "LANDING=$CURRENT" not in text
    assert 'path_is_within "$PROTECTED_DEV_PATH" "$WT_PATH"' in text
    assert 'path_is_within "$CURRENT_COMMON_DIR" "$WT_PATH"' in text
    assert 'test ! -L "$WT_PATH"' in text
    assert 'path_is_within "$CURRENT" "$WT_PATH"' in text


def test_prep_worktree_limits_creation_and_uses_non_destructive_cleanup():
    text = SKILL.read_text(encoding="utf-8")

    assert "PREP_WORKTREE_MAX" in text
    assert "WORKTREE_COUNT" in text
    assert "`>=`" in text
    assert "48 hours" in text
    assert 'mkdir "$LOCK_DIR"' in text
    assert 'printf \'%s\\n\' "$$" > "$LOCK_DIR/pid"' in text
    assert "re-enumerate" in text
    assert "git worktree remove -- \"$CANDIDATE_PATH\"" in text
    assert "Never use `--force`, `rm -rf`, `git worktree prune`" in text
    assert "shell `read`" in text


def test_embedded_bash_blocks_are_syntactically_valid():
    text = SKILL.read_text(encoding="utf-8")
    blocks = re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)

    assert blocks
    for block in blocks:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", encoding="utf-8") as script:
            script.write(block)
            script.flush()
            result = subprocess.run(
                ["bash", "-n", script.name], capture_output=True, text=True
            )
        assert result.returncode == 0, result.stderr
