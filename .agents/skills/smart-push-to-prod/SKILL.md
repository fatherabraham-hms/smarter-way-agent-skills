---
name: smart-push-to-prod
description: >-
  Commit, push, open a PR, squash-merge to the default branch, then refresh
  local main/master. When SMART_PUSH_PROD_PATH maps this repository,
  including a linked worktree of that develop checkout, also fast-forward
  that prod checkout. Use when the user says smart-push-to-prod,
  push to prod, ship this, or wants the usual branch→PR→squash→main pull
  after an update.
disable-model-invocation: true
metadata:
  requires:
    bins: ["git", "gh"]
---

# smart-push-to-prod

Invocation permits commit, push, opening a PR, and, after the review gate,
squash-merge.

## Workflow

Copy and track:

```text
smart-push-to-prod:
- [ ] 1. Preconditions
- [ ] 2. Branch sync / create
- [ ] 3. Commit
- [ ] 4. Push + create PR
- [ ] 5. Review gate (ask user)
- [ ] 6. Squash-merge (after gate)
- [ ] 7. Refresh local default branch (+ mapped prod checkout)
```

### 1. Preconditions

In the current repo (workspace root):

```bash
git rev-parse --show-toplevel
git status -sb
git remote
```

- Abort if not a git repo or no remote.
- Abort if there is nothing to commit **and** nothing already committed on the
  feature branch that still needs a PR/merge (say so and stop).
- Do not commit secrets (`.env`, credentials, private keys).

Resolve **default branch `$DEFAULT`**:

1. `git rev-parse --verify --quiet origin/main` → `$DEFAULT=main`
2. else `git rev-parse --verify --quiet origin/master` → `$DEFAULT=master`
3. else **stop** and ask which branch is default.

Resolve **`$PROD`** from `SMART_PUSH_PROD_PATH` (see below). Match the
repository, not the current worktree path. If this repo is a mapped prod
checkout, **stop** and name the paired develop path.

### Prod checkout (`SMART_PUSH_PROD_PATH`)

Optional. Unset means this repo has no separate prod checkout: `$PROD` stays
empty and step 7 only refreshes the repo you are in.

The value is an environment variable, not a path in this skill. Set it in
`~/.bashrc` **above** the interactive-only return so a login shell exports it:

```bash
export SMART_PUSH_PROD_PATH="<develop-toplevel>=<prod-toplevel>"
```

Several pairs join with `;`. Both sides are absolute paths. Skip a pair whose
two paths are the same checkout.

Resolve through a login shell (the agent process may not have inherited the
variable). Identity is the shared git dir:

```bash
TOPLEVEL=$(realpath "$(git rev-parse --show-toplevel)")
MAIN=$(realpath "$(git worktree list --porcelain | sed -n 's/^worktree //p' | head -n 1)")
COMMON=$(realpath "$(git rev-parse --path-format=absolute --git-common-dir)")
MAP=$(bash -lc 'printf "%s" "${SMART_PUSH_PROD_PATH-}"')
```

`$MAIN` is the primary checkout. A linked worktree's `$TOPLEVEL` differs; both
are this repo.

Split `$MAP` on `;`, then each pair on the first `=`. `realpath` both sides.
A side's repo id is `realpath` of `git -C <side> rev-parse --path-format=absolute --git-common-dir`.

This repo **is the develop side** of a pair when that side's repo id equals
`$COMMON`, or that side's realpath equals `$TOPLEVEL` or `$MAIN`. It **is the
prod side** when the prod side matches the same way.

- Prod side → **stop**. Report the paired develop path.
- One develop side → `$PROD` is that prod path. Confirm
  `git -C "$PROD" rev-parse --show-toplevel`.
- Several develop sides → **stop** and name them.
- No develop side → `$PROD` empty. Say that no pair maps this repository.

Done when `$PROD` is empty or a git toplevel other than this repo, and this
repo is not a mapped prod checkout.

### 2. Branch sync / create

```bash
git fetch origin
git branch --show-current
git rev-parse HEAD origin/$DEFAULT
```

**If current branch is `$DEFAULT` (or equals `origin/$DEFAULT` and you are on `$DEFAULT`):**

1. Confirm local default is current: `git pull --ff-only origin $DEFAULT`.
2. Create a feature branch from session context:
   - Prefer chat/session title + short change summary.
   - Format: `feature/<kebab-slug>` (lowercase, hyphens, max ~60 chars).
   - Example: session “dashboard recs UI” → `feature/dashboard-recs-ui`.
3. `git checkout -b feature/<kebab-slug>`

**If current branch is not `$DEFAULT`:**

1. Keep the branch.
2. Ensure it includes latest `$DEFAULT`:
   ```bash
   git merge origin/$DEFAULT
   ```
   - No interactive rebase.
   - If merge conflicts: stop, report files, do not force through.
3. Do **not** rename the branch unless the user asks.

### 3. Commit

Follow the repo commit protocol (status + diff + log in parallel, then stage,
commit via HEREDOC, verify status).

- Message: 1–2 sentences, why over what; match recent `git log` style.
- Only stage relevant files; never `--no-verify`.
- If hook fails: fix and make a **new** commit (do not amend unless commit
  rules allow).

If everything needed is already committed on the feature branch, skip creating
an empty commit.

### 4. Push + create PR

```bash
git push -u origin HEAD
```

If no open PR for this branch:

```bash
gh pr create --title "<concise title>" --body "$(cat <<'EOF'
## Summary
- <1-3 bullets of why/what>

## Test plan
- [ ] <checks>

EOF
)"
```

If a PR already exists for the branch, reuse it
(`gh pr view --json url,number,state`).

Capture the PR URL.

### 5. Review gate (required)

Ask the user exactly:

> Want the PR link to review before squash-merge? (yes/no)

- **yes** — reply with the PR URL only (plus one short line that you are
  waiting). **Stop.** Do not merge until the user says to proceed / squash /
  merge / LGTM (or equivalent).
- **no** — continue to step 6 immediately.

Do not skip this question.

### 6. Squash-merge

Only after step 5 allows it:

```bash
gh pr merge --squash --delete-branch
```

- Do not use merge commits or rebase-merge unless the user overrides.
- Never force-push `$DEFAULT`.
- If merge is blocked (checks, reviews): report status and stop.

### 7. Refresh local default branch

```bash
git checkout $DEFAULT
git pull --ff-only origin $DEFAULT
git status -sb
```

If `git pull --ff-only` fails, **stop** and report — do not rebase or merge.

When `$PROD` is set, fast-forward that checkout to the same branch. Pull only:

```bash
git -C "$PROD" pull --ff-only origin "$DEFAULT"
git -C "$PROD" status -sb
```

Done when this repo's `$DEFAULT` matches `origin/$DEFAULT` and, when `$PROD`
is set, that checkout does too. A failed prod pull stops the step; report it.
Leave the prod checkout otherwise untouched.

## Final reply

1. Branch name
2. PR URL (and whether it was reviewed first)
3. Merge result
4. Local `$DEFAULT` pull result (`ff-only` OK or error)
5. Prod pull result: path + `ff-only` OK or error, or that no pair maps this repository

## Out of scope

- Force push, hard reset, `git push --force` to `$DEFAULT`
- Amending pushed commits unless the user explicitly requests and commit rules
  allow
