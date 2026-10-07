---
name: smart-commit-to-pr
description: >-
  Commit current work, push, and open or update a GitHub PR from the current
  checkout without modifying other worktrees.
disable-model-invocation: true
metadata:
  requires:
    bins: ["git", "gh"]
---

# smart-commit-to-pr

Invocation permits fetch, creating or switching a feature branch in the
current checkout, commit, and push. Return the PR URL. Every other worktree is
owned by another session: do not inspect, checkout, switch, stash, reset,
clean, delete, or repair it.

## When invoked

Copy and track:

```text
smart-commit-to-pr:
- [ ] 1. Preconditions
- [ ] 2. Fetch + classify branch (BASE, LIVE, or MERGED)
- [ ] 3. Ensure a feature branch in this checkout
- [ ] 4. Commit (skip if nothing to commit)
- [ ] 5. Push + open or reuse PR
- [ ] 6. Verify and return the PR URL
```

## 1. Preconditions

```bash
git rev-parse --show-toplevel
git status -sb
git branch --show-current    # empty => detached HEAD
git remote
```

- Abort if not a git repo, no `origin`, or `gh` is missing.
- **Prod:** if the toplevel path has a component exactly `prod` (e.g.
  `.../prod/<repo>`), **stop** — use the development checkout.
- **Detached HEAD:** **stop** and ask which branch to use.
- **Secrets:** if the dirty set matches `.env`, `*.env`, `.env.*`, `id_rsa`,
  `id_ed25519`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `credentials*`,
  `secrets.*`, `*.keystore`, `*.jks`, **stop** and list the paths.

Resolve **`$DEFAULT`**:

1. `git rev-parse --verify --quiet origin/main` → `main`
2. else `git rev-parse --verify --quiet origin/master` → `master`
3. else **stop** and ask. Only `main` or `master`.

## 2. Fetch + classify branch

Refresh once. If fetch fails, continue only when the required
`origin/$DEFAULT` ref still exists; report that the classification used the
existing ref. Do not retry indefinitely.

```bash
git fetch origin || printf 'FETCH_FAILED_USING_EXISTING_REFS\n' >&2
CURRENT=$(git branch --show-current)
DEFAULT_REF="origin/$DEFAULT"
git rev-parse --verify --quiet "refs/remotes/$DEFAULT_REF" >/dev/null || {
  echo "STOP: origin/$DEFAULT is unavailable" >&2
  exit 1
}
```

Classify — first match wins:

| # | Condition | Class |
|---|---|---|
| 1 | `$CURRENT` is `$DEFAULT` or starts with `prep-worktree/` | **BASE** |
| 2 | `gh pr view --json state -q .state` is `MERGED` | **MERGED** |
| 3 | `git merge-base --is-ancestor HEAD origin/$DEFAULT` | **MERGED** |
| 4 | otherwise | **LIVE** |

`gh pr view` with no PR → treat as no GitHub PR. A `prep-worktree/...` branch
is a session base branch, not a PR head; it must be converted to a
`feature/...` branch before pushing.

Record:

```bash
DIRTY=$(git status --porcelain=v1)
UNIQUE=$(git rev-list --count "origin/$DEFAULT..HEAD")
```

**Has work** if any of:

- `DIRTY` is non-empty.
- **LIVE** with `UNIQUE > 0`.
- **BASE** with `UNIQUE > 0`.

**Already done:** LIVE, clean tree, `HEAD` matches `origin/$CURRENT` (already
pushed), and an OPEN or DRAFT PR exists for this head → skip to step 6 and
return that PR URL.

**Nothing to land:** no work and no OPEN/DRAFT PR to return → **stop**. Say the
branch is already in `$DEFAULT` or has no new work and there is nothing to PR.

## 3. Ensure a feature branch in this checkout

First derive a free branch name from the session goal (chat title, user's
stated goal, or a one-line summary of the dirty diff). Lowercase, hyphens, max
about 50 characters. If the goal is unclear, **stop and ask** — do not use
`feature/update`.

```bash
SLUG="<kebab-from-goal>"
BRANCH="feature/$SLUG"
n=2
while git rev-parse --verify --quiet "refs/heads/$BRANCH" \
   || git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; do
  BRANCH="feature/${SLUG}-$n"
  n=$((n+1))
done
```

