# smarter-way-agent-skills

Portable Agent Skills with stable editor links

This repository provides a small, dependency-free reconciler for Agent Skills.
It keeps editor-specific skill directories pointed at a stable namespace instead
of pointing them directly at plugin-internal paths.

```text
plugin checkout ──> ~/.local/share/agent-skills/installed/<skill>
                                  ▲
       ~/.cursor/skills/<skill> ──┘
       ~/.claude/skills/<skill> ──┘
        ~/.codex/skills/<skill> ──┘
```

After a plugin update changes or moves a skill, rerun the reconciler. It
discovers skills from `SKILL.md`, repairs all links, and can prune stale
symlinks. Real files and directories are never deleted automatically.

## Usage

```bash
python3 sync_skills.py \
  --source /path/to/plugin-checkout \
  --installed ~/.local/share/agent-skills/installed \
  --editor-dir ~/.cursor/skills \
  --editor-dir ~/.claude/skills \
  --editor-dir ~/.codex/skills \
  --prune
```

Use `--dry-run` to inspect the planned reconciliation first. The command
refuses to replace a real file or directory at a managed skill path; remove or
relocate that path explicitly before retrying.

The source must contain one or more directories with `SKILL.md` files. Each
file must have a valid `name` in YAML frontmatter matching its parent directory.
Duplicate skill names are rejected before any links are written.

Run the test suite with:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest
```
