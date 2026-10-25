# Prep-worktree repo-aware isolation plan

Replace the single global protected path with a repo-scoped manager that never blocks, leases each worktree to one agent, and reclaims idle worktrees under a disk budget. Four stacked PRs. PR 1 makes acquisition repo-aware. PR 2 adds leases and a guard. PR 3 adds reaping, reuse, and archive. PR 4 adopts the existing population and migrates the docs. The operator lands the stack. Done when two repos with dirty protected checkouts acquire in one shell, a foreign worktree write is refused, the managed population stays under budget, and the existing 59 worktrees are reconciled without touching user-owned work.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, a file, a log line, a screenshot, a test run, or a SHA. The body is a how-to. The appendices explain and record.

The program runs `skills/poteto-mode/playbooks/autopilot-stack.md`. The operator lands the stack. PR 1 to PR 4 stop at merge-ready and wait for the operator's click.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on her explicit go.
- [ ] On her go, write the goal file with this exact text. "Deliver `docs/plans/prep-worktree-repo-aware-isolation.md` as PR 1 to PR 4. Every PR is verified by unit, live, and perf evidence. The operator lands the stack. Done when two repos with dirty protected checkouts acquire without human input, a foreign worktree is refused by the guard, the managed population stays within the disk budget, and the existing 59-worktree inventory is reconciled without touching user-owned worktrees."
- [ ] Read these from trunk at program start. Re-read them at every tick.
  - [ ] `git show origin/main:skills/poteto-mode/playbooks/autopilot-stack.md`
  - [ ] `git show origin/main:skills/swarm/SKILL.md`
  - [ ] `git show origin/main:skills/control-cli/SKILL.md`
  - [ ] `git show origin/main:skills/poteto-mode/playbooks/opening-a-pr.md`
  - [ ] `git show origin/main:skills/prep-worktree/SKILL.md`
  - [ ] `git show origin/main:skills/smart-commit-to-pr/SKILL.md`
  - [ ] `git show origin/main:skills/show-me-your-work/SKILL.md`
- [ ] Run the 30-minute audit tick as a background Task with sleep plus poll. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the execution playbook from trunk and the goal file. Audit the operation against both and fix drift in this tick. Probe every active lane and judge progress by side effects only. Stand down a stuck lane and dispatch its replacement now. Then send the operator a status message, whether or not anything changed, with the queue table of PR, owner, state, and head SHA, the verdicts since the last tick, what merged, open operator gates, and blockers."
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Spawn one owner per PR with the full lifecycle the execution playbook names.
- [ ] Write the throughput checkpoint before fan-out.
  - [ ] Blocking first steps. PR 1 lands the manager before PR 2 and PR 3.
  - [ ] Independent workstreams. Each PR's tests run after its manager shape is fixed. The manager file is a shared write, so the PR owner writes it. Test fixtures parallelize.
  - [ ] Shared mutable state. Each worktree owns one metadata directory. Only reaping uses a repository-scoped `flock`.
  - [ ] Smallest safe decomposition. One owner per PR because all four touch the same manager file. The owner fans out test fixtures inside its PR.
- [ ] Follow this dependency graph. Start dependent work only after its parent merges.
  - [ ] PR 1 is first and branches from `origin/main` after PR #18 and PR #19 land.
  - [ ] PR 2 after PR 1.
  - [ ] PR 3 after PR 2.
  - [ ] PR 4 after PR 3.
- [ ] Hold the file boundaries. PR 1 to PR 3 touch only `.agents/skills/prep-worktree/**`, `tests/test_prep_worktree*.py`, `README.md`, and `config.example.json`. PR 4 also touches `.agents/skills/smart-implement/SKILL.md` and `.agents/skills/smart-commit-to-pr/SKILL.md`.
- [ ] Hold the review gate. PR 1 to PR 4 change a CLI interaction. They wait for the operator's review in chat with screenshots and a video before merge.

### PR mechanics, for every PR

- [ ] Open the PR ready, never draft, with `gh pr create` and `draft: false`. For a stack, create one branch per PR and set each child base with `gh pr edit --base <parent-branch>`.
- [ ] Run the repo's lint and typecheck once before the PR-facing push. Push with hooks on.
- [ ] Load the no-comments skill before review.
- [ ] Triage every review-bot comment.
- [ ] Rebase onto current trunk before babysit and again before the merge-ready report.

### Verdict and merge, for every PR

