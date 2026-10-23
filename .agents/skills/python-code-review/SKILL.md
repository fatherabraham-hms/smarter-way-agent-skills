---
name: python-code-review
description: >-
  Review Python changes for architecture, scalability, performance, and known
  bad patterns before style. Use for Python PRs, branches, diffs, or modules.
  Check async code, data access, queues, caches, API design, type safety, and
  code hygiene. Report evidence-backed findings with file and line locations.
paths:
  - "**/*.py"
  - "pyproject.toml"
  - "setup.py"
  - "requirements*.txt"
metadata:
  focus: architecture, scalability, performance, code hygiene
  python: ">=3.11 preferred"
---

# Python Code Review

Review changed code first. Read direct callers, callees, tests, configuration,
and the data path when the diff does not prove the behavior. Do not review a
rule in isolation. Check its counter-signal and the repository convention.

## Review order

1. Set the scope. Use the user-named range. Otherwise use the branch merge-base
   with `main` or `master`. Include only changed files and required neighbors.
2. Write a workload model. Record request volume, input size, fan-out, latency
   target, memory limit, concurrency, and failure behavior when known.
3. Trace one hot path from entry point to storage or external I/O. Count loops,
   queries, remote calls, allocations, tasks, locks, and retries.
4. Check architecture and scalability. Use the priority list below.
5. Check Python correctness, type safety, error handling, tests, and style.
6. Report only findings that have code evidence. Use `none found` for a clean
   area. A rule match is a review signal, not proof of a defect.

Done means every changed production path has an architecture, performance,
correctness, and hygiene decision, or an explicit `not applicable` result.

## Priority review list

### 1. Architecture and scalability

- **Bounds:** Find unbounded input, result sets, queues, retries, caches,
  recursion, task creation, and memory growth. Require a limit, pagination,
  streaming, backpressure, eviction, or an explicit workload bound.
- **Amplification:** Find queries, network calls, serialization, locks,
  repeated sorting, or expensive parsing inside loops. Check for N+1 behavior
  and O(n²) scans. Check row-wise dataframe loops and repeated full-frame
  copies. Prefer one batch plus a `dict` or `set` when the data contract
  allows it.
- **Async safety:** Find blocking file, network, subprocess, or CPU work in
  `async def`. Check task ownership, cancellation, cleanup, timeouts, and
  bounded concurrency. Use `TaskGroup` or an equivalent owner. Keep a
  reference to every background task. Close async generators and clients at
  the owner. Do not use unbounded `gather` for user-controlled work.
- **Resource lifetime:** Create clients, engines, pools, and workers at the
  application boundary. Close them with `with`, `async with`, or a lifecycle
  hook. Do not create a connection or HTTP client per item or request unless
  the design requires isolation.
- **Data access:** Check query shape, selected columns, indexes, pagination,
  eager loading, and connection-pool limits. Prefer keyset pagination for
  large ordered sets. Do not share a session or connection across requests or
  concurrent tasks. Flag database or remote work hidden in property access or
  serialization.
- **State:** Find module globals, mutable singletons, service locators,
  cross-request state, and caches without size, expiry, invalidation, or
  ownership. Keep mutable state in the narrowest scope. Use `contextvars` for
  request-scoped async context. Check cache stampede and thundering herd
  behavior on expiry. Check thread and process behavior before accepting
  shared state.
- **Boundaries:** Keep routes, handlers, and CLI adapters thin. Keep domain
  rules independent from frameworks, storage, and transport. Build the object
  graph once at a composition root and inject I/O there. Put pure rules in a
  pure core and side effects at the edge. Parse external data into a typed
  value at the edge before it enters the domain. Flag import-time I/O and
  hidden dependencies.
- **Dependency direction:** Imports point toward the domain. Domain code does
  not import framework, transport, or storage modules. Detect cycles. Use
  `TYPE_CHECKING` for type-only imports. Keep package `__init__.py` files
  light.
- **Failure isolation:** Every external call has a timeout. Retry only
  transient failures. Use bounded backoff with jitter and a rate limit. Make
  retries idempotent. Use a circuit breaker or load shed when a dependency
  stays down. Define the degraded behavior when a dependency is unavailable.
  Do not retry validation or authorization errors.
- **Transaction scope:** One transaction per use case. Do not commit inside
  helpers or dependency teardown. Roll back on failure. Keep slow external I/O
  outside the transaction when the contract allows it.
- **Configuration:** Load configuration once at startup into a typed object.
  Fail at startup on missing or invalid values. Keep secrets out of source and
  use a secret type.
- **Observability:** Emit structured logs with a correlation ID and propagate
  trace context. Add metrics for latency, error rate, queue depth, and
  saturation. Keep metric label cardinality bounded. Do not log secrets or
  personal data. Do not log per item on a hot path.
- **API compatibility:** Identify the public surface. Require a deprecation
  path for renames and removals. Do not change a public contract without a
  version or migration plan.
