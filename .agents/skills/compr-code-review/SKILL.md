---
name: compr-code-review
description: >-
  Comprehensive code review across correctness, security, maintainability,
  tests, style, and associated arch-blueprint goals and gates. Use when the
  user asks for compr-code-review, comprehensive code review, full review, PR
  review, or review before merge.
disable-model-invocation: true
---

# Comprehensive Code Review

Review code changes in the **current repo** before merge or after a feature is done.
Works in any project — infer language, framework, and conventions from the diff and surrounding code.

## Scope

Determine what to review:

| User intent | Diff scope |
|-------------|------------|
| Default | Branch changes vs merge-base with default branch (`main`/`master`) |
| Uncommitted / dirty / WIP | Staged + unstaged only |
| Specific PR or branch | Check out target branch first; then branch changes |

Gather context in parallel:

```bash
git status -sb
git diff --stat
git log --oneline -5
```

If the diff is empty, say so and stop.

## Arch-blueprint association (required)

Before scoring the diff, check whether an **arch-blueprint** belongs to this
session. Do **not** assume a machine-specific directory. Load the local plans
root from settings, then resolve the recipe.

### Local setting (`plans_path`)

Read user-local config only (never commit these paths; never invent a home
layout):

1. Env `COMPR_CODE_REVIEW_PLANS_PATH` — directory of architecture plans
   (catalog `README.md` plus `<slug>/README.md`).
2. Else JSON file, first existing:
   - `$COMPR_CODE_REVIEW_CONFIG`
   - `config.json` next to this `SKILL.md` (gitignored; copy from
     [config.example.json](config.example.json))
   - `$XDG_CONFIG_HOME/smarter-way/compr-code-review.json`
   - `$HOME/.config/smarter-way/compr-code-review.json`
3. Keys:
   - `plans_path` (required for catalog lookup) — architecture-plans root
   - `cursor_plans` (optional) — editor plan files (`.plan.md`)

Expand `~` and environment variables in those values. If `plans_path` is
unset, skip catalog scan; still use session attachments and `arch_blueprint:`
pointers found in files. Never commit `config.json`.

### Resolve

Use the first match that you can confirm by reading the files. Do not invent a
slug.

1. **Session:** attached or named `.plan.md`; user/todo text naming a blueprint
   slug or `arch_blueprint:` path; conversation implementing a named recipe.
2. **Plan pointer:** matching plan frontmatter `arch_blueprint:` (in the
   attached/named plan, or under `cursor_plans` if that setting exists).
3. **Blueprint pointer:** recipe frontmatter `cursor_plan:`, `arch_blueprint:`,
   `repository:`.
4. **Branch / catalog:** only if `plans_path` is set — current branch or PR
   title vs `$plans_path/README.md` and in-scope paths in candidate recipes.

If the plan and blueprint disagree on architecture or locked decisions, record
that as **P0** and review against the mismatch — do not pick the stale file
silently.

If none match, write **No associated arch-blueprint** (and **plans_path unset**
when catalog lookup was skipped for that reason) and continue ordinary review.
If the diff is architecture/plan work with no recipe, add a **P1**.

### When a blueprint is associated

Making sure **all the goals are met** and **all the gates pass** is part of
this review, not an optional appendix. Unmet in-scope goals and unrun/failed
gates for work being shipped are merge blockers (**P0**). **Request changes.**

Read the blueprint (and matching plan). Extract:

| Kind | Where |
|------|--------|
| Goals | Outcome, Definition of done, locked decisions, phase objectives and exit criteria for phases in this ship |
| Gates | Each phase Checkpoint (Smoke, Regression, E2E), Verification record, human/canary lines |

Then:

1. **Goals.** Every in-scope DoD item and locked decision for this ship must
   be true in the diff. Unchecked `[ ]` on shipped work is **P0**. Out of
   scope stays out of scope only if the blueprint says so **and** this review
   is not shipping that phase.
2. **Gates.** For every shipped phase, smoke, regression, and E2E must have
   actually run and passed. `PENDING`, unchecked boxes, and “we’ll canary
   later” are **P0**. Re-run named local commands when practical; record
   command + result. Do not rewrite `PENDING` to PASS.
3. **Smoke is not E2E.** `--help`, `--check-only`, and mocked unit tests do
   not satisfy an E2E line (frozen cycle, old/new parity, production canary).
   Tests must assert the contract the gate names, not a fallback that hides a
   miss.
4. **Cannot run.** Stop and say so. Do not waive the gate or Approve.

## Review dimensions

Evaluate every changed file against these areas. Skip areas that do not apply.

1. **Correctness** — logic bugs, edge cases, race conditions, error paths, off-by-one, null/undefined handling
2. **Security** — injection, authz gaps, secret leakage, unsafe defaults, SSRF, path traversal, missing input validation
3. **Maintainability** — naming, function size, duplication, layering, coupling, dead code
4. **Tests** — coverage of new behavior, clarity, meaningful assertions vs implementation details; note gaps
5. **Style & conventions** — match existing repo patterns (imports, types, error handling, naming)
6. **Performance** — only when the change touches hot paths or data access; avoid speculative nitpicks
7. **Blueprint goals & gates** — when a recipe is associated (section above)

Read surrounding code when hunks alone are insufficient to judge intent.

## Severity

| Level | Meaning |
|-------|---------|
| P0 | Must fix before merge — bugs, security holes, data loss risk, unmet shipped goals, unrun/failed gates |
| P1 | Should fix — likely problems, missing critical tests, fragile design, architecture work with no blueprint |
| P2 | Nice to have — style, minor refactors, optional test improvements |

Surface P0 and P1 in the summary. Mention P2 only when few or when grouped briefly.

## Output format

Use this structure:

```markdown
# Code review: [short title]

## Summary
[1–3 sentences: overall quality and merge recommendation]

## Blueprint
[Slug + path, or "No associated arch-blueprint"]
[Plan vs blueprint: in sync / mismatch]

### Goals
| Goal | Met? | Evidence |
|------|------|----------|
| ... | yes/no | file, test, or DoD item |

### Gates
| Phase | Smoke | Regression | E2E | Result |
|-------|-------|------------|-----|--------|
| ... | cmd + pass/fail/PENDING | ... | ... | ... |

## Findings

| Sev | Location | Finding |
|-----|----------|---------|
| P0  | path:line | ... |
| P1  | path:line | ... |

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

## Workflow

```text
compr-code-review:
- [ ] 1. Determine diff scope
- [ ] 2. Resolve associated arch-blueprint (or record none)
- [ ] 3. If associated: check all goals met and all gates pass
- [ ] 4. Read changed files + surrounding context
- [ ] 5. Run review dimensions checklist
- [ ] 6. Write structured report
- [ ] 7. Stop — do not fix unless asked
```

### Optional deep dives

When the user wants focused subagent review on top of this pass:

- Bugs / logic → launch `bugbot` subagent (see `review-bugbot` skill)
- Security only → launch `security-review` subagent (see `review-security` skill)

Run subagents only when requested or when P0 security/bug risk warrants a second pass and the user has not said "quick review."

## Out of scope

- Applying fixes or opening commits unless explicitly asked
- Force checkout or stash without user confirmation
- Reviewing unrelated files outside the diff scope
- Waiving blueprint gates or marking `PENDING` evidence as passed
