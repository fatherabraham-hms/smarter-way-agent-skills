---
name: smart-commit-to-pr
description: >-
  Commit current work, push, and open or update a GitHub PR. On an unmerged
  feature branch, keep that branch and reuse its open PR. On main/master or a
  merged branch, cut a fresh feature branch from the default branch named for
  the session goal. Use when the user says smart-commit-to-pr, commit to PR,
  open a PR, or wants the PR link for this session's work.
disable-model-invocation: true
metadata:
  requires:
    bins: ["git", "gh"]
---

# smart-commit-to-pr

Invocation permits fetch, creating or switching a feature branch, commit, and
push, including leaving `main`/`master`. Return the PR URL.

## When invoked

Copy and track:

```text
smart-commit-to-pr:
- [ ] 1. Preconditions
- [ ] 2. Fetch + classify branch (LIVE vs MERGED)
- [ ] 3. Ensure feature branch
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

```bash
git fetch origin || true
CURRENT=$(git branch --show-current)
```

Classify **LIVE** vs **MERGED** — first match wins:

| # | Condition | Class |
|---|-----------|--------|
| 1 | `$CURRENT` is `$DEFAULT` | **MERGED** |
| 2 | `gh pr view --json state -q .state` is `MERGED` | **MERGED** |
| 3 | `git merge-base --is-ancestor HEAD origin/$DEFAULT` | **MERGED** |
| 4 | otherwise | **LIVE** |

`gh pr view` with no PR → treat as no GitHub PR (do not fail the run).

Record dirty (`git status --porcelain=v1` non-empty) and unique commit count
(`git rev-list --count origin/$DEFAULT..HEAD`).

**Has work** if any of: dirty tree; LIVE with unique commits > 0; `$CURRENT` is
`$DEFAULT` with unique commits > 0.

**Already done:** LIVE, clean tree, `HEAD` matches `origin/$CURRENT` (already
pushed), and an OPEN or DRAFT PR exists for this head → skip to step 6 and
return that PR URL.

**Nothing to land:** not has-work, and no OPEN/DRAFT PR to return → **stop**.
Say the branch is already in `$DEFAULT` (or has no new work) and there is
nothing to PR.

## 3. Ensure feature branch

### LIVE

Keep `$CURRENT`. Do not rename. Do not merge `$DEFAULT`.

### MERGED

Need a free `feature/<slug>` from the session goal (chat title, user's stated
goal, or a one-line summary of the dirty diff). Lowercase, hyphens, max ~50
chars. If the goal is unclear, **stop and ask** — do not use `feature/update`.

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

Then **one** of these (do not mix):

**On `$DEFAULT`** (unique commits and/or dirty files come along):

```bash
git pull --ff-only origin $DEFAULT    # stop on failure; do not rebase or merge
git checkout -b "$BRANCH"
git branch --force "$DEFAULT" origin/$DEFAULT   # only while on $BRANCH
```

**On a merged feature** (do not re-PR squash leftovers). Branch from
`origin/$DEFAULT`:

```bash
git stash push -u -m "smart-commit-to-pr"   # skip if clean
git checkout -b "$BRANCH" origin/$DEFAULT
git stash pop                              # skip if no stash; on conflict, stop and list files
```

## 4. Commit

If the tree is clean, skip — do not create an empty commit.

Otherwise follow the repo commit protocol: `git status`, `git diff`, and
`git log` in parallel; stage only relevant files; commit via HEREDOC.

- Message: 1–2 sentences, why over what; match recent `git log` style.
- Never `--no-verify` / `--no-gpg-sign`. Never commit secrets.
- After `git add`, re-scan staged paths for the secrets patterns in step 1;
  if any match, `git reset` and **stop**.
- If a hook rejects the commit, fix and make a **new** commit (do not amend
  unless the user asked and the commit has not been pushed).

## 5. Push + open or reuse PR

```bash
git push -u origin HEAD
```

If push is rejected (non-fast-forward), **stop** and report. Do not force-push.

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

Title from the session goal / commit subject. Capture the URL from `gh pr create`
output.

## 6. Verify and return the PR URL

```bash
gh pr view --json url,state,headRefName
```

Done only when **all** are true:

- `headRefName` equals the current branch
- `state` is `OPEN` or `DRAFT`
- `url` is a non-empty `https://github.com/...` PR link

Lead the final reply with that URL, then:

1. Branch name
2. New PR vs existing PR updated
3. Short SHA of `HEAD`

## Hard rules

- Never open a PR whose head is `$DEFAULT`.
- Never squash-merge, delete branches, or refresh local `$DEFAULT` (that is
  `smart-push-to-prod`).
- Never force-push, rebase, or `git reset --hard`.
