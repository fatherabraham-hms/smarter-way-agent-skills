---
name: compr-code-review
description: >-
  Comprehensive code review across correctness, security, maintainability,
  tests, and style for any repo. Use when the user asks for compr-code-review,
  comprehensive code review, full review, PR review, or review before merge.
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

## Review dimensions

Evaluate every changed file against these areas. Skip areas that do not apply.

1. **Correctness** — logic bugs, edge cases, race conditions, error paths, off-by-one, null/undefined handling
2. **Security** — injection, authz gaps, secret leakage, unsafe defaults, SSRF, path traversal, missing input validation
3. **Maintainability** — naming, function size, duplication, layering, coupling, dead code
4. **Tests** — coverage of new behavior, clarity, meaningful assertions vs implementation details; note gaps
5. **Style & conventions** — match existing repo patterns (imports, types, error handling, naming)
6. **Performance** — only when the change touches hot paths or data access; avoid speculative nitpicks

Read surrounding code when hunks alone are insufficient to judge intent.

## Severity

| Level | Meaning |
|-------|---------|
| P0 | Must fix before merge — bugs, security holes, data loss risk |
| P1 | Should fix — likely problems, missing critical tests, fragile design |
| P2 | Nice to have — style, minor refactors, optional test improvements |

Surface P0 and P1 in the summary. Mention P2 only when few or when grouped briefly.

## Output format

Use this structure:

```markdown
# Code review: [short title]

## Summary
[1–3 sentences: overall quality and merge recommendation]

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
- Every finding needs `file:line` (or `file` if line unknown).
- Sort findings by severity (P0 first).
- Be specific and actionable; avoid vague praise or generic advice.
- Do not rewrite the code unless the user asks.

## Workflow

```text
compr-code-review:
- [ ] 1. Determine diff scope
- [ ] 2. Read changed files + surrounding context
- [ ] 3. Run review dimensions checklist
- [ ] 4. Write structured report
- [ ] 5. Stop — do not fix unless asked
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
