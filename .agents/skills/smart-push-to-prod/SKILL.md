---
name: smart-push-to-prod
description: >-
  Commit, push, open a PR, squash-merge to the default branch, then refresh
  local main/master. When SMART_PUSH_PROD_PATH maps this repo, also
  fast-forward that prod checkout. Use when the user says smart-push-to-prod,
  push to prod, ship this, or wants the usual branch→PR→squash→main pull
  after an update.
disable-model-invocation: true
metadata:
  requires:
    bins: ["git", "gh"]
---

# smart-push-to-prod

Ship changes in the **current repo** to GitHub `main`/`master` via PR and
squash-merge, then fast-forward the local default branch. Works in any project
with a git remote and GitHub CLI.

## When invoked

User wants the full ship loop after an update. Treat invocation as explicit
permission to commit, push, open a PR, and (after the review gate below)
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

Resolve **`$PROD`** from `SMART_PUSH_PROD_PATH` (see below). If the
current toplevel is a mapped prod checkout, **stop** and name the paired
develop path.

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
variable):

```bash
TOPLEVEL=$(git rev-parse --show-toplevel)
MAP=$(bash -lc 'printf "%s" "${SMART_PUSH_PROD_PATH-}"')
```

Canonicalize with `realpath`. Match `$TOPLEVEL` to one side of a pair:

- Equals a **prod** path → stop. Report the paired develop path.
- Equals a **develop** path → `$PROD` is that prod path. Confirm it is a git
  checkout (`git -C "$PROD" rev-parse --show-toplevel`).
- No match → `$PROD` empty.

Done when `$PROD` is empty or a git toplevel, and the current toplevel is not
a mapped prod path.

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

- Prefer squash. Do not use merge commits or rebase-merge unless the user
  overrides.
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

Done when this repo's `$DEFAULT` matches `origin/$DEFAULT`, and — if `$PROD`
was set — that checkout does too. A failed prod pull stops the step; report
it. Leave the prod checkout otherwise untouched.

## Final reply

Short:

1. Branch name
2. PR URL (and whether it was reviewed first)
3. Merge result
4. Local `$DEFAULT` pull result (`ff-only` OK or error)
5. Prod pull result when `$PROD` was set (path + `ff-only` OK or error)

## Out of scope

- Force push, hard reset, `git push --force` to `$DEFAULT`
- Committing, branching, or pushing in a prod checkout named by
  `SMART_PUSH_PROD_PATH`
- Amending pushed commits unless the user explicitly requests and commit rules
  allow
- Skipping the review-gate question
