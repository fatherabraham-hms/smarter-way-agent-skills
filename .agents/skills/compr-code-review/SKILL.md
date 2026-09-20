---
name: compr-code-review
description: >-
  Comprehensive code review across correctness, security, maintainability,
  tests, style, and associated arch-blueprint goals and gates. Use when the
  user asks for compr-code-review, comprehensive code review, full review, PR
  review, or review before merge. Review using parallel sub-agents and report
  axes side by side.
disable-model-invocation: true
---

# Comprehensive Code Review

Review code changes in the **current repo** before merge or after a feature is
done. Works in any project — infer language, framework, and conventions from
the diff and surrounding code.

```text
- [ ] 1. Determine diff scope
- [ ] 2. Identify standards sources
- [ ] 3. Resolve associated arch-blueprint (or record none)
- [ ] 4. If associated: check all goals met and all gates pass
- [ ] 5. Classify active review lanes; fan them out in parallel
- [ ] 6. Aggregate per-axis findings (never a cross-axis winner)
- [ ] 7. Write structured report — stop; do not fix unless asked
```

## 1. Diff scope

| User intent | Diff scope |
|-------------|------------|
| Default | Branch changes vs merge-base with default branch (`main`/`master`) |
| Uncommitted / dirty / WIP | Staged + unstaged only |
| Specific PR or branch | `git diff <default>...<target>`; do not check out or stash without user confirmation |

Gather in parallel:

```bash
git status -sb
git diff --stat
git log --oneline -5
```

If the diff is empty, say so and stop.

## 2. Standards sources

Anything in the repo that documents how code should be written
(CODING_STANDARDS.md, CONTRIBUTING.md, etc.).

On top of whatever the repo documents, the Standards axis always carries the
**smell baseline** below — a fixed set of Fowler code smells (Refactoring,
ch. 3) that applies even when a repo documents nothing. Match each smell
against the diff; each reads *what it is → how to fix*:

- **Mysterious Name** — a name that doesn't reveal what it does or holds → rename it; if no honest name comes, the design's murky.
- **Duplicated Code** — the same logic shape in more than one hunk or file → extract the shared shape, call it from both.
- **Feature Envy** — a method reaching into another object's data more than its own → move the method onto the data it envies.
- **Data Clumps** — the same few fields or params keep travelling together → bundle them into one type, pass that.
- **Primitive Obsession** — a primitive or string standing in for a domain concept → give the concept its own small type.
- **Repeated Switches** — the same switch/if-cascade on the same type recurring → polymorphism, or one map both sites share.
- **Shotgun Surgery** — one logical change forcing scattered edits across many files → gather what changes together into one module.
- **Divergent Change** — one module edited for several unrelated reasons → split so each changes for one reason.
- **Speculative Generality** — abstraction, params, or hooks for needs the spec doesn't have → delete it; inline back until a real need shows.
- **Message Chains** — long `a.b().c().d()` navigation → hide the walk behind one method on the first object.
- **Middle Man** — a class or function that mostly delegates onward → cut it, call the real target direct.
- **Refused Bequest** — a subclass ignoring or overriding most of what it inherits → drop the inheritance, use composition.

Two rules bind the baseline:

- **The repo overrides.** A documented repo standard always wins; where it
  endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible
  Feature Envy"), never a hard violation. Like any standard here, skip
  anything tooling already enforces.

## 3. Arch-blueprint association (required)

Before scoring the diff, check whether an **arch-blueprint** belongs to this
session. Do **not** assume a machine-specific directory — load the local plans
root from settings, then resolve the recipe.

### Local setting (`plans_path`)

All smarter-way skills share **one** user-local file. Do not add per-skill
config. Never commit real paths; never invent a home layout.

File (first existing):

- `$XDG_CONFIG_HOME/smarter-way/config.json`
- `$HOME/.config/smarter-way/config.json`

Key: `plans_path` — architecture-plans root (catalog `README.md` plus
`<slug>/README.md`). Copy [config.example.json](../../../config.example.json)
there to set it. Expand `~` and environment variables.

If `plans_path` is unset, skip the catalog scan; still use session attachments
and `arch_blueprint:` pointers found in files.

### Resolve

Use the first match confirmed by reading the files. Do not invent a slug.

1. **Session:** attached or named `.plan.md`; user/todo text naming a blueprint
   slug or `arch_blueprint:` path; conversation implementing a named recipe.
2. **Plan pointer:** plan frontmatter `arch_blueprint:` in the attached or named plan file.
3. **Blueprint pointer:** recipe frontmatter `cursor_plan:`, `arch_blueprint:`, `repository:`.
4. **Branch / catalog:** only if `plans_path` is set — current branch or PR
   title vs `$plans_path/README.md` and in-scope paths in candidate recipes.

Outcomes:

