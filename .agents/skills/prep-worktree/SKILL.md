---
name: prep-worktree
description: >-
  Always create a fresh isolated worktree from a clean, up-to-date default
  branch snapshot. Never land on the current or protected dev checkout.
disable-model-invocation: true
metadata:
  requires:
    bins: ["bash", "git"]
---

# prep-worktree

This skill always creates a fresh isolated prep worktree. It must never land on
the current checkout, even when that checkout is clean and on the default
branch. It must also never land on or mutate the user's protected development
checkout.

The user must configure their protected development checkout with an absolute
path before invoking this skill:

```bash
export PREP_WORKTREE_PROTECTED_DEV_PATH=/absolute/path/to/pristine/dev/checkout
```

The value is user configuration and must not be hardcoded in this skill. The
protected checkout must be a clean checkout of this repository on the resolved
default branch. Validate that requirement, but never pull, merge, rebase,
stash, checkout, reset, clean, or otherwise mutate it. The current checkout is
also report-only and must not be mutated.

The shell examples require Bash; run them under Bash rather than `/bin/sh`.

Existing worktrees and their in-progress operations are session-owned. Do not
reclaim a worktree by age or automatically delete anything. The only exception
is the explicit, user-confirmed cleanup flow below, which is conservative and
never force-removes a worktree.

## Workflow

```text
prep-worktree:
- [ ] 1. Validate current/protected checkouts and resolve the default branch
- [ ] 2. Refresh the default ref without changing a checkout
- [ ] 3. Enforce the configurable worktree limit and offer cleanup if needed
- [ ] 4. Create a unique isolated worktree and branch
- [ ] 5. Verify and report the handoff
```

### 1. Validate current, protected, and default

Run from the user's current directory:

```bash
CURRENT=$(git rev-parse --show-toplevel) || { echo "STOP: not a git checkout" >&2; exit 1; }
CURRENT=$(cd "$CURRENT" && pwd -P)
case "/$CURRENT/" in */prod/*) echo "STOP: production/runtime checkout" >&2; exit 1;; esac
STATUS=$(git status --porcelain=v1 --untracked-files=all)
CURRENT_BRANCH=$(git branch --show-current)
DIRTY_FILE_COUNT=$(printf '%s\n' "$STATUS" | awk 'NF {n++} END {print n+0}')

PROTECTED_DEV_PATH=${PREP_WORKTREE_PROTECTED_DEV_PATH:-}
if [ -z "$PROTECTED_DEV_PATH" ] || [ "${PROTECTED_DEV_PATH#/}" = "$PROTECTED_DEV_PATH" ]; then
  echo "STOP: set PREP_WORKTREE_PROTECTED_DEV_PATH to an absolute path" >&2
  exit 1
fi
PROTECTED_DEV_PATH=$(cd "$PROTECTED_DEV_PATH" 2>/dev/null && pwd -P) || {
  echo "STOP: protected dev checkout does not exist" >&2; exit 1;
}
case "/$PROTECTED_DEV_PATH/" in
  */prod/*) echo "STOP: protected dev checkout is under a production/runtime path" >&2; exit 1;;
esac

if git rev-parse --verify --quiet refs/remotes/origin/main >/dev/null; then
  DEFAULT=main
elif git rev-parse --verify --quiet refs/remotes/origin/master >/dev/null; then
  DEFAULT=master
elif git show-ref --verify --quiet refs/heads/main; then
  DEFAULT=main
elif git show-ref --verify --quiet refs/heads/master; then
  DEFAULT=master
else
  echo "STOP: no origin/main, origin/master, main, or master ref" >&2; exit 1
fi

PROTECTED_ROOT=$(git -C "$PROTECTED_DEV_PATH" rev-parse --show-toplevel 2>/dev/null) || {
  echo "STOP: protected path is not a git checkout" >&2; exit 1;
}
PROTECTED_ROOT=$(cd "$PROTECTED_ROOT" && pwd -P)
test "$PROTECTED_ROOT" = "$PROTECTED_DEV_PATH" || {
  echo "STOP: protected path must be the checkout root, not a subdirectory" >&2; exit 1;
}
resolve_common_dir() {
  local checkout="$1" common_dir
  common_dir=$(git -C "$checkout" rev-parse --git-common-dir) || return 1
  case "$common_dir" in
    /*) cd "$common_dir" && pwd -P ;;
    *) cd "$checkout/$common_dir" && pwd -P ;;
  esac
}
CURRENT_COMMON_DIR=$(resolve_common_dir "$CURRENT") || exit 1
PROTECTED_COMMON_DIR=$(resolve_common_dir "$PROTECTED_DEV_PATH") || exit 1
test "$CURRENT_COMMON_DIR" = "$PROTECTED_COMMON_DIR" || {
  echo "STOP: protected dev checkout belongs to a different repository" >&2; exit 1;
}
PROTECTED_BRANCH=$(git -C "$PROTECTED_DEV_PATH" branch --show-current)
test "$PROTECTED_BRANCH" = "$DEFAULT" || {
  echo "STOP: protected dev checkout must be on $DEFAULT, found ${PROTECTED_BRANCH:-detached HEAD}" >&2; exit 1;
}
PROTECTED_STATUS=$(git -C "$PROTECTED_DEV_PATH" status --porcelain=v1 --untracked-files=all --ignored) || {
  echo "STOP: could not inspect protected dev checkout" >&2; exit 1;
}
test -z "$PROTECTED_STATUS" || {
  echo "STOP: protected dev checkout is not clean" >&2; exit 1;
}
for operation_marker in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG rebase-apply rebase-merge sequencer; do
  operation_path=$(git -C "$PROTECTED_DEV_PATH" rev-parse --git-path "$operation_marker") || exit 1
  test ! -e "$operation_path" || {
    echo "STOP: protected dev checkout has an in-progress Git operation" >&2; exit 1;
  }
done
```