- [ ] At the merge-ready head SHA, run the swarm per `skills/swarm/SKILL.md`. One gates lane. The ten live lanes from the PR's **Verify, live** block. The perf lane from its **Verify, perf** block. One audit lane that reads the diff and the receipts and distrusts the PR body.
- [ ] Clean only when every lane is `PASS`. Findings go back to the owner. A new head gets a fresh swarm and a fresh verdict.
- [ ] Append the clean PR to the one linear stack in verified order. The operator lands it with her own merges. No owner merges or enables auto-merge.
- [ ] If trunk moves, rebase the chain and compare `git patch-id` at each verdict SHA. Re-verify any PR whose patch id changed.

### Boot recipe, for every live lane

Each live lane runs at the PR head via the Task tool. Drive through the control-cli skill in this package.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>` in a scratch clone under `/tmp/prep-plan/<pr-id>`.
- [ ] Create two throwaway repositories under `/tmp/prep-plan/<pr-id>/repos` with a local bare origin. Start no service. Wait for `prep-worktree doctor` to exit 0 on the healthy fixture.
- [ ] Deliver input only through the `prep-worktree` CLI. Name the read-only diagnostics as `git worktree list --porcelain`, `git status --porcelain=v1 --untracked-files=all`, `ls`, and `du`.
- [ ] Save every screenshot to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.png` and the full transcript to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.log`. Return the paths with the report.

## Make prep-worktree repo-aware and never blocking (PR 1)

**Depends on.** PR #18 and PR #19 are merged, or their content is absorbed into this PR.

**Files.**

- [ ] Create `.agents/skills/prep-worktree/scripts/prep_worktree.py`.
- [ ] Create `.agents/skills/prep-worktree/scripts/prep-worktree`.
- [ ] Edit `.agents/skills/prep-worktree/SKILL.md`.
- [ ] Edit `README.md`.
- [ ] Edit `config.example.json`.
- [ ] Delete `tests/test_prep_worktree_skill.py`.
- [ ] Create `tests/test_prep_worktree.py`.

**Build.**

- [ ] Add `resolve_repo(path)` in `prep_worktree.py`. Return the canonical common dir, the device and inode key, the main worktree, and the remote URL.
- [ ] Add `load_config(repo)` in `prep_worktree.py`. Read the shared `$XDG_CONFIG_HOME/smarter-way/config.json` or `$HOME/.config/smarter-way/config.json`. Select defaults by common-dir path, then by remote URL. Return defaults when no entry exists.
- [ ] Add `resolve_base(repo, config)` in `prep_worktree.py`. Use the configured base ref, then `origin/main`, `origin/master`, `main`, then `master`. Fetch only the base ref. On fetch failure, use the existing ref and print `BASE_STALE`.
- [ ] Add `acquire(repo, options)` in `prep_worktree.py`. Treat `protected_paths` as exclusion paths only. Do not require them to exist, be clean, be on the default branch, or belong to the current repository.
- [ ] Add the current checkout as an implicit protected path. Never mutate it. Never land inside it, inside another registered worktree, or inside the common Git directory.
- [ ] Store metadata in `$COMMON/prep-worktree/worktrees/<admin-id>/` with `meta.json` and `lease.json`. The admin id is the basename of the worktree's admin directory under `$COMMON/worktrees/`.
- [ ] Use `git status --porcelain=v1 --untracked-files=all` for cleanliness. Never use `--ignored` for a block decision. Carry the PR #18 rule.
- [ ] Add a thin `scripts/prep-worktree` Bash wrapper with `acquire`, `list`, `status`, `guard`, `heartbeat`, `release`, `reap`, `adopt`, `doctor`, and `archive restore`.
- [ ] Emit shell exports from `acquire` by default and JSON with `--json`. Print `PREP_WORKTREE_ID`, `PREP_WORKTREE_PATH`, `PREP_WORKTREE_BRANCH`, and `PREP_WORKTREE_BASE_SHA`.
- [ ] Remove the `PREP_WORKTREE_PROTECTED_DEV_PATH` requirement from `SKILL.md` and `README.md`. Accept it only as a legacy override when it resolves to the current repository. Ignore a wrong-repository value with `LEGACY_PROTECTED_IGNORED`.

**You see.**

- [ ] `prep-worktree acquire --repo /repo/a` prints four exports and exits 0 while `/repo/a` has tracked changes.
- [ ] The same shell calls `prep-worktree acquire --repo /repo/b` and exits 0 with no environment change.
- [ ] `PREP_WORKTREE_PROTECTED_DEV_PATH=/repo/b` in `/repo/a` prints `LEGACY_PROTECTED_IGNORED` and still creates the worktree.
- [ ] `prep-worktree acquire --repo /repo/a --json` prints `{"id": "...", "path": "...", "branch": "...", "base_sha": "..."}`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/test_prep_worktree.py::test_two_repos_with_dirty_protected_checkouts` builds two repos and asserts both `acquire` calls exit 0. Run `python3 -m pytest tests/test_prep_worktree.py`.
- [ ] `tests/test_prep_worktree.py::test_missing_wrong_repo_and_dirty_protected_paths_do_not_block` asserts exit 0 and the warning text.
- [ ] `tests/test_prep_worktree.py::test_ignored_files_do_not_block` writes `logs/` and `.venv/` in the protected checkout and asserts exit 0.
- [ ] `tests/test_prep_worktree.py::test_base_fetch_failure_uses_existing_ref` removes the origin remote after the fetch and asserts `BASE_STALE` plus exit 0.
- [ ] `tests/test_prep_worktree.py::test_per_repo_config_selects_protected_paths` writes the shared config and asserts repo A and repo B select different protected paths.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the inherited parent model at the PR head, per the boot recipe.

