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
| `audit-plan` | `/audit-plan` | Six independent subagent passes (feasibility, performance and scalability, security, logical continuity, testability, feature flags), then one rollup report |
| `cleanup-branch-noise` | `/cleanup-branch-noise` | Discard branch noise, park unclear work on a CLEANUP branch, land on fresh main/master |
| `compr-code-review` | `/compr-code-review` | Structured PR/branch review; when an arch-blueprint is associated, also require goals met and gates passed |
| `install-ffmpeg` | `/install-ffmpeg` | Install `ffmpeg`/`ffprobe` on macOS, Linux, or Windows when missing |
| `media-disk-space-archiver` | `/media-disk-space-archiver` | Find large local media missing from an external archive, verify, optionally compress for a target screen size, then move approved files |
| `postgres-best-practices` | `/postgres-best-practices` | Postgres best practices for schema, queries, indexes, connections, RLS, and diagnostics; load before writing or changing anything in a Postgres database |
| `python-code-review` | `/python-code-review` | Python review focused on architecture, scalability, performance, known bad patterns, and code hygiene |
| `prep-worktree` | `/prep-worktree` | Create a repo-scoped worktree with an owner lease, non-blocking acquisition, and budgeted reaping |
| `smart-commit-to-pr` | `/smart-commit-to-pr` | Commit, push, and open or update a PR; cut a fresh feature branch from main/master when the current one is already merged |
| `smart-implement` | `/smart-implement` | Implement from a spec or tickets (TDD, typecheck, tests), then `/compr-code-review`, then commit |
| `smart-push-to-prod` | `/smart-push-to-prod` | Commit, push, open PR, squash-merge to main/master, refresh local default branch and any prod checkout mapped by `SMART_PUSH_PROD_PATH` |
| `test-audit` | `/test-audit` | Authoring gate for new tests, plus an audit of low-value or implementation-coupled tests and the test-only seams they require |

Source files live under `.agents/skills/<name>/SKILL.md`.

## Local settings

One user-local file is shared by every skill in this repo:

- `$XDG_CONFIG_HOME/smarter-way/config.json`
- else `$HOME/.config/smarter-way/config.json`

Copy [`config.example.json`](config.example.json) there. The shared file holds
`plans_path` and the per-repo `prep_worktree` settings. Do not add per-skill
config files.

`smart-push-to-prod` reads `SMART_PUSH_PROD_PATH` from the environment
(`<develop-toplevel>=<prod-toplevel>`, pairs separated by `;`). Set it in
`~/.bashrc` above any interactive-only return. Unset means that skill only
refreshes the current repo.

`prep-worktree` resolves the repository from the current checkout and reads its
entry under `prep_worktree.repos`. The repo key is the canonical Git common
directory, or the `origin` URL. When no entry exists, defaults apply. The skill
never blocks on a missing, dirty, or wrong-repository protected checkout.

The manager stores per-worktree records under `<git-common-dir>/prep-worktree/`.
Each worktree has one owner lease, one metadata file, and one lease file. Create
and acquire do not take a global lock. Reaping takes a short repository lock and
continues without reaping when the lock is busy.

Default limits are 8 managed worktrees, 20 GiB per repository, and a 24 hour
idle lease. Reaping archives tracked and untracked work into
`refs/prep-archive/<id>/<timestamp>` and verifies every file hash before
removal. Secret-looking ignored files stop reaping with `HUMAN_REVIEW`. Unmerged
branches are kept.

`PREP_WORKTREE_PROTECTED_DEV_PATH`, `PREP_WORKTREE_MAX`, and
`PREP_WORKTREE_ROOT` are optional overrides. The protected path override is
ignored when it belongs to another repository.

Example config:

```json
{
  "prep_worktree": {
    "defaults": {
      "max_managed_worktrees": 8,
      "disk_budget_gib": 20,
      "idle_ttl_hours": 24
    },
    "repos": {
      "/absolute/path/to/dev-checkout": {
        "protected_paths": ["/absolute/path/to/dev-checkout"]
      }
    }
  }
}
```

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

Install mode resolves the repository's primary development checkout. Running it
from a linked worktree still links the development directory, never the
ephemeral worktree.

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
