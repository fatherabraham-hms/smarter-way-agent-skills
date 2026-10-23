---
name: python-code-review
description: >-
  Review Python changes for known bad patterns, type safety, and code hygiene.
  Use for Python PRs, branches, diffs, or modules. Check async code, data
  access, API design, error handling, and test quality. Report evidence-backed
  findings with file and line locations. Defer architecture, scalability, and
  performance to the compr-code-review skill.
paths:
  - "**/*.py"
  - "pyproject.toml"
  - "setup.py"
  - "requirements*.txt"
metadata:
  focus: correctness, type safety, code hygiene
  python: ">=3.11 preferred"
---

# Python Code Review

Review changed code first. Read direct callers, callees, tests, configuration,
and the data path when the diff does not prove the behavior. Do not review a
rule in isolation. Check its counter-signal and the repository convention.

## Review order

1. Set the scope. Use the user-named range. Otherwise use the branch merge-base
   with `main` or `master`. Include only changed files and required neighbors.
2. Check Python correctness, type safety, error handling, tests, and style.
3. Report only findings that have code evidence. Use `none found` for a clean
   area. A rule match is a review signal, not proof of a defect.

Done means every changed production path has a correctness, type safety, and
hygiene decision, or an explicit `not applicable` result.

## Priority review list

### 1. Python correctness and known bad patterns

- Catch specific exceptions. Preserve cause with `raise NewError(...) from err`.
  Use bare `raise` to re-raise. Use `!r` for identifiers in error text.
  Translate infrastructure errors at the boundary. Keep a new exception under
  an existing base when callers already catch that base. Do not catch
  `BaseException`, swallow errors, log and re-raise at every layer, or
  classify by message text.
- Do not return `None` to signal an error that the caller must guess. Raise a
  typed error or return an explicit result type. Do not use exceptions for
  expected control flow.
- Preserve cancellation. `CancelledError` must reach the task owner after
  cleanup. Do not convert cancellation into success.
- Use runtime checks for runtime contracts. Do not use `assert` for input,
  authorization, or data validity.
- Never use mutable defaults or mutable class attributes. Use `None` plus
  construction or `default_factory`.
- Use `is None` for optional checks. Do not rely on truthiness when `0`, `""`,
  `[]`, or `False` are valid values. Use `x or default` only when every falsy
  value means missing. Use `==` for values and `is` for identity.
- Reject `bool` before a numeric check when `True` and `False` are not valid
  numbers.
- Bind loop variables in closures. A lambda or callback created in a loop
  captures the last value.
- Make invalid states hard to construct. Prefer frozen dataclasses for values,
  tagged variants for modes, `NewType` for domain IDs, and `Protocol` for
  replaceable capabilities. Use `assert_never` when variants must be closed.
- Derive state from its source fields. Do not store mirror flags. Use aware
  datetimes. Use a private sentinel when `None` is a valid value.
- Use `Decimal` or integer minor units for money. Do not use `float` for
  currency. Do not use `datetime.utcnow()`.
- Match annotations to runtime values. Replace `Any`, unjustified `cast`, and
  `# type: ignore` with precise types or a boundary adapter. Use `X | None`,
  `list[str]`, `Literal`, `TypedDict`, `Final`, `ClassVar`, `TypeAlias`,
  `Protocol`, `Self`, `TypeGuard`, and `overload`. Use `Sequence` and
  `Mapping` for read-only parameters. Narrow with `isinstance`, not `hasattr`
  or a type name string. Do not add a runtime check for a value the type
  system already guarantees.
- Use immutable input and return-new contracts when callers share data. Use
  mutation only when the contract is explicit and local.
- Use `pathlib.Path` for filesystem paths. Specify the encoding for text I/O.
- Keep imports at the top of the file and static. Use absolute imports. Do not
  use `import *` or change `sys.path`. Do not run network, model, environment
  reads, or plugin registration at import time. Declare optional dependencies
  with an install hint. Keep `eval`, `exec`, and `pickle` away from untrusted
  data.