The current branch and dirty set are report-only. A divergent local branch does
not block prep and never justifies changing the current checkout.

### 2. Refresh the default ref without changing a checkout

Do not run `git worktree prune`. If `origin` exists, fetch exactly the selected
default branch and use its refreshed remote-tracking ref:

```bash
if git remote get-url origin >/dev/null 2>&1; then
  git fetch --no-tags origin "$DEFAULT" || {
    echo "STOP: could not refresh origin/$DEFAULT; no worktree created" >&2; exit 1;
  }
  BASE="refs/remotes/origin/$DEFAULT"
else
  BASE="$DEFAULT"
fi
BASE_SHA=$(git rev-parse "$BASE") || { echo "STOP: landing base disappeared" >&2; exit 1; }
```

Fetch may update shared repository refs, but it must not change any checkout's
files, branch, or working tree. On a Git metadata lock failure, retry once at
most; never poll or remove a lock file.

### 3. Enforce the worktree limit and offer cleanup

`PREP_WORKTREE_MAX` is configurable and defaults to `20`. Count every
registered worktree, including the protected and current checkouts. Check at
`>=` so creating the new worktree cannot exceed the limit:

```bash
WORKTREE_MAX=${PREP_WORKTREE_MAX:-20}
case "$WORKTREE_MAX" in ''|*[!0-9]*|0) echo "STOP: PREP_WORKTREE_MAX must be a positive integer" >&2; exit 1;; esac
LOCK_DIR="$CURRENT_COMMON_DIR/prep-worktree.lock"
LOCK_ACQUIRED=0
cleanup_lock() {
  [ "$LOCK_ACQUIRED" = 1 ] || return 0
  if [ -f "$LOCK_DIR/pid" ] && [ "$(cat "$LOCK_DIR/pid" 2>/dev/null)" != "$$" ]; then
    return 0
  fi
  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup_lock EXIT
mkdir "$LOCK_DIR" 2>/dev/null || {
  echo "STOP: another prep-worktree session holds the repository lock" >&2; exit 1;
}
LOCK_ACQUIRED=1
printf '%s\n' "$$" > "$LOCK_DIR/pid" || {
  echo "STOP: could not record the repository lock owner" >&2; exit 1;
}
WORKTREE_LIST=$(git worktree list --porcelain) || {
  echo "STOP: could not enumerate registered worktrees" >&2; exit 1;
}
WORKTREE_COUNT=$(printf '%s\n' "$WORKTREE_LIST" | awk '$1 == "worktree" {n++} END {print n+0}')
```

Before counting, cleanup, or creating, acquire a repository-scoped coordination
lock. Use an atomic `mkdir` under `$CURRENT_COMMON_DIR` and release it with an
`EXIT` trap. If the lock already exists, stop and ask the user to retry after
the other prep session finishes. Record the owner PID only after `mkdir`
succeeds. Never automatically remove or reclaim a lock: if the user believes it
is stale, verify the recorded PID is no longer alive and obtain explicit
confirmation before removing only that lock directory. If the PID is missing or
invalid, require manual inspection and confirmation; never infer that the lock
is stale. Hold the lock
through user confirmation, candidate revalidation, cleanup, recount, and
`git worktree add`. This prevents concurrent invocations of this skill from
exceeding the limit or deleting a path approved by another session.

If the count is below the limit, continue. Otherwise, stop before creation and
inspect registered paths only to produce a cleanup report. This is the one
deliberate exception to the normal no-age-selection rule, requested by the user
for this limit flow.

An eligible cleanup candidate must:

- exist and be neither `CURRENT` nor `PROTECTED_DEV_PATH`;
- not be equal to or contained by either checkout after canonicalization;
- not be marked `locked` in `git worktree list --porcelain`;
- have no tracked, untracked, or ignored files (`git status --porcelain=v1
  --untracked-files=all --ignored` must be empty); and
- have filesystem access-time evidence at least 48 hours old.

Use `stat -c %X` on GNU/Linux or `stat -f %a` on BSD/macOS. Access time is a
heuristic, not proof of inactivity: `noatime` and `relatime` mounts can make it
inaccurate. List each candidate with its branch and “last observed access”, and
also explain excluded dirty or locked worktrees.