- **Plan and blueprint disagree** on architecture or locked decisions → record
  **P0** and review against the mismatch; do not pick the stale file silently.
- **No match** → write **No associated arch-blueprint** (and **plans_path
  unset** when catalog lookup was skipped for that reason) and continue
  ordinary review. If the diff is architecture/plan work with no recipe, add a
  **P1**.
- **Match** → the rest of this section applies.

### Goals and gates

Making sure **all the goals are met** and **all the gates pass** is part of
this review, not an optional appendix. Unmet in-scope goals and unrun/failed
gates for shipped work are merge blockers (**P0**) → **Request changes**.

Read the blueprint (and matching plan). Extract:

| Kind | Where |
|------|--------|
| Goals | Outcome, Definition of done, locked decisions, phase objectives and exit criteria for phases in this ship |
| Gates | Each phase Checkpoint (Smoke, Regression, E2E), Verification record, human/canary lines |

Rules:

1. **Goals.** Every in-scope DoD item and locked decision for this ship must
   be true in the diff. Unchecked `[ ]` on shipped work is **P0**. Out of
   scope stays out of scope only if the blueprint says so **and** this review
   is not shipping that phase.
2. **Gates.** For every shipped phase, smoke, regression, and E2E must have
   actually run and passed. `PENDING`, unchecked boxes, and "we'll canary
   later" are **P0**. Re-run named local commands when practical and record
   command + result in the Gates table. Do not rewrite `PENDING` to PASS.
3. **Smoke is not E2E.** `--help`, `--check-only`, and mocked unit tests do
   not satisfy an E2E line (frozen cycle, old/new parity, production canary).
   Tests must assert the contract the gate names, not a fallback that hides a
   miss.
4. **Cannot run.** Stop and say so; record the gate as unrun. Do not waive it
   or Approve.

## 4. Review dimensions

Evaluate every changed file against these areas. Skip areas that do not apply.
Read surrounding code when hunks alone are insufficient to judge intent.

1. **Correctness** — logic bugs, edge cases, race conditions, error paths, off-by-one, null/undefined handling
2. **Security** — injection, authz gaps, secret leakage, unsafe defaults, SSRF, path traversal, missing input validation
3. **Maintainability** — naming, function size, duplication, layering, coupling, dead code
4. **Tests** — coverage of new behavior, clarity, meaningful assertions vs implementation details; note gaps
5. **Style & conventions** — match existing repo patterns (imports, types, error handling, naming)
6. **Performance** — only when the change touches hot paths or data access; avoid speculative nitpicks
7. **Blueprint goals & gates** — when a recipe is associated (§3)
8. **Code smells** — the §2 baseline, matched against the diff

## 5. Parallel review lanes

Use a **lane** for an independent question. Select only lanes the diff makes
live, then launch every selected lane in one parallel dispatch. This replaces a
fixed two-agent split: a small ordinary diff uses two compact reviews, while a
risky or broad change gets the extra independent scrutiny it needs.

### Build the dispatch card

Before dispatching, make one compact card containing:

- the exact diff command and merge-base/range;
- changed-file manifest (path, status, changed-line count, and a short role);
- standards-source paths;
- blueprint and plan paths when present;
- each lane's assigned paths and question.

Do not paste the full diff, whole standards files, or whole blueprint into
every prompt. Sub-agents share the checkout: instruct them to run the supplied
diff command, read only their assigned hunks plus necessary neighbours, and
open only the cited standards or spec sections. Paste a source excerpt only
when it is unavailable in the checkout. This makes the dispatch card the
single source of shared review context and prevents N copies of a large diff.

### Select lanes

| Lane | Covers | Run when |
|------|--------|----------|
| Behavior | Correctness and tests | Always |
| Standards | Maintainability, style, conventions, and §2 smells | Always |
| Security | Security | The diff crosses a trust boundary: auth/authz, secrets, user-controlled input, filesystem/network/process access, serialization, permissions, or dependency/configuration security |
| Performance | Performance | The diff changes a hot path, query, loop over unbounded data, cache, rendering path, queue, or data-access pattern |
| Blueprint | Blueprint goals, gates, and spec scope | An associated blueprint or plan exists |

Record inactive lanes as `not applicable` in the axis summary; do not spend an
agent on them. If no associated blueprint exists, record Blueprint as `no
associated blueprint`, rather than spawning a speculative spec review.

### Batch large lanes

One lane normally gets one agent. Split a lane only when its assigned scope is
larger than roughly 12 changed files or 800 changed lines, and split by
dependency cluster (feature, package, or call chain), never arbitrary file
count. Give each batch its own paths and call out shared interfaces to inspect.

Keep a lane to four batches. If it is still too large, first narrow to changed
production code and its directly affected tests, then have the parent review
the remaining integration seams. More agents without a narrower question are
duplicate context spend, not more coverage.