- Treat optimization as conditional. Profile the hot path before a rewrite.
  Add a benchmark or profile for a claimed optimization. Use `functools.cache`
  only on a pure function with a bounded key space. Use
  `functools.cached_property` only on an immutable instance with no
  thread-safety requirement. Compile a static regex at module scope. A list
  comprehension, cache, or regex change needs a workload reason. Prefer the
  clearer form when the path is not measured or hot.
- Prefer `dict` and `set` membership, `dict.get`, `str.join`, simple
  comprehensions, and generators when they make one-pass work clear. Do not
  report a micro-pattern without a workload or clarity reason.

### 2. Python correctness and known bad patterns

- Catch specific exceptions. Preserve cause with `raise NewError(...) from err`.
  Use bare `raise` to re-raise. Use `!r` for identifiers in error text.
  Translate infrastructure errors at the boundary. Keep a new exception under
  an existing base when callers already catch that base. Do not catch
  `BaseException`, swallow errors, log and re-raise at every layer, or
  classify by message text.
- Do not return `None` to signal an error that the caller must guess. Raise a
  typed error or return an explicit result type. Do not use exceptions for
  expected control flow.
- Preserve cancellation. `CancelledError` must reach the task owner after
  cleanup. Do not convert cancellation into success.
- Use runtime checks for runtime contracts. Do not use `assert` for input,
  authorization, or data validity.
- Never use mutable defaults or mutable class attributes. Use `None` plus
  construction or `default_factory`.
- Use `is None` for optional checks. Do not rely on truthiness when `0`, `""`,
  `[]`, or `False` are valid values. Use `x or default` only when every falsy
  value means missing. Use `==` for values and `is` for identity.
- Reject `bool` before a numeric check when `True` and `False` are not valid
  numbers.
- Bind loop variables in closures. A lambda or callback created in a loop
  captures the last value.
- Make invalid states hard to construct. Prefer frozen dataclasses for values,
  tagged variants for modes, `NewType` for domain IDs, and `Protocol` for
  replaceable capabilities. Use `assert_never` when variants must be closed.
- Derive state from its source fields. Do not store mirror flags. Use aware
  datetimes. Use a private sentinel when `None` is a valid value.
- Use `Decimal` or integer minor units for money. Do not use `float` for
  currency. Do not use `datetime.utcnow()`.
- Match annotations to runtime values. Replace `Any`, unjustified `cast`, and
  `# type: ignore` with precise types or a boundary adapter. Use `X | None`,
  `list[str]`, `Literal`, `TypedDict`, `Final`, `ClassVar`, `TypeAlias`,
  `Protocol`, `Self`, `TypeGuard`, and `overload`. Use `Sequence` and
  `Mapping` for read-only parameters. Narrow with `isinstance`, not `hasattr`
  or a type name string. Do not add a runtime check for a value the type
  system already guarantees.
- Use immutable input and return-new contracts when callers share data. Use
  mutation only when the contract is explicit and local.
- Use `pathlib.Path` for filesystem paths. Specify the encoding for text I/O.
- Keep imports at the top of the file and static. Use absolute imports. Do not
  use `import *` or change `sys.path`. Do not run network, model, environment
  reads, or plugin registration at import time. Declare optional dependencies
  with an install hint. Keep `eval`, `exec`, and `pickle` away from untrusted
  data.
- Treat optimization as conditional. Profile the hot path before a rewrite.
  Add a benchmark or profile for a claimed optimization. Use `functools.cache`
  only on a pure function with a bounded key space. Use
  `functools.cached_property` only on an immutable instance with no
  thread-safety requirement. Compile a static regex at module scope. A list
  comprehension, cache, or regex change needs a workload reason. Prefer the
  clearer form when the path is not measured or hot.
- Prefer `dict` and `set` membership, `dict.get`, `str.join`, simple
  comprehensions, and generators when they make one-pass work clear. Do not
  report a micro-pattern without a workload or clarity reason.

### 3. Hygiene and style

- Use one name for one concept. Rename stale or generic names when behavior
  changes. Prefer a specific name over `id` or `data`. Do not encode the type
  in the name with suffixes such as `_dict` or `_list`. Do not repeat the
  owner in an attribute name. Use upper-case names for module constants.