- [ ] Lane 1. Two repos, repo A dirty and repo B clean, both acquire from one shell. Save `pr1-two-repos.png`. Pass when both exit 0 and each path is outside its protected checkout.
- [ ] Lane 2. Repo A has a tracked modification and an untracked file. Save `pr1-dirty-protected.png`. Pass when acquire exits 0 and prints the dirty count as a warning, not a stop.
- [ ] Lane 3. The protected path is missing. Save `pr1-missing-protected.png`. Pass when acquire exits 0 and prints `PROTECTED_MISSING`.
- [ ] Lane 4. The protected path points at repo B while run in repo A. Save `pr1-wrong-repo.png`. Pass when acquire exits 0 and prints `PROTECTED_OTHER_REPO`.
- [ ] Lane 5. The protected checkout is on a feature branch. Save `pr1-feature-branch.png`. Pass when acquire exits 0 and records `protected_branch=feature/example`.
- [ ] Lane 6. The protected checkout has `logs/`, `.venv/`, and `node_modules/`. Save `pr1-ignored-artifacts.png`. Pass when acquire exits 0 and the worktree is clean by `git status`.
- [ ] Lane 7. `origin` is unreachable after the first fetch. Save `pr1-stale-base.png`. Pass when acquire exits 0 and prints `BASE_STALE` with the existing `origin/main` SHA.
- [ ] Lane 8. No `origin` remote exists and local `main` exists. Save `pr1-local-base.png`. Pass when acquire exits 0 and records `base=main`.
- [ ] Lane 9. The shared config gives repo A one protected path and repo B another. Save `pr1-config.png`. Pass when `prep-worktree status --json` shows the matching protected paths.
- [ ] Lane 10. The legacy env var points at the wrong repository. Save `pr1-legacy-env.png`. Pass when acquire exits 0, prints `LEGACY_PROTECTED_IGNORED`, and leaves the env unchanged.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `acquire` wall time in milliseconds and blocked-run count across the 20-scenario matrix.
- [ ] Probe. Run `time` around 20 `prep-worktree acquire` calls on a fixture with two repos and 60 registered worktrees at trunk and at the head, interleaved.
- [ ] Baseline. Record the trunk blocked-run count first. The current skill requires one global path and a clean checkout, so the expected baseline is 20 blocked runs out of 20.
- [ ] Rule. Head must finish 20 of 20 runs and keep p95 at or below 2000 ms. One blocked run or p95 above 5000 ms fails.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2, lane 4, and lane 10 screenshots into `/tmp/prep-plan/media/pr-1-review-<slug>.png`.
- [ ] Record a 30 to 60 second video of the two-repo acquire and the wrong-repo warning. Save it as `/tmp/prep-plan/media/pr-1-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Review triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] Root appends PR 1 to the stack. The operator lands it.

## Lease each worktree to one agent (PR 2)

**Depends on.** PR 1.

**Files.**

- [ ] Edit `.agents/skills/prep-worktree/scripts/prep_worktree.py`.
- [ ] Edit `.agents/skills/prep-worktree/scripts/prep-worktree`.
- [ ] Edit `.agents/skills/prep-worktree/SKILL.md`.
- [ ] Edit `tests/test_prep_worktree.py`.

**Build.**

- [ ] Add a per-worktree lease under `$COMMON/prep-worktree/worktrees/<admin-id>/lease`. Store `owner_session`, `owner_pid`, `created_at`, `last_seen`, `state`, `branch`, and `path`.
- [ ] Generate `owner_session` from `OPENCODE_SESSION_ID`, then `PREP_AGENT_ID`, then a random 128-bit id. Record it in the handoff output.
- [ ] Write each lease with a temp file and `mv` into the per-worktree directory. Do not use one shared registry JSON.
- [ ] Add `guard`. It resolves the current worktree, reads the lease, and exits 2 when the current path is not the leased path or `PREP_WORKTREE_ID` does not match the lease.
- [ ] Add `heartbeat`. It updates `last_seen` only for the lease owner.
- [ ] Add `release`. It marks the lease `idle` only when the worktree is clean and has no commits ahead of its base. Otherwise it marks `needs-cleanup`.
- [ ] Add `list` and `status`. Report id, path, branch, state, owner, age, and whether a live process has a working directory inside the worktree.
- [ ] Make `acquire` always return a new id and path while a lease is active. Never hand the same path to two agents.
- [ ] Add a `doctor` check that every managed path is a registered worktree, every lease points at its own path, and no two leases share a path.

**You see.**

- [ ] `prep-worktree acquire` prints `PREP_WORKTREE_ID=...` and `PREP_WORKTREE_OWNER=...`.
- [ ] `prep-worktree guard` exits 0 in the leased worktree.
- [ ] `prep-worktree guard` exits 2 in a different managed worktree and prints `FOREIGN_WORKTREE` with the owner id.
- [ ] A second acquire from another shell prints a different path and a different id.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/test_prep_worktree.py::test_acquire_returns_unique_paths` runs eight concurrent acquires and asserts eight unique paths.
- [ ] `tests/test_prep_worktree.py::test_guard_rejects_foreign_worktree` asserts exit 2 and the `FOREIGN_WORKTREE` message.
- [ ] `tests/test_prep_worktree.py::test_guard_rejects_missing_lease` asserts exit 2 outside a managed worktree.
- [ ] `tests/test_prep_worktree.py::test_heartbeat_and_release_are_owner_only` asserts a foreign owner cannot update the lease.
- [ ] `tests/test_prep_worktree.py::test_lease_records_survive_git_gc` runs `git gc` and asserts the meta and lease files remain.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the inherited parent model at the PR head, per the boot recipe.