- **Concurrency:** Check thread and process safety. Keep lock scope small. Do
  not hold a lock across I/O. Define a lock order when a path takes more than
  one lock. Protect shared caches. Use atomic writes. Check for
  time-of-check/time-of-use races.
- **Design principles:** Each module has one reason to change. Add a new type
  or function for a new variant instead of editing a stable branch. Subtypes
  keep the base contract. Keep interfaces small. Use a method when behavior
  depends on instance state. Use a module function when it does not. Prefer
  the simplest design that meets the contract.
- **API shape:** Flag boolean flag soup, optional-field bags, primitive or
  stringly typed domain values, ambiguous mutation, and interfaces that
  expose more state than callers need. Prefer explicit variants, immutable
  values, small `Protocol` boundaries, keyword-only optional parameters, and
  a leading underscore for private names. Keep models flat. Do not wrap one
  field in an extra object. Do not reach into another module's private names.
  Do not require a hidden call order. Do not expose storage models as public
  API models.

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
- Check the repository's configured Ruff, formatter, type checker, and pytest
  commands. Do not report a style preference that the repository rejects.

## Finding rules

Report one root cause once. Deduplicate findings across files. Each finding
needs a severity, axis, location, evidence, impact, and fix.

| Severity | Use |
|---|---|
| P0 | Data loss, outage, security failure, broken cancellation, or a clear production failure |
| P1 | Likely scalability or correctness failure, unbounded growth, serious coupling, or missing critical proof |
| P2 | Hygiene issue, local design debt, or low-risk optimization |

Use P1 for architecture risk only when the changed path and workload support
the risk. Ask for a measurement or bound when evidence is incomplete. Do not
turn a preference into a blocker.

Return this compact report:

```markdown
# Python code review: [title]

## Summary
[One or two sentences. State the merge recommendation.]

## Findings
| Sev | Axis | Location | Evidence and impact | Fix |
|---|---|---|---|---|
| P1 | Performance | `pkg/file.py:42` | One query runs per item. 1,000 items cause 1,001 queries. | Batch the query and index by key. |

## Checks
| Axis | Result |
|---|---|
| Architecture and scalability | pass / findings / not applicable |
| Performance | pass / findings / not applicable |
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

### 1. N+1 I/O

```python
# Bad: one remote call per item.
for order in orders:
    order.customer = await customers.get(order.customer_id)

# Better: one bounded batch and one lookup.
ids = {order.customer_id for order in orders}
customers_by_id = await customers.get_many(ids)
for order in orders:
    order.customer = customers_by_id[order.customer_id]
```

Flag the bad form when `orders` can grow and the client supports batching.

### 2. Quadratic matching

```python
# Bad: O(n * m) work.
matches = [a for a in accounts if any(a.id == row.account_id for row in rows)]

# Better: O(n + m) membership checks.
row_account_ids = {row.account_id for row in rows}
matches = [a for a in accounts if a.id in row_account_ids]
```

Keep the original form when the collections are tiny by contract or when
ordering and duplicate semantics require it.

### 3. Unbounded async fan-out

```python
# Bad: user input controls task count. Tasks have no owner or limit.
results = await asyncio.gather(*(fetch(item) for item in items))

# Better: bound pending work and own cancellation.
async def fetch_all(items: Sequence[Item]) -> list[Result]:
    results: list[Result] = []
    remaining = iter(items)
    while batch := list(islice(remaining, 32)):
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(fetch(item)) for item in batch]
        results.extend(task.result() for task in tasks)
    return results
```

Also check whether `items` needs a maximum or a streaming producer.

### 4. Blocking work in async code

```python
# Bad: this blocks every task on the event loop.
async def load_report(path: str) -> bytes:
    return Path(path).read_bytes()

# Better: use an async API or isolate known blocking work.
async def load_report(path: str) -> bytes:
    return await asyncio.to_thread(Path(path).read_bytes)
```

For CPU-heavy work, check process workers and a bounded queue instead of
assuming a thread removes the bottleneck.

### 5. Materialization and bounds

```python
# Bad: materializes the full result set.
def total_cost(rows: Iterable[Row]) -> Decimal:
    values = [row.cost for row in rows]
    return sum(values, Decimal("0"))

# Better: stream when the caller does not need the values.
def total_cost(rows: Iterable[Row]) -> Decimal:
    return sum((row.cost for row in rows), Decimal("0"))
```

Do not replace a list when the caller needs reuse, random access, or a known
small collection.

### 6. Resource lifetime

```python
# Bad: creates a client for every request.
async def send(payload: Payload) -> Response:
    async with httpx.AsyncClient(timeout=5) as client:
        return await client.post(URL, json=payload.model_dump())

# Better: create one client in application lifespan and inject it.
async def send(client: httpx.AsyncClient, payload: Payload) -> Response:
    return await client.post(URL, json=payload.model_dump())
