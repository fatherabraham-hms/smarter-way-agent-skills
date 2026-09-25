---
name: prep-worktree
description: >-
  Put a worktree on clean, up-to-date main/master without touching the current
  dirty branch. Use when the user says prep-worktree, prep worktree, or give me
  a clean main.
disable-model-invocation: true
metadata:
  requires:
    bins: ["git"]
---

# prep-worktree

Invocation is **explicit permission** to: switch the current worktree to
`$DEFAULT` when its tree is clean; discard uncommitted changes in other
worktrees **only** when idle >48h; move a blocking worktree onto a temp branch;
create a new worktree. The dirty files in the **current** worktree are never
discarded, and every other-worktree discard is recoverable (stash).

## Workflow

Copy and track:

```text
prep-worktree:
- [ ] 1. Preconditions + default branch
- [ ] 2. Clean tree → land in place (done)
- [ ] 3. Dirty: enumerate worktrees + pick idle target
- [ ] 4. Free $DEFAULT from a blocking worktree
- [ ] 5. Land target on clean $DEFAULT (discard via stash, or create worktree)
- [ ] 6. Pull + report
```

### 1. Preconditions + default branch

```bash
git rev-parse --show-toplevel   # abort if not a git repo
git status --porcelain          # the dirty set (gitignored files excluded)
git branch --show-current       # empty => detached HEAD (see below)
```

- **Prod guard:** if the toplevel path contains a `prod` component (e.g.
  `.../prod/<repo>`), **stop** — never discard or switch branches in a
  production/runtime checkout.
- **Detached HEAD:** **stop** and ask which branch the user means — do not
  guess.
- Resolve **`$DEFAULT`** offline-first: `git rev-parse --verify --quiet
  origin/main` → `main`; else same for `origin/master` → `master`; else local
  `main`, else local `master`; else **stop** and ask.
- `git remote` may be empty → skip all pull steps below.

### 2. Clean tree → land in place

- If already on `$DEFAULT`: land here — go to step 6 (pull + report). Done.
- Else `git checkout $DEFAULT`. If it fails with `'main' is already used by
  worktree at '<path>'`: that path is the blocker → run step 4 (it cannot be
  the current worktree here), then retry. No worktree hunting otherwise.

### 3. Dirty tree: enumerate worktrees + pick idle target

```bash
git worktree prune              # clear stale registrations from removed dirs
git worktree list --porcelain   # paths + branch per worktree
```

Exclude the current worktree from candidates. Portable mtime (GNU `%Y`, BSD
`%m` — never treat a stat failure as 0):

```bash
mts(){ stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo bad; }
```

For each candidate, **last activity** = max of HEAD commit timestamp, top-dir
mtime, and index mtime; then recheck every dirty file's own mtime (top-dir and
index mtimes miss deep edits):

```bash
head_ts=$(git -C "$WT" log -1 --format=%ct 2>/dev/null || echo 0)
act=$head_ts; for v in "$(mts "$WT")" "$(mts "$(git -C "$WT" rev-parse --absolute-git-dir)/index")"; do
  [ "$v" = bad ] && { echo "STAT FAILED $WT"; continue 2; }; act=$(( v > act ? v : act )); done
cut=$(( $(date +%s) - 172800 ))
# -uall so files inside untracked dirs are listed individually, not just the dir
for f in $(git -C "$WT" status --porcelain -uall | cut -c4-); do
  v=$(mts "$WT/$f"); [ "$v" = bad ] && continue; [ "$v" -gt "$cut" ] && { echo "ACTIVE $WT"; continue 2; }
done
echo "IDLE $WT @ $act"
```

A candidate is **idle** only if `act < cut` *and* the per-file loop printed no
ACTIVE. If `mts` reports `bad` (no stat flavor works), treat the worktree as
**active** — the heuristic must never fail toward discarding.

- Record each candidate's branch and short HEAD (for the report).
- `$TARGET` = idle candidate with the **oldest** activity. Note if
  `$TARGET`'s branch **is** `$DEFAULT` (then step 5A just discards; no
  checkout).
- No idle candidate → `$TARGET` = new worktree: step 4 first, then 5B.

### 4. Free $DEFAULT from a blocking worktree

A **blocker** is a worktree whose branch is `$DEFAULT`, **never** `$TARGET`.

- No blocker → step 5.
- **Blocker is the current (dirty) worktree:** the user is sitting on dirty
  main. **Stop and confirm** before moving — `switch -c` keeps their changes
  but renames their working branch mid-session. On yes:
  `git switch -c "prep-worktree/released-$DEFAULT-$(date -u +%Y%m%dT%H%M%SZ)"`.
- **Blocker is another worktree:** move it (uncommitted changes carry over):

  ```bash
  STAMP=$(date -u +%Y%m%dT%H%M%SZ)
  git -C "$BLOCKER" switch -c "prep-worktree/released-$DEFAULT-$STAMP"
  ```

Any `switch` failure (mid-rebase/merge in that worktree, name collision,
anything): **stop** and show the error with the blocker's path and branch.
Do not force, detach, or delete.

### 5. Land $TARGET on clean $DEFAULT

#### 5A. Existing idle worktree

Guard first: if the target's git dir contains `rebase-merge`, `rebase-apply`,
`MERGE_HEAD`, `CHERRY_PICK_HEAD`, or `BISECT_LOG`
(`git -C "$TARGET" rev-parse --absolute-git-dir`), **stop** and report.

If the target is dirty:

1. Capture the file list for the report: `git -C "$TARGET" status --porcelain
   -uall`.
2. If any listed file matches `.env*`, `id_rsa`, `id_ed25519`, `*.pem`,
   `*.key`, `credentials*`, or `secrets*`: **stop**, list them, ask before
   discarding.
3. Discard **recoverably** — the stash clears tracked and untracked changes
   from the tree but keeps them restorable:

   ```bash
   git -C "$TARGET" stash push -u -m "prep-worktree discarded from $WTNAME $STAMP"
   ```

   If stash fails, **stop** and report — do not fall back to
   destructive `restore`/`clean`.

Then, if the target's branch is not `$DEFAULT`:

```bash
git -C "$TARGET" checkout $DEFAULT
```

#### 5B. No idle worktree → create one

Local `$DEFAULT` ref must exist; creating it as a ref never touches another
worktree's checkout:

```bash
git rev-parse --verify --quiet "$DEFAULT" || git branch "$DEFAULT" "origin/$DEFAULT"
WT_ROOT=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
# sibling of the main checkout: <repo>-wt-main; append -2, -3, ... while the
# path exists on disk OR appears in `git worktree list --porcelain`
git worktree add "<chosen-path>" "$DEFAULT"
```

### 6. Pull + report

With a remote, refresh the landing worktree (no-op/divergence-safe):

```bash
git -C "$LANDING" pull --ff-only origin $DEFAULT
```

If `--ff-only` fails (local `$DEFAULT` diverged): **stop**, report, do not
rebase or merge.

Report:

- `$LANDING` (the worktree now on clean `$DEFAULT`): path, `git -C "$LANDING"
  status -sb`, pull result.
- **Where work happens next:** unless landing was in place, the session's cwd
  is still the old worktree — tell the user to `cd "$LANDING"` or start the
  next session there.
- Current worktree: branch + dirty file count unchanged (dirty path), or
  "switched in place" (clean path).
- Discards: stashed file list, the stash message to recover it with
  (`git -C "$TARGET" stash list`), and the branch + short HEAD the target was
  parked on.
- Temp branch created for any blocker.