- [ ] Lane 1. Acquire a worktree in repo A. Save `pr2-acquire.png`. Pass when the output includes a path, branch, base SHA, and owner id.
- [ ] Lane 2. Acquire twice from two shells. Save `pr2-two-agents.png`. Pass when the two paths differ and neither lease names the other owner.
- [ ] Lane 3. Run `guard` in the first worktree. Save `pr2-guard-own.png`. Pass when exit is 0.
- [ ] Lane 4. Run `guard` in the second worktree with the first worktree's id. Save `pr2-guard-foreign.png`. Pass when exit is 2 and the owner id is printed.
- [ ] Lane 5. Run `guard` in `/tmp` outside every worktree. Save `pr2-guard-outside.png`. Pass when exit is 2 and the message says no lease.
- [ ] Lane 6. Run `heartbeat` as the owner. Save `pr2-heartbeat.png`. Pass when `last_seen` changes.
- [ ] Lane 7. Run `heartbeat` as a foreign session. Save `pr2-heartbeat-foreign.png`. Pass when exit is 2 and `last_seen` does not change.
- [ ] Lane 8. Release a clean worktree. Save `pr2-release.png`. Pass when the lease state becomes `idle`.
- [ ] Lane 9. Release a dirty worktree. Save `pr2-release-dirty.png`. Pass when the state becomes `needs-cleanup` and no files are deleted.
- [ ] Lane 10. Run `prep-worktree doctor`. Save `pr2-doctor.png`. Pass when it reports zero duplicate paths and zero broken leases.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `guard` wall time and duplicate-path count.
- [ ] Probe. Run `guard` 200 times on a fixture with 60 managed worktrees, at trunk and at the head, interleaved.
- [ ] Baseline. Record the trunk guard time first. The current skill has no guard, so the baseline duplicate-path count is unmeasured.
- [ ] Rule. Head `guard` p95 at or below 100 ms. Any duplicate live path or any foreign guard pass fails.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2, lane 4, and lane 9 screenshots into `/tmp/prep-plan/media/pr-2-review-<slug>.png`.
- [ ] Record a 30 to 60 second video of two acquires, an own guard, and a foreign guard. Save it as `/tmp/prep-plan/media/pr-2-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Review triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] Root appends PR 2 to the stack. The operator lands it.

## Reclaim idle worktrees and bound disk (PR 3)

**Depends on.** PR 2.

**Files.**

- [ ] Edit `.agents/skills/prep-worktree/scripts/prep_worktree.py`.
- [ ] Edit `.agents/skills/prep-worktree/scripts/prep-worktree`.
- [ ] Edit `.agents/skills/prep-worktree/SKILL.md`.
- [ ] Edit `README.md`.
- [ ] Edit `tests/test_prep_worktree.py`.

**Build.**

- [ ] Add `reap --dry-run` and `reap --apply`. Serialize reaping with `flock` on `$COMMON/prep-worktree/reap.lock`. Use a bounded wait. If the lock is busy, print `REAP_SKIPPED` and continue. Never block an acquire.
- [ ] Reuse an `idle` managed worktree before creating a new one. Reset it to the base SHA with `git reset --hard` and `git clean -fd`. Keep ignored files.
- [ ] Delete an idle branch only when it is merged into its base or has zero commits ahead. Keep an unmerged branch and record `BRANCH_RETAINED`.
- [ ] Archive tracked and untracked non-ignored files to `refs/prep-archive/<admin-id>/<timestamp>` with a temporary `GIT_INDEX_FILE` and `git commit-tree`.
- [ ] Verify the archive by reading the commit back into a temporary index and comparing every path hash with the worktree. Remove the worktree only after the archive verifies.
- [ ] Count ignored bytes and list secret-looking ignored paths. Never auto-remove a worktree whose ignored set matches `.env`, `*.pem`, `*.key`, `credentials*`, `secrets.*`, or an SSH key. Mark it `HUMAN_REVIEW`.
- [ ] Remove only managed worktrees with no live lease, no live process working directory, and no `git worktree lock`. Treat a missing registry record as user-owned and never remove it.
- [ ] Reconcile prunable registrations by removing that exact registration after the path is gone. Never run a blanket `git worktree prune`.
- [ ] Enforce a soft `max_managed_worktrees` and a `disk_budget_gib`. When the budget is exceeded, reap first. If no safe candidate exists, create anyway, print `OVER_BUDGET`, and keep the create non-blocking.
- [ ] Add `archive restore <ref> --path <path>`. Restore is an explicit action and consumes a new managed slot.

**You see.**

- [ ] `prep-worktree reap --dry-run` lists each candidate, its reason, branch, and size, and changes nothing.
- [ ] `prep-worktree reap --apply` removes a clean expired worktree and prints its archive ref or `NO_ARCHIVE_NEEDED`.
- [ ] A dirty expired worktree is archived and removed only after `ARCHIVE_VERIFIED`.
- [ ] A worktree with a live process working directory prints `SKIP_ACTIVE` and remains.
- [ ] A worktree with a secret-looking ignored file prints `HUMAN_REVIEW` and remains.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/test_prep_worktree.py::test_reap_removes_clean_expired_worktree` asserts the path is gone and the branch rule ran.
- [ ] `tests/test_prep_worktree.py::test_reap_archives_dirty_worktree_before_removal` asserts the archive ref exists and every file hash matches.
- [ ] `tests/test_prep_worktree.py::test_reap_skips_active_and_locked_worktrees` asserts both remain.
- [ ] `tests/test_prep_worktree.py::test_reap_refuses_secret_ignored_files` asserts the worktree remains and the report says `HUMAN_REVIEW`.
- [ ] `tests/test_prep_worktree.py::test_reuse_resets_tracked_files_and_keeps_ignored_cache` asserts tracked files return to base and `.venv` remains.
- [ ] `tests/test_prep_worktree.py::test_reap_lock_busy_does_not_block_acquire` holds the reap lock and asserts acquire still exits 0.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the inherited parent model at the PR head, per the boot recipe.