### Common brief

Every sub-agent receives the dispatch card and this contract:

> Inspect only the assigned lane and paths, but read direct callers, callees,
> and tests when needed to prove a finding. Return findings only: `P0|P1|P2`,
> `file:line`, one-sentence impact, and one-sentence fix or missing test.
> Cite the relevant code, standard, or spec line. Do not repeat the diff, give
> praise, or report speculative concerns. Return `none found` when clean.
> Stay under 250 words per batch.

Add the lane-specific question below. The parent owns severity normalization
and the final report, so agents should state evidence rather than debate other
lanes or merge recommendations.

**Behavior:** *"Find observable behavior that is wrong, incomplete, or
regresses on edge/error/concurrency paths. Check whether changed behavior has
meaningful tests that assert its contract, including failure cases where
relevant."*

**Standards:** *"Find documented-standard violations and maintainability,
style, or §2 smell issues. Cite the standard file and rule. Documented
violations may be hard findings; smells are always labelled judgement calls,
and repo standards override the smell baseline. Ignore tooling-enforced rules."*

**Security:** *"Trace attacker-controlled data and privilege boundaries. Find
concrete injection, authorization, secret, unsafe-default, SSRF, path,
deserialization, dependency, or validation flaws introduced by this diff."*

**Performance:** *"Check changed execution and data-access paths for concrete
avoidable work, unbounded growth, query amplification, cache regressions, or
blocking behavior. Report only evidence-backed regressions."*

**Blueprint:** *"Check every in-scope goal, locked decision, and shipped gate
against the diff and verification evidence. Quote the blueprint or plan line.
Report missing/partial requirements, scope creep, incorrect implementations,
and each unrun, pending, or failed shipped gate."*

## 6. Aggregate

Deduplicate reports that identify the same root cause; retain every applicable
axis in the finding's `Axis` field rather than counting it repeatedly. Verify
each reported location and normalize severity using the table below. Then sort
the single findings rollup P0, P1, P2 while retaining the side-by-side axis
summary. Never choose a single winning axis — severity prioritizes work; it
does not rerank or erase the independent reviews. End with one line per axis:
finding count and worst issue (if any), including lanes that were not
applicable.

## Severity

| Level | Meaning |
|-------|---------|
| P0 | Must fix before merge — bugs, security holes, data loss risk, unmet shipped goals, unrun/failed gates |
| P1 | Should fix — likely problems, missing critical tests, fragile design, architecture work with no blueprint |
| P2 | Nice to have — style, minor refactors, optional test improvements |

Surface P0 and P1 in the summary. Mention P2 only when few or when grouped
briefly.

## Output format

```markdown
# Code review: [short title]

## Summary
[1–3 sentences: overall quality and merge recommendation]

## Blueprint
[Slug + path, or "No associated arch-blueprint" (+ "plans_path unset" when
catalog lookup was skipped for that reason)]
[Plan vs blueprint: in sync / mismatch]

### Goals
| Goal | Met? | Evidence |
|------|------|----------|
| ... | yes/no | file, test, or DoD item |

### Gates
| Phase | Smoke | Regression | E2E | Result |
|-------|-------|------------|-----|--------|
| ... | cmd + pass/fail/PENDING/unrun | ... | ... | ... |

## Findings
| Sev | Axis | Location | Finding |
|-----|------|----------|---------|
| P0  | Security | path:line | ... |
| P1  | Standards | path:line | ... |

## Axis summary
| Axis | Findings | Worst |
|------|----------|-------|
| Behavior | n | P_ file:line — one clause, or "—" |
| Standards | n | ... |
| Security | n / not applicable | ... |
| Performance | n / not applicable | ... |
| Blueprint | n / no associated blueprint | ... |

## Tests
[What is covered, what is missing, verdict]

## Merge recommendation
**Approve** / **Approve with fixes** / **Request changes** — one sentence why.
```

Rules:

- Every finding needs `file:line` (or `file` if line unknown). Blueprint gaps
  may use `arch-blueprints/<slug>/README.md` plus section name.
- Sort findings by severity (P0 first).
- Be specific and actionable; avoid vague praise or generic advice.
- Do not rewrite the code unless the user asks.
- Do not **Approve** when any in-scope shipped goal is unmet or any shipped
  gate is unchecked, `PENDING`, unrun, or failed.

## Optional deep dives

Only when requested, or when P0 security/bug risk warrants a second pass and
the user has not said "quick review":

- Bugs / logic → `bugbot` subagent (see `review-bugbot` skill)
- Security only → `security-review` subagent (see `review-security` skill)

## Out of scope

- Applying fixes or opening commits unless explicitly asked
- Force checkout or stash without user confirmation
- Reviewing unrelated files outside the diff scope
- Waiving blueprint gates or marking `PENDING` evidence as passed