```

Check that the application closes the injected client and sets connect and
read timeouts.

### 7. Hidden architecture coupling

```python
# Bad: transport code owns business rules and storage construction.
@router.post("/orders")
async def create_order(data: OrderIn) -> OrderOut:
    repo = SqlOrderRepository(ENGINE)
    if data.total <= 0:
        raise HTTPException(400, "invalid total")
    return await repo.insert(data)

# Better: the adapter calls an injected use case.
@router.post("/orders")
async def create_order(data: OrderIn, use_case: CreateOrder) -> OrderOut:
    return await use_case.execute(data)
```

Flag the bad form when it prevents alternate storage, isolated tests, or a
consistent transaction boundary. Do not require layers without a real seam.

### 8. Illegal state modeling

```python
# Bad: unrelated fields and flags permit invalid combinations.
@dataclass
class Job:
    running: bool
    error: str | None = None
    result: bytes | None = None

# Better: each variant states its valid data.
@dataclass(frozen=True)
class Succeeded:
    result: bytes

@dataclass(frozen=True)
class Failed:
    error: str

Job = Succeeded | Failed
```

Use a discriminant when serialization or pattern matching needs an explicit
tag. Add `NewType("UserId", str)` when two string IDs must not mix.

### 9. Error and cancellation handling

```python
# Bad: hides the failure and may turn cancellation into success.
try:
    await operation()
except BaseException:
    return None

# Better: add context and let cancellation reach the owner.
try:
    await operation()
except OperationError as err:
    raise ServiceError("operation failed") from err
```

Catch `CancelledError` only to clean up, then re-raise it. Log the traceback
at the boundary that can act on the failure.

### 10. Boolean flag soup

```python
# Bad: callers can request contradictory modes.
def export(data, compact=False, encrypted=False, streamed=False): ...

# Better: make the mode explicit.
class ExportMode(Enum):
    COMPACT = "compact"
    ENCRYPTED = "encrypted"
    STREAMED = "streamed"

def export(data: Data, *, mode: ExportMode) -> bytes: ...
```

Use separate commands or variants when modes have different required data or
side effects. Do not replace every boolean with an enum without a real variant.

### 11. Cache and global state

```python
# Bad: unbounded process-local state has unclear ownership.
responses: dict[str, Response] = {}

def remember(key: str, response: Response) -> None:
    responses[key] = response
```

Flag this when keys or response sizes can grow, workers do not share state, or
stale data is unsafe. Use a bounded cache with an invalidation contract, or
inject a shared store with explicit ownership.

### 12. Hygiene and proof

```python
# Bad: broad type escape and a test that proves only a call shape.
def decode(payload: Any) -> Any:
    return cast(Any, json.loads(payload))

def test_calls_parser(mocker):
    parser = mocker.patch("app.parse")
    decode("{}")
    parser.assert_called_once()

# Better: validate at the boundary and assert the contract.
@dataclass(frozen=True)
class Message:
    kind: Literal["created"]
    id: str

def decode(payload: str) -> Message:
    value = json.loads(payload)
    if value.get("kind") != "created" or not isinstance(value.get("id"), str):
        raise ValueError("invalid message")
    return Message(kind="created", id=value["id"])

def test_decode_rejects_missing_kind():
    with pytest.raises(ValueError):
        decode('{"id": "x"}')
```

Check the real adapter and test owner before accepting or rejecting this shape.

### 13. Mutable default

```python
# Bad: every call shares one list.
def add_item(item: Item, items: list[Item] = []) -> list[Item]:
    items.append(item)
    return items

# Better: build a new list for each call.
def add_item(item: Item, items: Sequence[Item] | None = None) -> list[Item]:
    result = list(items) if items is not None else []
    result.append(item)
    return result
```

The same defect applies to mutable class attributes. Use `default_factory` for
dataclass fields.

### 14. Truthiness instead of None

```python
# Bad: a valid zero or empty string takes the default.
def label(value: str | None) -> str:
    return value or "unknown"

# Better: use None as the only missing signal.
def label(value: str | None) -> str:
    return "unknown" if value is None else value
```

Check each falsy value against the contract. A valid `0`, `False`, `""`, or
empty collection needs an explicit `is None` check.

### 15. Retry without idempotency

```python
# Bad: a retry can create the same order twice.
for attempt in range(3):
    await client.post("/orders", json=order)

# Better: retry only transient failures and send an idempotency key.
await retry(
    lambda: client.post(
        "/orders",
        json=order,
        headers={"Idempotency-Key": order.id},
    ),
    retries=3,
    retry_on=(TimeoutError, TransientHTTPError),
)
```

Check that the server honors the key. A retry without idempotency is safe only
for a read or a fully idempotent write.

## Sources

This review combines patterns from these public references. Use the repository
code and project standards as the current source of truth.

- <https://github.com/ludo-technologies/python-best-practices>
- <https://github.com/nathan-gage/python-skills>
- <https://github.com/0xbigboss/claude-code>