- [ ] Lane 1. Clean expired worktree. Save `pr3-clean-reap.png`. Pass when `reap --apply` removes it and prints the branch decision.
- [ ] Lane 2. Dirty tracked worktree. Save `pr3-dirty-archive.png`. Pass when the archive ref exists and `ARCHIVE_VERIFIED` is printed before removal.
- [ ] Lane 3. Untracked file worktree. Save `pr3-untracked-archive.png`. Pass when the archive contains the untracked path and its hash matches.
- [ ] Lane 4. Unpushed commit worktree. Save `pr3-unpushed.png`. Pass when the branch is retained and the commit remains reachable.
- [ ] Lane 5. Ignored-only worktree with `.env`. Save `pr3-secret-ignored.png`. Pass when the worktree remains and the report says `HUMAN_REVIEW`.
- [ ] Lane 6. Live process with a working directory inside the worktree. Save `pr3-active.png`. Pass when `reap` prints `SKIP_ACTIVE` and the worktree remains.
- [ ] Lane 7. Idle worktree reuse. Save `pr3-reuse.png`. Pass when the tracked tree is at the base SHA and `.venv` remains.
- [ ] Lane 8. Disk budget exceeded. Save `pr3-budget.png`. Pass when `reap` frees a candidate and acquire still creates within the budget.
- [ ] Lane 9. Twenty acquire and release cycles. Save `pr3-soak.png`. Pass when the managed count stays at or below `max + 1` and no call blocks.
- [ ] Lane 10. Kill a process during `reap --apply`. Save `pr3-crash.png`. Pass when the next `reap --dry-run` reconciles the archive and registration and no worktree is half-removed.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `reap --dry-run` wall time, managed worktree count, and disk bytes after 20 acquire and release cycles.
- [ ] Probe. Run `prep-worktree reap --dry-run --json` on a fixture with 60 managed worktrees. Run the 20-cycle soak at trunk and at the head, interleaved.
- [ ] Baseline. Record the trunk managed count first. The live inventory is 59 registered worktrees against `PREP_WORKTREE_MAX=20`, with 48 under `/tmp`.
- [ ] Rule. Head `reap --dry-run` p95 at or below 2000 ms. After each cycle the managed count must be at or below `max + 1`, and disk must stay at or below the configured budget. Any unbounded growth or any blocking acquire fails.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2, lane 5, and lane 9 screenshots into `/tmp/prep-plan/media/pr-3-review-<slug>.png`.
- [ ] Record a 30 to 60 second video of a dirty archive, a secret ignored refusal, and a soak count. Save it as `/tmp/prep-plan/media/pr-3-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Review triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] Root appends PR 3 to the stack. The operator lands it.

## Adopt existing worktrees and migrate the contract (PR 4)

**Depends on.** PR 3.

**Files.**

- [ ] Edit `.agents/skills/prep-worktree/scripts/prep_worktree.py`.
- [ ] Edit `.agents/skills/prep-worktree/SKILL.md`.
- [ ] Edit `README.md`.
- [ ] Edit `.agents/skills/smart-implement/SKILL.md`.
- [ ] Edit `.agents/skills/smart-commit-to-pr/SKILL.md`.
- [ ] Edit `tests/test_prep_worktree.py`.

**Build.**

- [ ] Add `adopt --dry-run` and `adopt --apply`. Detect a legacy worktree only when its branch starts with `prep-worktree/` and its path matches `.*-<repo>-prep.*`, or when the registry already names it. Treat every other worktree as user-owned and never touch it.
- [ ] Write a legacy record with `state=legacy`, `owner=unknown`, `last_seen` from the worktree directory mtime, and no lease.
- [ ] Reconcile prunable registrations in the adopt report. Remove only the specific registration after the path is gone.
- [ ] Add a one-time runbook to `README.md`. Inventory, dry-run, archive, reap, and verify. Do not run `git worktree prune`.
- [ ] Document the shared config key `prep_worktree` in `README.md` and `config.example.json`. Document that `PREP_WORKTREE_PROTECTED_DEV_PATH` and `PREP_WORKTREE_MAX` are optional legacy overrides.
- [ ] Document the canonical-checkout rule. The primary worktree is the first entry in `git worktree list --porcelain`. Prep protected paths are explicit exclusions. `sync_skills.py` and prep-worktree use these two different rules on purpose.
- [ ] Add a `prep-worktree guard` step to `smart-implement` before the first edit.
- [ ] Keep the `prep-worktree/` branch prefix. Update `smart-commit-to-pr` to say the prefix is still a prep base branch and still must become a `feature/...` branch before push.
- [ ] Add a rollback note. The old skill is a single Markdown file. Keep the last released copy in the PR body so the operator can restore it.

**You see.**

- [ ] `prep-worktree adopt --dry-run --json` reports managed legacy, user-owned, and prunable counts without changing any worktree.
- [ ] `prep-worktree adopt --apply` adds legacy records and leaves every user-owned path unchanged.
- [ ] The README config example parses with the manager and yields the documented defaults.
- [ ] `smart-implement` tells the agent to run `prep-worktree guard` before editing.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/test_prep_worktree.py::test_adopt_dry_run_changes_nothing` asserts identical `git worktree list` output before and after.
- [ ] `tests/test_prep_worktree.py::test_adopt_skips_user_owned_worktree` asserts the user worktree has no record and no state change.
- [ ] `tests/test_prep_worktree.py::test_adopt_detects_legacy_prep_branch` asserts the branch-prefix and path-pattern match.
- [ ] `tests/test_prep_worktree.py::test_prunable_registration_is_reconciled` asserts the missing path is removed from the registration list and the branch remains.
- [ ] `tests/test_prep_worktree.py::test_readme_config_example_parses` loads `config.example.json` and asserts the `prep_worktree` keys.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the inherited parent model at the PR head, per the boot recipe.

