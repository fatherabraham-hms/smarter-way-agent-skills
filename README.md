# smarter-way-agent-skills

Portable Agent Skills with stable editor links

This repository provides a small, dependency-free reconciler for Agent Skills.
It keeps editor-specific skill directories pointed at a stable namespace instead
of pointing them directly at plugin-internal paths.

```text
plugin checkout ──> ~/.local/share/agent-skills/installed/<skill>
                                  ▲
       ~/.cursor/skills/<skill> ──┤
       ~/.agents/skills/<skill> ──┤
       ~/.claude/skills/<skill> ──┤
        ~/.codex/skills/<skill> ──┘
```

After a plugin update changes or moves a skill, rerun the reconciler. It
discovers skills from `SKILL.md`, repairs all links, and can prune stale
symlinks. Real files and directories are never deleted automatically.

## Included skills

| Skill | Slash command | Description |
|-------|---------------|-------------|
| `cleanup-branch-noise` | `/cleanup-branch-noise` | Discard branch noise, park unclear work on a CLEANUP branch, land on fresh main/master |
| `compr-code-review` | `/compr-code-review` | Structured PR/branch review; when an arch-blueprint is associated, also require goals met and gates passed |
| `smart-push-to-prod` | `/smart-push-to-prod` | Commit, push, open PR, squash-merge to main/master, refresh local default branch |

Source files live under `.agents/skills/<name>/SKILL.md`.

`compr-code-review` looks up architecture plans from a **user-local** setting,
not from this repository. Copy
`.agents/skills/compr-code-review/config.example.json` to
`.agents/skills/compr-code-review/config.json` (gitignored) or
`$HOME/.config/smarter-way/compr-code-review.json`, or set
`COMPR_CODE_REVIEW_PLANS_PATH`. Point `plans_path` at your architecture plans
root. Optional `cursor_plans` is the local editor plans directory.

## Install from this repo

After cloning on any machine, from the repo root:

```bash
python3 sync_skills.py
```

That links `.agents/skills` into common editor directories:

| Editor / runtime | Skills directory |
|------------------|------------------|
| Cursor | `~/.cursor/skills` |
| OpenClaw (personal agent skills) | `~/.agents/skills` |
| Claude | `~/.claude/skills` |
| Codex | `~/.codex/skills` |

Stable copies live under `~/.local/share/agent-skills/installed`. After `git pull`,
rerun the same command to refresh links.

Preview first with `python3 sync_skills.py --dry-run`.

If a skill path already exists as a real directory (not a symlink), move or remove
it first — the reconciler refuses to overwrite real paths.

### Advanced usage

Override defaults when needed:

```bash
python3 sync_skills.py \
  --source .agents/skills \
  --installed ~/.local/share/agent-skills/installed \
  --editor-dir ~/.cursor/skills \
  --editor-dir ~/.agents/skills \
  --prune
```

Or point at another checkout:

```bash
python3 sync_skills.py \
  --source /path/to/plugin-checkout/.agents/skills \
  --installed ~/.local/share/agent-skills/installed \
  --editor-dir ~/.cursor/skills \
  --prune
```

The source must contain one or more directories with `SKILL.md` files. Each
file must have a valid `name` in YAML frontmatter matching its parent directory.
Duplicate skill names are rejected before any links are written.

Run the test suite with:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest
```
