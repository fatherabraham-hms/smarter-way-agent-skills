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
- [ ] 5. Run dimensions checklist; spawn Standards + Spec sub-agents in parallel
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

## 5. Parallel sub-agents

Spawn both in a single message. Sub-agents have no other context — paste
inputs in full.

**Standards sub-agent.** Include: the full diff command and commit list; the
standards-source files found in §2; dimensions 3, 5, and the §2 smell baseline,
pasted in full.
Brief: *"Report, per file/hunk where relevant, (a) every place the diff
violates a documented standard: cite the standard (file + the rule); and (b)
any baseline smell you spot: name it and quote the hunk. Distinguish hard
violations from judgement calls: documented-standard breaches can be hard, but
baseline smells are always judgement calls, and a documented repo standard
overrides the baseline. Skip anything tooling enforces. Under 400 words."*

**Spec sub-agent.** The spec is the associated blueprint + matching plan (§3).
Include: the diff command and commit list; the path or fetched contents of the
spec.
Brief: *"Report: (a) requirements the spec asked for that are missing or
partial; (b) behaviour in the diff that wasn't asked for (scope creep);
(c) requirements that look implemented but where the implementation looks
wrong. Quote the spec line for each finding. Under 400 words."*

If there is no associated blueprint, skip the Spec sub-agent and note this in
the final report.

## 6. Aggregate

Report the axes side by side. End the findings with a one-line summary per
axis: total findings and the worst issue within that axis (if any). Never pick
a single winner across axes — that is the reranking the separation exists to
prevent.

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
| Standards | n | P_P file:line — one clause, or "—" |
| Spec | n | ... |
| [each review dimension] | ... | ... |

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