- [ ] Lane 1. Legacy prep worktree with a `prep-worktree/` branch. Save `pr4-legacy.png`. Pass when `adopt --dry-run` lists it as managed legacy.
- [ ] Lane 2. User-owned feature worktree. Save `pr4-user-owned.png`. Pass when the report lists it as user-owned and `adopt --apply` changes nothing.
- [ ] Lane 3. Prunable registration. Save `pr4-prunable.png`. Pass when the registration is removed and the branch remains.
- [ ] Lane 4. The 59-worktree inventory. Save `pr4-inventory.png`. Pass when the dry-run counts match `git worktree list --porcelain` and the prototype inventory.
- [ ] Lane 5. `adopt --apply` on the fixture. Save `pr4-apply.png`. Pass when only managed legacy records are added.
- [ ] Lane 6. `reap --dry-run` after adoption. Save `pr4-reap-dry-run.png`. Pass when every candidate has a reason and no user-owned path appears.
- [ ] Lane 7. README config example copied to a temp config. Save `pr4-config.png`. Pass when `prep-worktree doctor` accepts it.
- [ ] Lane 8. `smart-implement` text check. Save `pr4-smart-implement.png`. Pass when the guard step appears before the first edit instruction.
- [ ] Lane 9. `smart-commit-to-pr` branch classification. Save `pr4-smart-commit.png`. Pass when a `prep-worktree/` branch is still classified as BASE and converted before push.
- [ ] Lane 10. Rollback. Save `pr4-rollback.png`. Pass when restoring the prior `SKILL.md` makes the old command work again without touching any worktree.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. `adopt --dry-run` wall time for the live inventory and user-owned mutation count.
- [ ] Probe. Run `prep-worktree adopt --dry-run --json` on the 59-worktree fixture at trunk and at the head, interleaved. Diff the user-owned path list before and after `adopt --apply`.
- [ ] Baseline. Record the trunk inventory first. The live repository has 59 registered worktrees, 197 unmerged branches, 27 prep branches, and 20 merged prep branches.
- [ ] Rule. Head dry-run p95 at or below 5000 ms. After apply, managed records must be at or below `max + 1`, and the user-owned path list must be byte-identical. Any user-owned mutation fails.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 1, lane 2, and lane 4 screenshots into `/tmp/prep-plan/media/pr-4-review-<slug>.png`.
- [ ] Record a 30 to 60 second video of the dry-run, apply, and user-owned path diff. Save it as `/tmp/prep-plan/media/pr-4-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Review triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] Root appends PR 4 to the stack. The operator lands it.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] Reply to the operator with the stack root and tip, the per-PR verdicts, the live inventory after adoption, and the remaining risks.

## Appendix A. Prototype evidence

The prototypes ran under `/tmp/opencode/prep-exp`. The scripts and outputs are local and disposable. They proved these facts.

- Repository identity. `A-identity.sh` showed that `git rev-parse --path-format=absolute --git-common-dir` plus the device and inode of that directory is stable across linked worktrees and a directory rename. Two clones with the same remote URL have different common dirs, so the remote URL is not an identity. A nested worktree created from a linked worktree still shares the same common dir.
- Removal behavior. `C-remove.sh` showed that plain `git worktree remove` refuses tracked and untracked changes, removes an ignored-only worktree and deletes the ignored files, never deletes the branch, removes a worktree while a process has its working directory inside, and cannot remove a worktree whose `.git` file was replaced.
- Lock behavior. `D-locks.sh` showed that a `mkdir` lock survives `SIGKILL` and blocks forever, while `flock` releases on process death in about 0 ms. `flock -n` does not queue under contention. A deleted lock file breaks exclusion. `flock -o` prevents child inheritance. The command-line `flock` is not on macOS by default.
- Archive behavior. `F-archive.sh` showed that a temporary index plus `git commit-tree` captures tracked, staged, deleted, and untracked files. Reading the archive back and comparing hashes is the proof. Ignored files are not covered by default and can be large.
- Concurrency. `G-concurrency.sh` showed that an unlocked check-then-act limit admits 9 worktrees against a limit of 3. `G2.sh` showed that a bounded `flock` held across count and add keeps the count at the limit with no wait longer than the timeout.
- No global lock. `N` ran eight concurrent `git worktree add` calls with per-worktree records and no global create lock. All eight succeeded, the registration count was 9, the record count was 8, and `git status` stayed clean.
- Live inventory. `I-inventory.sh` measured 59 registered worktrees in `openclaw-customizations`, 48 of them under `/tmp`, 257 local branches, 197 branches not merged to `origin/main`, 27 prep branches, and 20 merged prep branches. The main worktree is 2.6G. The configured maximum is 20.

Unproven. macOS `flock` needs a Python or Perl wrapper because the command is absent. `flock` is not reliable on NFS or SMB. A same-user agent can still write into another worktree if it ignores the guard. The guard prevents accidents, not a hostile process. The archive policy for secret-looking ignored files needs a human decision in PR 3.

Delivery note. The operator invoked `smart-implement` and requested the plan on one branch. The four-PR sequence is collapsed into one branch. The unit suite, the live guard and archive drive, and the cleanup checks ran. The full 40-lane live matrix and the review videos did not run. Treat those as open gates, not passes.

## Appendix B. Alternatives rejected

- Keep one global protected path and switch the environment per repo. It blocks the second repo in the same session and hides repo identity in shell state. Rejected.
- Keep the protected checkout cleanliness gate. A development checkout is routinely dirty, and the worktree is created from a fetched ref, so cleanliness proves nothing about safety. Rejected.
- Use the remote URL as the repository key. Two clones of one origin collide, and one repository can have several URL spellings. Rejected.
- Use the first `git worktree list` entry as the protected path. That is the primary worktree, but the user may need to protect a different linked checkout or a second clone. Rejected as a single rule. The primary worktree is documented only as the install source.
- Use `git worktree lock` as the ownership marker. It changes removal behavior and stays after the owner dies. Rejected.
- Use one shared `registry.json`. It creates a shared write target and needs a lock on every acquire. Rejected in favor of one directory and one metadata file per worktree.
- Use a global `mkdir` lock on the create path. It deadlocks after a crash and serializes independent agents. Rejected in favor of per-worktree atomic records and a `flock` only for reaping.
- Require human approval for every cleanup. Unattended agents cannot approve, so the population grows. Rejected in favor of verify, archive, and reap.
- Delete dirty worktrees without an archive. It loses uncommitted work and ignored files. Rejected.
- Treat access time as the inactivity clock. `relatime` and the manager's own scans make it unreliable. Rejected in favor of the manager's `last_seen` and lease state.
- Keep every ignored file because it may be a secret. This leaves 469M or more per worktree. Rejected. The manager reports ignored bytes, refuses secret-looking paths, and keeps the human review path.
- Put the registry inside the worktree. The file shows as untracked, and removing the worktree loses the record. Rejected. Metadata lives in the common Git directory.

## Appendix C. Risks

- PR 1. A repository moved to a new filesystem changes its inode key. The manager falls back to the common-dir path and prints `REPO_KEY_FALLBACK`. The owner watches the fallback rate.
- PR 1. A wrong legacy protected path is ignored, so a user may believe a checkout is protected when it is not. The `status` output names the effective protected paths. The owner checks that line in lane 4.
- PR 2. A same-user agent can bypass the guard. This is a trust boundary, not a sandbox. The archive and lease gate cleanup, but they cannot stop a hostile write. The owner documents the limit in `SKILL.md`.
- PR 2. A long-running agent may not call `heartbeat`. The lease then looks idle. Reaping still requires an absent live process working directory and an archive. The owner watches `resurrection_total`.
- PR 3. Archiving ignored files can copy secrets. The default excludes them and marks secret-looking paths `HUMAN_REVIEW`. The owner checks lane 5.
- PR 3. Removing a worktree while a process has an open file but a different working directory is undetected. The archive is the recovery path. The owner watches `remove_refused` and `resurrection_total`.
- PR 3. A hard disk budget can still be exceeded when every worktree is active. The manager creates anyway and prints `OVER_BUDGET`. The owner watches the alert count and the next reap.
- PR 4. Adoption can misclassify a user worktree if it happens to use the `prep-worktree/` prefix and the path pattern. The dry-run report is mandatory, and the apply path fails closed on any missing registry evidence. The owner checks lane 2.
- PR 4. The live inventory contains 48 worktrees under `/tmp` and one prunable Cursor registration. A reboot can turn them into prunable registrations. The runbook reconciles them by exact path and never runs a blanket prune.
- All PRs. macOS and network filesystems need a separate test pass. The plan's live lanes run on Linux. The owner records the platform gap in the PR body.

## Appendix D. Links and reading list

- `skills/prep-worktree/SKILL.md`. The current contract, shell blocks, and cleanup prose.
- `README.md`. The shared config rule, the current `PREP_WORKTREE_*` claims, and the install section.
- `tests/test_prep_worktree.py`. The behavior suite for the manager.
- `skills/smart-commit-to-pr/SKILL.md`. The `prep-worktree/` branch-prefix contract.
- `sync_skills.py` and `tests/test_sync_skills.py`. The primary-worktree install rule from PR #19.
- PR #18. Ignore gitignored files in pristine checks.
- PR #19. Point skill installs at the primary development checkout.
- `/tmp/opencode/prep-exp/A-identity.sh`, `C-remove.sh`, `D-locks.sh`, `F-archive.sh`, `G-concurrency.sh`, `G2.sh`, and `I-inventory.sh`. The prototype scripts.
- `/tmp/opencode/prep-exp/results/`. The prototype output.
- `skills/how/SKILL.md` for PR 1.
- `skills/interrogate/SKILL.md` for PR 2 and PR 3.
- `skills/show-me-your-work/SKILL.md`. The decision trail for the whole program. Keep it local unless the operator asks for the audit trail to be committed.
