---
name: cleanup-branch-noise
description: >-
  Clean up current-branch noise at session start: detect merge into main/master,
  discard discardable output leftovers, stop on significant code changes with
  clickable file links, or park unclear work on a CLEANUP- branch then return to
  a fresh default branch. Use when the user says cleanup-branch-noise, clean up
  branch noise, clean session start, start clean, park branch noise, or wants a
  clean main/master before new work.
disable-model-invocation: true
metadata:
  openclaw:
    requires:
      bins: ["git"]
---

# cleanup-branch-noise

Clean up current-branch noise when starting a new session. Prefer moving forward
without interrupting flow: discard obvious output leftovers, stop only when
significant coding changes need a human look, otherwise park unclear work on a
`CLEANUP-` branch and return to a fresh default branch.

## When invoked

Treat invocation as **explicit permission** to fetch, discard discardable
uncommitted files, create/switch branches, commit, and push — including leaving
the current branch for `main`/`master`. This overrides the usual “do not switch
branches unless asked” rule for this run only.

## Production vs development checkouts

Do not run this skill in a production or runtime clone. If the git toplevel
has a path component exactly `prod` (for example `.../prod/<repo>`), **stop**
and tell the user to use the development checkout used for branches and PRs.
Never commit, push, or check out branches in prod.

## Workflow

Copy and track:

```text
cleanup-branch-noise:
- [ ] 1. Preconditions + default branch
- [ ] 2. Fetch + merge check
- [ ] 3. Classify uncommitted files
- [ ] 4. Act (discard / stop / CLEANUP-)
- [ ] 5. Land on fresh default branch (when proceeding)
```

### 1. Preconditions + default branch

```bash
git rev-parse --show-toplevel   # abort if not a git repo
git status -sb
git branch --show-current        # empty output => detached HEAD (see below)
git remote                       # may be empty => no remote (see below)
```

Resolve **default branch `$DEFAULT`** offline-first, in this order:

1. `git rev-parse --verify --quiet origin/main` succeeds → `$DEFAULT=main`
2. else `git rev-parse --verify --quiet origin/master` succeeds → `$DEFAULT=master`
3. else if a remote exists, `git remote set-head origin -a` (auto) then read
   `git rev-parse --verify origin/HEAD` and derive the name; if that fails, **stop**
   and ask the user which branch is default.
4. else (no remote) use local `main` if it exists, else `master`, else **stop**.

Only consider `main` or `master` as default (per skill scope). If the repo's real
default is something else (e.g. `develop`, `trunk`), **stop** and ask.

**Detached HEAD:** if `git branch --show-current` is empty, **stop** and ask the
user which branch to return to — do not guess or create a CLEANUP branch from a
detached tip.

**Already on `$DEFAULT` with a clean tree:** `git pull --ff-only origin $DEFAULT`
(skip pull if no remote), report clean, done. If pull fails (non-fast-forward),
**stop** and report — do not rebase or merge.

**Secrets guard (always):** scan the dirty set for secret patterns and if any
appear, **stop** and list them before doing anything destructive. Patterns:
`.env`, `*.env`, `.env.*`, `id_rsa`, `id_ed25519`, `*.pem`, `*.key`, `*.p12`,
`*.pfx`, `credentials*`, `secrets.*`, `*.keystore`, `*.jks`.

### 2. Fetch + merge check

```bash
git fetch origin || true   # tolerate offline; fall back to local refs
git branch --show-current
git merge-base --is-ancestor HEAD origin/$DEFAULT && echo MERGED || echo NOT_MERGED
```

Use **only** `git merge-base --is-ancestor HEAD origin/$DEFAULT` (exit 0 =
merged). If there is no remote, substitute the local `$DEFAULT` ref
(`refs/heads/$DEFAULT`).

Record:

- **merged**: current `HEAD` is an ancestor of `origin/$DEFAULT` (PR already in)
- **not merged**: unique commits still exist only on this branch

If not merged and you need the unique-commit count:

```bash
git rev-list --count origin/$DEFAULT..HEAD
```

### 3. Classify uncommitted files

Inspect both staged and unstaged (tracked mods + untracked):

```bash
git status --porcelain=v1
```

Classify each path into exactly one bucket:

| Bucket | Meaning | Examples |
|--------|---------|----------|
| **discardable** | Obvious run/output/cache noise | `*.log`, `*.tmp`, `*.pyc`, `__pycache__/`, `.pytest_cache/`, paths under `logs/`, `tmp/`, `output/`, `artifacts/`; untracked `*.json` that are clearly output (name/path contains `result`, `output`, `report`, `run`, or lives under those dirs) |
| **significant** | Coding / source changes | `*.py`, `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.mjs`, `*.cjs`, `*.go`, `*.rs`, `*.java`, `*.c`, `*.cpp`, `*.h`, `*.rb`, `*.php`, `*.swift`, `*.kt`, `*.cs`, `*.vue`, `*.svelte`, `*.sh`, plus tracked config/source like `package.json`, `tsconfig*.json`, `openclaw.json`, `*.yaml`, `*.yml`, `*.toml`, `Dockerfile*` |
| **unclear** | Anything else, or mixed signals | Untracked `*.json` that might be config; binary blobs; generated-but-valuable files; mix of discardable + non-discardable that is not purely significant |

