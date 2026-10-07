---
name: prep-worktree
description: >-
  Put this session on a clean, up-to-date default-branch snapshot without
  touching any other worktree.
disable-model-invocation: true
metadata:
  requires:
    bins: ["git"]
---

# prep-worktree

Invocation is **explicit permission** to use the current checkout when it is
already a clean default checkout, or otherwise create a fresh isolated
worktree. It is never permission to modify another worktree. Existing
worktrees, their branches, their files, and their in-progress operations are
owned by their sessions and remain untouched.

The isolation rule is the design, not a fallback: do not select a worktree by
age, inspect its mtimes, reclaim its branch, stash its files, or clean its
directory. A dirty, stale, abandoned, or dusty worktree is still not a target.

## Workflow

Copy and track:

```text
prep-worktree:
- [ ] 1. Validate the current checkout and resolve the default branch
- [ ] 2. Use the current checkout only if it is clean and already on default
- [ ] 3. Refresh the default ref without touching a checkout
- [ ] 4. Create a unique isolated prep worktree and branch
- [ ] 5. Verify the landing tree and report the handoff
```

### 1. Validate the current checkout and resolve the default branch

Run these from the user's current directory:

```bash
CURRENT=$(git rev-parse --show-toplevel) || { echo "STOP: not a git checkout"; exit 1; }
CURRENT=$(cd "$CURRENT" && pwd -P)
git status --porcelain=v1 --untracked-files=all
CURRENT_BRANCH=$(git branch --show-current)
```

- **Production guard:** if `$CURRENT` has a path component named `prod`, stop.
  Never run this skill from a production/runtime checkout.
- A detached current checkout is allowed because it will be left untouched.
  Resolve the landing branch independently; do not guess from `HEAD`.
- Resolve one default branch, in this order. The conditional matters: do not
  print or use more than one candidate.

```bash
if git rev-parse --verify --quiet refs/remotes/origin/main >/dev/null; then
  DEFAULT=main
elif git rev-parse --verify --quiet refs/remotes/origin/master >/dev/null; then
  DEFAULT=master
elif git show-ref --verify --quiet refs/heads/main; then
  DEFAULT=main
elif git show-ref --verify --quiet refs/heads/master; then
  DEFAULT=master
else
  echo "STOP: no origin/main, origin/master, main, or master ref" >&2
  exit 1
fi
```

The current dirty set is for the final report only. It is never a reason to
stash, reset, clean, or otherwise alter the current checkout.

### 2. Use the current checkout only if it is clean and already on default

This is the only in-place path:

```bash
if [ "$CURRENT_BRANCH" = "$DEFAULT" ] && \
   [ -z "$(git status --porcelain=v1 --untracked-files=all)" ]; then
  LANDING=$CURRENT
  if git remote get-url origin >/dev/null 2>&1; then
    git pull --ff-only origin "$DEFAULT" || {
      echo "STOP: fast-forward pull failed in the current checkout" >&2
      exit 1
    }
  fi
  git status -sb
  exit 0
fi
```

Do not checkout `$DEFAULT` in the current worktree when this condition is
false. A clean feature checkout is still session-owned, and changing its
branch surprises the session that owns it. The fresh-worktree path below is
the normal path for parallel agents.

### 3. Refresh the default ref without touching a checkout

Do not run `git worktree prune` here. A stale registration cannot block a
unique new path, while pruning shared worktree metadata can race another agent
that is creating or removing a worktree.

If `origin` exists, fetch exactly the selected default branch. Treat a fetch
failure as a stop rather than silently landing on stale code:

```bash
if git remote get-url origin >/dev/null 2>&1; then
  git fetch --no-tags origin "$DEFAULT" || {
    echo "STOP: could not refresh origin/$DEFAULT; no landing worktree created" >&2
    exit 1
  }
  BASE="refs/remotes/origin/$DEFAULT"
else
  BASE="$DEFAULT"
fi
BASE_SHA=$(git rev-parse "$BASE") || {
  echo "STOP: landing base disappeared: $BASE" >&2
  exit 1
}
```

`git fetch` updates shared refs, not another worktree's files. If another
agent is simultaneously updating the same Git metadata and Git reports a lock
failure, make at most one short retry. If it still fails, stop and report the
lock error; never poll indefinitely and never remove a lock file.

### 4. Create a unique isolated prep worktree and branch

Create a never-before-used empty sibling directory. `mktemp -d` reserves the
name atomically; `rmdir` removes only that empty reservation so Git can own the
path. If the repository parent is not writable, use the system temporary
directory. Never reuse a path that already exists, even if it contains only
old dust.

```bash
REPO_PARENT=$(dirname "$CURRENT")
REPO_NAME=$(basename "$CURRENT")
WT_PATH=$(mktemp -d "$REPO_PARENT/.${REPO_NAME}-prep.XXXXXX" 2>/dev/null) || \
WT_PATH=$(mktemp -d "${TMPDIR:-/tmp}/${REPO_NAME}-prep.XXXXXX") || {
  echo "STOP: could not reserve an isolated worktree path" >&2
  exit 1
}
rmdir "$WT_PATH" || {
  echo "STOP: reserved landing path was not empty" >&2
  exit 1
}

WT_NAME=$(basename "$WT_PATH")
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BRANCH="prep-worktree/$DEFAULT-$STAMP-${WT_NAME##*.}"
```

Add a unique branch rather than checking out `$DEFAULT`. This avoids the
single-branch worktree lock and gives the next agent a real branch without
requiring it to mutate another checkout:

```bash
git worktree add -b "$BRANCH" "$WT_PATH" "$BASE_SHA" || {
  echo "STOP: git could not create the isolated worktree" >&2
  echo "  requested path: $WT_PATH" >&2
  echo "  requested branch: $BRANCH" >&2
  echo "  existing worktrees were not modified" >&2
  exit 1
}
```

The `git worktree add` command is the only command in this workflow that
registers a new worktree. Do not follow an error by switching, detaching,
stashing, resetting, cleaning, deleting, or repairing another worktree. If
the add partially registered a path, report it for manual recovery instead of
guessing what is safe to remove.

### 5. Verify the landing tree and report the handoff

The landing worktree must be on the unique prep branch, at the refreshed base,
and clean. A failure here concerns only the newly created landing worktree;
stop and report it without touching any other checkout.

```bash
test "$(git -C "$WT_PATH" branch --show-current)" = "$BRANCH" || {
  echo "STOP: landing branch verification failed" >&2
  exit 1
}
test "$(git -C "$WT_PATH" rev-parse HEAD)" = "$BASE_SHA" || {
  echo "STOP: landing base verification failed" >&2
  exit 1
}
test -z "$(git -C "$WT_PATH" status --porcelain=v1 --untracked-files=all)" || {
  echo "STOP: newly created landing tree is not clean" >&2
  exit 1
}
git -C "$WT_PATH" status -sb
```

Report all of the following:

- `LANDING`: the absolute path to `$WT_PATH`.
- `BRANCH`: the isolated `prep-worktree/...` branch and `BASE_SHA`.
- `CURRENT`: the original path, branch, and dirty-file count, unchanged.
- `OTHER WORKTREES`: “not inspected or modified”; stale registrations were
  not pruned.
- `NEXT`: the next session must start in `$WT_PATH`; it must not checkout
  `$DEFAULT` there, because another agent may own that branch.

The prep branch is session-owned. Remove its worktree and branch only in a
separate, explicit cleanup operation after the session has finished and its
work has been committed or otherwise preserved.
