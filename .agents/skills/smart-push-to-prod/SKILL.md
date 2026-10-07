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
    bins: ["git", "gh", "python3"]
---

# smart-push-to-prod

Invocation permits commit, push, opening a PR, and, after the review gate,
squash-merge.

## Scripted terminal work

Set `$SCRIPT` before the workflow. The default path is the installed skill;
override it when this checkout is using another skill installation:

```bash
SCRIPT="${SMART_PUSH_SCRIPT:-$HOME/.agents/skills/smart-push-to-prod/scripts/smart_push_git.py}"
if [ ! -f "$SCRIPT" ]; then
  SCRIPT="$HOME/.local/share/agent-skills/installed/smart-push-to-prod/scripts/smart_push_git.py"
fi
python3 "$SCRIPT" preflight
python3 "$SCRIPT" branch-sync --branch "feature/<kebab-slug>"
python3 "$SCRIPT" refresh --pr-url "$PR_URL"
```

Use the helper for deterministic git work; it emits one compact JSON result and
keeps the review, commit-content, and merge decisions visible to the agent.
The helper never stages, commits, pushes, or merges a PR. A nonzero exit stops
the current step unless the result explicitly identifies a nonfatal local
default-branch pull failure.

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
python3 "$SCRIPT" preflight
```

- Abort if the helper reports a nonzero exit, no `origin`, or no default ref.
- Treat filename- or content-based `secret_paths` in its JSON result as a hard
  stop and list those paths.
- Abort if there is nothing to commit **and** nothing already committed on the
  feature branch that still needs a PR/merge (say so and stop).
- Do not commit secrets. The helper reports `toplevel`, `branch`, `default`,
  `prod`, `dirty`, and `secret_paths`; retain those values for later steps.

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

The helper reads an inherited mapping first, then parses a static assignment in
the documented `~/.bashrc` fallback without executing shell startup code, and
matches repository identity across the primary
checkout and linked worktrees. It stops for a mapped prod checkout, multiple
develop-side matches, an invalid mapping, or a missing prod git checkout. Use
its `prod` result as the only prod path.

### 2. Branch sync / create

Choose the feature slug from the session goal. The preflight result supplies
the current branch and `$DEFAULT`.

**If current branch is `$DEFAULT` (or equals `origin/$DEFAULT` and you are on `$DEFAULT`):**

1. Prefer chat/session title + short change summary.
2. Format: `feature/<kebab-slug>` (lowercase, hyphens, max ~60 chars).
3. Run `python3 "$SCRIPT" branch-sync --branch "feature/<kebab-slug>"`.

**If current branch is not `$DEFAULT`:**

1. Run `python3 "$SCRIPT" branch-sync` to fetch and merge `origin/$DEFAULT`.
2. Keep the branch; do not rename it.

The helper stops on fetch, fast-forward pull, branch creation, or merge
conflicts. It never rebases, resets, or force-updates a branch.

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

Capture the PR URL as `$PR_URL`.

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
- If the command fails or merge is blocked (checks, reviews), report status and
  stop before pulling any checkout.

### 7. Refresh local default branch

Run the helper only after the squash merge command succeeds:

```bash
python3 "$SCRIPT" refresh --pr-url "$PR_URL"
```

The helper first confirms that the PR belongs to this repository, targets
`$DEFAULT`, and has `state: MERGED` with non-empty `mergedAt` and
`mergeCommit`; otherwise it refreshes neither checkout. It refreshes the
worktree that owns `$DEFAULT`, leaving a linked feature worktree untouched,
and refuses to refresh a dirty local default worktree. Tracked prod changes
also stop the workflow; existing untracked prod files are preserved. It
attempts the local `git pull --ff-only` and continues to prod when that local
pull fails. The mapped prod checkout must already be on `$DEFAULT` and is
pulled only after the merge confirmation. A failed prod pull stops the
workflow and must be reported. The JSON result includes both pull outcomes and
both status summaries. Leave both checkouts otherwise untouched.

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