### LIVE

Keep `$CURRENT`. Do not rename it, merge `$DEFAULT`, or inspect another
worktree.

### BASE: current `$DEFAULT` or `prep-worktree/*`

Preserve current-worktree commits and files. The branch choice depends on
whether this checkout already contains commits beyond `origin/$DEFAULT`:

```bash
if [ "$UNIQUE" -gt 0 ]; then
  # Carries implementation commits and any dirty files from this checkout.
  git checkout -b "$BRANCH"
else
  # The base has no unique commits. Refresh the branch point, carrying only
  # this checkout's dirty files forward.
  STASHED=0
  if [ -n "$DIRTY" ]; then
    git stash push -u -m "smart-commit-to-pr current checkout" || {
      echo "STOP: could not stash current-checkout changes" >&2
      exit 1
    }
    STASHED=1
  fi
  git checkout -b "$BRANCH" "origin/$DEFAULT" || {
    echo "STOP: could not create $BRANCH from origin/$DEFAULT" >&2
    exit 1
  }
  if [ "$STASHED" -eq 1 ]; then
    git stash pop || {
      echo "STOP: stash conflict while restoring current-checkout changes" >&2
      git status -sb
      exit 1
    }
  fi
fi
```

This is the normal handoff from `prep-worktree`: the isolated prep branch is
never pushed as a PR head. The branch switch above changes only the current
checkout.

### MERGED

Do not re-PR squash leftovers from the merged branch. Preserve dirty files in
this checkout, but branch from refreshed `$DEFAULT`:

```bash
STASHED=0
if [ -n "$DIRTY" ]; then
  git stash push -u -m "smart-commit-to-pr current checkout" || {
    echo "STOP: could not stash current-checkout changes" >&2
    exit 1
  }
  STASHED=1
fi
git checkout -b "$BRANCH" "origin/$DEFAULT" || {
  echo "STOP: could not create $BRANCH from origin/$DEFAULT" >&2
  exit 1
}
if [ "$STASHED" -eq 1 ]; then
  git stash pop || {
    echo "STOP: stash conflict while restoring current-checkout changes" >&2
    git status -sb
    exit 1
  }
fi
```

## 4. Commit

If the tree is clean, skip — do not create an empty commit.

Otherwise follow the repo commit protocol: `git status`, `git diff`, and `git
log` in parallel; stage only relevant files; commit via HEREDOC.

- Message: 1–2 sentences, why over what; match recent `git log` style.
- Never `--no-verify` / `--no-gpg-sign`. Never commit secrets.
- After `git add`, re-scan staged paths for the secrets patterns in step 1; if
  any match, `git reset` and **stop**.
- If a hook rejects the commit, fix and make a **new** commit (do not amend
  unless the user asked and the commit has not been pushed).

## 5. Push + open or reuse PR

```bash
git push -u origin HEAD
```

If push is rejected (non-fast-forward), **stop** and report. Do not
force-push.

Reuse an existing **open or draft** PR for this head:

```bash
gh pr view --json url,number,state
```

- `OPEN` or `DRAFT` → that PR **is** the PR. Push already added the commits.
  Do not open a second PR.
- No PR, or state is `CLOSED`/`MERGED` → create one:

```bash
gh pr create --title "<concise title>" --body "$(cat <<'EOF'
## Summary
- <1-3 bullets of why/what>

## Test plan
- [ ] <checks>

EOF
)"
```

Title from the session goal / commit subject. Capture the URL from `gh pr
create` output.

## 6. Verify and return the PR URL

```bash
gh pr view --json url,state,headRefName
```

Done only when **all** are true:

- `headRefName` equals the current branch.
- `state` is `OPEN` or `DRAFT`.
- `url` is a non-empty `https://github.com/...` PR link.

Lead the final reply with that URL, then:

1. Branch name
2. New PR vs existing PR updated
3. Short SHA of `HEAD`

## Hard rules

- Never open a PR whose head is `$DEFAULT` or `prep-worktree/*`.
- Never force-update `$DEFAULT`; never rename or delete another worktree's
  branch.
- Never squash-merge, delete branches, or refresh local `$DEFAULT` (that is
  `smart-push-to-prod`).
- Never force-push, rebase, or `git reset --hard`.