Ask the user in the conversation whether to remove the listed candidates. Do
not use shell `read`, assume consent, or silently continue. If the user
declines, stop without creating a worktree. If the user agrees, remove only the
explicitly listed paths using:

```bash
git worktree remove -- "$CANDIDATE_PATH"
```

Before each removal, while still holding the coordination lock, re-enumerate
the worktree and verify that its canonical path, branch, HEAD, lock state,
clean/ignored status, and explicit approval record still match the candidate
shown to the user. If any value changed, do not remove it; report it as changed.
Reject a candidate if it contains or is contained by the current checkout,
protected checkout, or any other registered worktree. Never remove by a path
that was not revalidated.

Never use `--force`, `rm -rf`, `git worktree prune`, or automatic branch
deletion. If removal refuses a path, leave it in place and report it. Re-count
after cleanup and continue only if the count is below `WORKTREE_MAX`; otherwise
stop and report that the limit remains reached. Existing branches are preserved.

### 4. Create a unique isolated worktree and branch

Reserve a never-before-used empty sibling directory. Keep the reservation in
place through `git worktree add`; do not remove it first, because another
process could replace the empty path with a symlink during that gap. If the
repository parent
is not writable, use `${TMPDIR:-/tmp}`. Never reuse an existing path:

```bash
REPO_PARENT=$(dirname "$CURRENT")
REPO_NAME=$(basename "$CURRENT")
if ! WT_PATH=$(mktemp -d "$REPO_PARENT/.${REPO_NAME}-prep.XXXXXX" 2>/dev/null); then
  TMP_PARENT=${TMPDIR:-/tmp}
  case "$TMP_PARENT" in /*) ;; *) echo "STOP: TMPDIR must be absolute" >&2; exit 1;; esac
  TMP_PARENT=$(cd "$TMP_PARENT" 2>/dev/null && pwd -P) || {
    echo "STOP: TMPDIR is not accessible" >&2; exit 1;
  }
  WT_PATH=$(mktemp -d "$TMP_PARENT/${REPO_NAME}-prep.XXXXXX") || {
    echo "STOP: could not reserve an isolated worktree path" >&2; exit 1;
  }
fi
test ! -L "$WT_PATH" || { echo "STOP: reserved path is a symlink" >&2; exit 1; }
path_is_within() {
  [ "$1" = "/" ] && return 0
  case "$2/" in "$1/"*) return 0;; esac
  return 1
}
if path_is_within "$CURRENT" "$WT_PATH" || path_is_within "$PROTECTED_DEV_PATH" "$WT_PATH"; then
  echo "STOP: landing path is inside a protected checkout; isolation violated" >&2
  exit 1
fi
if path_is_within "$CURRENT_COMMON_DIR" "$WT_PATH"; then
  echo "STOP: landing path is inside the shared Git directory" >&2
  exit 1
fi
while IFS= read -r registered_path; do
  test -n "$registered_path" || continue
  registered_path=$(cd "$registered_path" 2>/dev/null && pwd -P) || {
    echo "STOP: could not canonicalize a registered worktree path" >&2; exit 1;
  }
  if path_is_within "$registered_path" "$WT_PATH"; then
    echo "STOP: landing path is inside another registered worktree" >&2
    exit 1
  fi
done < <(printf '%s\n' "$WORKTREE_LIST" | sed -n 's/^worktree //p')
WT_NAME=$(basename "$WT_PATH")
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BRANCH="prep-worktree/$DEFAULT-$STAMP-${WT_NAME##*.}"
git worktree add -b "$BRANCH" "$WT_PATH" "$BASE_SHA" || {
  echo "STOP: git could not create the isolated worktree" >&2
  echo "requested path: $WT_PATH" >&2; echo "requested branch: $BRANCH" >&2; exit 1;
}
```

`git worktree add` is the only registration operation. After it succeeds,
canonicalize the registered path from `git worktree list --porcelain` and verify
it is exactly `$WT_PATH` and remains outside the current/protected roots, every
other registered worktree, and `$CURRENT_COMMON_DIR`. If it partially registers
a path or this verification fails, report it for manual recovery; do not repair
another checkout.

### 5. Verify and report

Verify that `git -C "$WT_PATH" branch --show-current` equals `$BRANCH`, its
`HEAD` equals `$BASE_SHA`, and its status including ignored files is empty. On failure, stop
and report without touching another checkout.

Report:

- `LANDING`: the absolute `$WT_PATH`.
- `BRANCH`: the isolated `prep-worktree/...` branch and `$BASE_SHA`.
- `CURRENT`: original path, branch, and dirty-file count, unchanged.
- `PROTECTED DEV CHECKOUT`: configured path, branch, and clean validation.
- `WORKTREE COUNT`: count after approved cleanup and configured maximum.
- `OTHER WORKTREES`: not modified; stale registrations were not pruned.
- `NEXT`: start in `$WT_PATH`; do not checkout `$DEFAULT` there.

The prep branch is session-owned. Remove its worktree and branch only in a
separate explicit cleanup operation after its work has been committed or
otherwise preserved.