- Remove dead imports, commented-out code, duplicate logic, and speculative
  extension points.
- Use `any`, `all`, `enumerate`, and `zip` when they make intent clearer.
- Keep public APIs typed. Use Google-style docstrings. Document non-obvious
  contracts, failure behavior, units, ownership, and lifetime. Define the
  public surface with `__all__`.
- Use comments to explain why, not what. Remove a comment that restates the
  code.
- Use early returns and guard clauses to keep the happy path flat. Keep
  functions small enough to read in one screen. Prefer a readable loop over a
  deeply nested comprehension.
- Do not create a `utils.py` dumping ground or a class with many unrelated
  responsibilities. Put a helper beside its owner or in a named module.
- Prefer composition over inheritance for reuse. Use a property for a cheap
  computed value with no side effects. Use a method for work with side effects.
- Name repeated magic values and units in constants or types.
- Use structured logger fields or deferred formatting. Use
  `logger.exception` inside an `except` block. Do not build log text when the
  log level will discard it. Use logging, not `print`, in library code.
- Keep tests at the owner boundary. Test observable behavior and credible
  regressions. Control time, randomness, and IDs. Avoid assertion-free probes,
  copied expected values, broad mocks, and tests coupled to private call
  shape.
- Use event-based synchronization instead of sleeps. Make expected failures
  strict. Do not let `xfail` hide a regression.
- Check the repository's configured Ruff, formatter, type checks, and pytest
  commands. Do not report a style preference that the repository rejects.

## Finding rules

Report one root cause once. Deduplicate findings across files. Each finding
needs a severity, axis, location, evidence, impact, and fix.

| Severity | Use |
|---|---|
| P0 | Data loss, outage, security failure, broken cancellation, or a clear production failure |
| P1 | Likely correctness failure, unbounded growth, serious coupling, or missing critical proof |
| P2 | Hygiene issue, local design debt, or low-risk optimization |

Use P1 for a correctness risk only when the changed path and evidence support
it. Ask for a reproduction or bound when evidence is incomplete. Do not
turn a preference into a blocker.

Return this compact report:

```markdown
# Python code review: [title]

## Summary
[One or two sentences. State the merge recommendation.]

## Findings
| Sev | Axis | Location | Evidence and impact | Fix |
|---|---|---|---|---|
| P1 | Correctness | `pkg/file.py:42` | One query runs per item. 1,000 items cause 1,001 queries. | Batch the query and index by key. |

## Checks
| Axis | Result |
|---|---|
| Correctness and types | pass / findings / not applicable |
| Tests | pass / findings / not applicable |
| Hygiene and style | pass / findings / not applicable |

## Merge recommendation
**Approve** / **Approve with fixes** / **Request changes** - [reason].
```

## Lane boundaries

- Security defects belong to the security lane. Report a Python-specific
  security flaw only when the change introduces it and the security lane is
  not active.
- Test value belongs to the test-audit lane. Report a missing Python contract
  test, not a test-style preference.
- Fowler smells belong to the Standards lane. Report a Python-specific
  pattern here.
- Review the diff and its direct neighbors. Do not sweep stable code.
- Skip rules that configured tooling already enforces.

## Review examples

Use the examples as patterns. Adapt them to the repository and workload.

Examples moved to `.agents/skills/python-code-review/examples/`:

- `n-plus-one-io.py`
- `quadratic-matching.py`
- `unbounded-async-fanout.py`
- `blocking-async-code.py`
- `materialization-and-bounds.py`
- `resource-lifetime.py`
- `hidden-architecture-coupling.py`
- `illegal-state-modeling.py`
- `error-and-cancellation-handling.py`
- `boolean-flag-soup.py`
- `cache-and-global-state.py`
- `hygiene-and-proof.py`
- `mutable-default.py`
- `truthiness-instead-of-none.py`
- `retry-without-idempotency.py`

## Sources

This review combines patterns from these public references. Use the repository
code and project standards as the current source of truth.

- <https://github.com/ludo-technologies/python-best-practices>
- <https://github.com/nathan-gage/python-skills>
- <https://github.com/0xbigboss/claude-code>
