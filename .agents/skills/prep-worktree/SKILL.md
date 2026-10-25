---
name: prep-worktree
description: >-
  Create a fresh isolated worktree from the current repo's default branch.
  Never land on the current or protected checkout.
disable-model-invocation: true
metadata:
  requires:
    bins: ["bash", "git", "python3"]
---

# prep-worktree

Create one isolated worktree for one agent. The manager keys state by repository, not by a global environment variable. It never blocks on a dirty, missing, or wrong-repository protected checkout. It leases each worktree to one owner and reclaims idle worktrees under a disk budget.

## Start here

Run this from the repository you want to work in.

```bash
eval "$(prep-worktree acquire)"
prep-worktree guard
```

`acquire` prints shell exports and changes nothing until you `eval` them. `guard` refuses to continue when the current worktree is leased to another owner. Run `guard` before the first edit and after a context switch.

When the work is committed, pushed, or otherwise saved, release the lease.

```bash
prep-worktree release
```

`release` marks the worktree `idle` only when it is clean and has no commits ahead of its base. A dirty worktree becomes `needs-cleanup`. Nothing is deleted by `release`.

## Commands

| Command | Use |
| --- | --- |
| `prep-worktree acquire` | Create or reuse a worktree and lease it to the current owner |
| `prep-worktree guard` | Fail when the current worktree belongs to another owner |
| `prep-worktree heartbeat` | Refresh the lease timestamp |
| `prep-worktree release` | Mark the lease idle or needs-cleanup |
| `prep-worktree list` | List managed worktrees |
| `prep-worktree status` | Show repo, base, protected paths, and managed counts |
| `prep-worktree reap --dry-run` | Report reclaim candidates and change nothing |
| `prep-worktree reap --apply` | Archive, verify, remove safe candidates, and keep unmerged branches |
| `prep-worktree adopt --dry-run` | Report legacy and user-owned worktrees |
| `prep-worktree adopt --apply` | Add records for legacy prep worktrees only |
| `prep-worktree doctor` | Check records, paths, branches, and writable roots |
| `prep-worktree archive restore --ref <ref> --path <path>` | Restore an archive into a new managed worktree |

Every command accepts `--json`. Use it in scripts.

## Configuration

The manager reads the shared config at `$XDG_CONFIG_HOME/smarter-way/config.json`, then `$HOME/.config/smarter-way/config.json`. When the file or a repo entry is absent, defaults apply. The manager never stops because configuration is missing.

```json
{
  "prep_worktree": {
    "defaults": {
      "max_managed_worktrees": 8,
      "disk_budget_gib": 20,
      "idle_ttl_hours": 24,
      "worktree_root": null,
      "archive_ignored": false,
      "protected_paths": []
    },
    "repos": {
      "/absolute/path/to/dev-checkout": {
        "protected_paths": ["/absolute/path/to/dev-checkout"],
        "max_managed_worktrees": 8
      }
    }
  }
}
```

`protected_paths` are exclusion paths. The manager never lands inside one. It does not require a protected path to exist, to be clean, to be on the default branch, or to belong to the current repository. A bad protected path becomes a warning.

The current checkout is always an implicit protected path. The manager never mutates it.

`PREP_WORKTREE_PROTECTED_DEV_PATH` and `PREP_WORKTREE_MAX` are optional legacy overrides. A protected path that belongs to another repository is ignored with `LEGACY_PROTECTED_IGNORED`. `PREP_WORKTREE_ROOT` overrides `worktree_root`.

## Safety rules

The manager never force-removes a worktree. It removes a worktree only when all of these are true.

- The worktree has a managed record.
- No live lease or process working directory points at it.
- Its branch is not locked.
- Its tracked and untracked work is clean or archived and verified.
- Its ignored files are regenerable, or the operator passed `--include-ignored`.

Secret-looking ignored or untracked files stop reaping with `HUMAN_REVIEW`. This includes `.env`, `*.pem`, `*.key`, `credentials*`, `secrets.*`, and SSH keys.

An archive is a Git ref under `refs/prep-archive/<id>/<timestamp>`. The manager reads the archive back and compares every file hash before removal. A failed verification leaves the worktree in place.

Unmerged branches are kept after worktree removal. Merged branches with no unique commits are deleted.

## Reclaim policy

`acquire` calls reaping when the managed count reaches `max_managed_worktrees` or the disk budget is reached. Reaping uses a repository-scoped `flock` with a short timeout. If the lock is busy, acquire prints `REAP_SKIPPED` and creates the worktree anyway. Acquisition never waits on the human.

The default worktree root is a sibling directory of the primary checkout, named `.<repo>-prep-worktrees`. When that parent is not writable, the manager uses `$TMPDIR/smarter-way/<repo>-prep-worktrees`.

## Adopt existing worktrees

Run the dry run first.

```bash
prep-worktree adopt --dry-run
prep-worktree reap --dry-run
```

Adoption records a worktree only when its branch starts with `prep-worktree/` and its path looks like a prep worktree. Every other worktree is user-owned and never touched. Prunable registrations are removed by exact admin id, never with a blanket `git worktree prune`.

## Verification

Run the behavior tests with a Python environment that has pytest.

```bash
python3 -m pytest tests/test_prep_worktree.py
```

The tests create throwaway repositories. They cover two repos in one shell, dirty and missing protected paths, ignored files, stale base refs, concurrent acquires, foreign guards, dirty archives, secret refusals, reuse, locked reaping, adoption, and prunable registration cleanup.

## Limits

The guard is cooperative. A same-user process can still write into another worktree when it ignores the guard. The guard prevents accidents, not a hostile process. The archive and lease rules make cleanup recoverable.

`flock` is reliable on local filesystems. It is not reliable on NFS or SMB. macOS does not ship the `flock` command, but Python's `fcntl` module provides the same kernel lock.