**Never** treat these basenames as discardable: `package.json`, `package-lock.json`,
`tsconfig.json`, `openclaw.json`, `composer.json`, `Cargo.toml`, lockfiles, plus
any `*.md`, `*.plan.md`, `SKILL.md`, `*.canvas.tsx` (docs/skill edits are never
noise). Treat a rename (`R` in porcelain) as significant if **either** side
matches a significant extension.

Decision inputs:

1. merge status (`merged` / `not merged`)
2. buckets present in the dirty set

### 4. Act

Let `S` = significant set, `U` = unclear set, `D` = discardable set. Decide in
this exact order (first match wins):

| # | Condition | Action |
|---|-----------|--------|
| 1 | `S` non-empty | **Stop** (case A) — do not discard anything |
| 2 | `D` non-empty | Discard `D` (case B), then re-evaluate `U` and merge status → go to row 3/4 |
| 3 | after discard: `U` non-empty **OR** (not merged **AND** unique commits > 0) | **CLEANUP** (case C): park remaining work, then step 5 |
| 4 | otherwise (merged or clean, nothing unclear left) | step 5 directly (case D) |

Rationale: significant always wins; discard obvious noise first; if anything
unclear or any unmerged unique commits remain, preserve them on a CLEANUP
branch rather than risk losing work.

#### A. Significant coding changes present

**Stop.** Do not discard, commit, or switch branches — even the discardable
files stay untouched.

List every **significant** path as a **clickable** markdown link
(workspace-relative), plus a one-line `git status -sb` summary:

```markdown
Significant changes — review before cleanup:

- [src/foo.py](src/foo.py)
- [workspace-x/bar.ts](workspace-x/bar.ts)
```

Say briefly why cleanup paused and wait for the user.

#### B. Discard discardable noise

Preview first (dry run), then discard:

```bash
# 1. Preview (no changes):
git clean -nd -- <discardable-untracked-paths>
git status --porcelain=v1 -- <discardable-tracked-paths>

# 2. Unstage + revert tracked discardable to HEAD state:
git restore --staged --worktree -- <discardable-tracked-paths>

# 3. Remove untracked discardable (use -d for directories like __pycache__/):
git clean -fd -- <discardable-untracked-paths>
```

Path-limited `-fd` is required and allowed for untracked *directories*; the ban
is only on **unpathed** repo-wide `git clean -fd`. Never use `-x` (don't touch
ignored files).

After discard, re-run classification on what remains and continue to row 3/4.

#### C. Park remaining work on a CLEANUP branch

Use when `U` is non-empty OR the branch is not merged with unique commits you'd
otherwise abandon.

1. Create and switch (handle name collisions):

```bash
BRANCH="CLEANUP-$(git branch --show-current | tr -c 'a-zA-Z0-9/-' '-' | sed 's/--*/-/g')-$(date +%Y%m%d)"
# if $BRANCH already exists, append -2, -3, ... until free
git checkout -b "$BRANCH"
```

2. **Secrets re-check** on the staged set before committing:

```bash
git add -A
git status --porcelain=v1 | grep -Ei '\.env$|\.env\.|id_rsa|id_ed25519|\.pem$|\.key$|\.p12$|\.pfx$|credentials|secrets\.|\.keystore$|\.jks$' \
  && { echo "SECRET DETECTED — aborting commit"; git reset; }
```

   If the grep matches, **stop**, unstage (`git reset`), list the files, and wait.

3. Commit and push (push failure is non-fatal):

```bash
git commit -m "Park session branch noise on CLEANUP branch."
git push -u origin HEAD || echo "PUSH FAILED — work preserved locally on $BRANCH; continuing"
```

4. Continue to step 5.

#### D. Merged + clean working tree

Skip discard/commit; go to step 5.

### 5. Land on fresh default branch

When proceeding (not the significant-changes stop):

```bash
git checkout $DEFAULT
git pull --ff-only origin $DEFAULT   # skip if no remote
git status -sb
git rev-parse --short HEAD
```

If `git pull --ff-only` fails (local default has diverged), **stop** and report —
do not rebase or merge. If already on `$DEFAULT`, the `checkout` is a no-op.

Confirm to the user:

- previous branch name
- whether it was merged
- what was discarded vs parked on `CLEANUP-…` (with remote branch name, or
  "push failed, preserved locally")
- that `$DEFAULT` matches `origin/$DEFAULT` and the tree is clean

Do **not** delete local/remote feature branches unless the user asks.

## Hard rules

- Goal: move forward without interrupting flow when safe.
- Significant source changes → stop + clickable list; never auto-discard them
  (or anything else while stopped).
- Discard only clearly discardable output/cache paths, after a dry-run preview.
- Unclear or unmerged-unique work → `CLEANUP-` commit + push, then fresh `$DEFAULT`.
- Never use unpathed repo-wide `git clean -fd`; path-limited `-fd` for dirs is OK.
- Never use `git clean -x` (ignored files are out of scope).
- No force-push, no rebase/merge on the default branch (ff-only only).
- No secrets in commits; re-check after `git add -A` and abort if found.
- Stop (don't guess) on: detached HEAD, no resolvable default branch, non-main/
  master default, ff-only pull failure, or push failure (push failure is
  non-fatal for flow — just report it).
- No prod commits for openclaw; writes stay in develop.
