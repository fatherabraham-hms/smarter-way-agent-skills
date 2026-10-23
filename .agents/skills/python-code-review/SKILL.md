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
- **Amplification:** Find queries, network calls, serialization, locks, or
  expensive parsing inside loops. Check for N+1 behavior and O(n²) scans.
  Prefer one batch plus a `dict` or `set` when the data contract allows it.
- **Async safety:** Find blocking file, network, subprocess, or CPU work in
  `async def`. Check task ownership, cancellation, cleanup, timeouts, and
  bounded concurrency. Use `TaskGroup` or an equivalent owner. Do not use
  unbounded `gather` for user-controlled work.
- **Resource lifetime:** Create clients, engines, pools, and workers at the
  application boundary. Close them with `with`, `async with`, or a lifecycle
  hook. Do not create a connection or HTTP client per item or request unless
  the design requires isolation.
- **Data access:** Check query shape, selected columns, indexes, transaction
  scope, pagination, eager loading, and connection-pool limits. Flag database
  or remote work hidden in property access or serialization.
- **State:** Find module globals, mutable singletons, cross-request state, and
  caches without size, expiry, invalidation, or ownership. Check thread and
  process behavior before accepting shared state.
- **Boundaries:** Keep routes, handlers, and CLI adapters thin. Keep domain
  rules independent from frameworks, storage, and transport. Inject I/O at a
  composition boundary. Flag import-time I/O and hidden dependencies.
- **API shape:** Flag boolean flag soup, optional-field bags, primitive domain
  identifiers, ambiguous mutation, and interfaces that expose more state than
  callers need. Prefer explicit variants, immutable values, and small
  `Protocol` boundaries.

### 2. Python correctness and known bad patterns

- Catch specific exceptions. Preserve cause with `raise NewError(...) from err`.
  Do not catch `BaseException`, swallow errors, or classify by message text.
- Preserve cancellation. `CancelledError` must reach the task owner after
  cleanup. Do not convert cancellation into success.
- Use runtime checks for runtime contracts. Do not use `assert` for input,
  authorization, or data validity.
- Make invalid states hard to construct. Prefer frozen dataclasses for values,
  tagged variants for modes, `NewType` for domain IDs, and `Protocol` for
  replaceable capabilities. Use `assert_never` when variants must be closed.
- Derive state from its source fields. Do not store mirror flags. Use aware
  datetimes. Use a private sentinel when `None` is a valid value.
- Match annotations to runtime values. Replace `Any`, unjustified `cast`, and
  `# type: ignore` with precise types or a boundary adapter.
- Use immutable input and return-new contracts when callers share data. Use
  mutation only when the contract is explicit and local.
- Treat optimization as conditional. A list comprehension, cache, or regex
  change needs a workload reason. Prefer the clearer form when the path is not
  measured or hot.
- Prefer `dict` and `set` membership, `str.join`, simple comprehensions, and
  generators when they make one-pass work clear. Do not report a micro-pattern
  without a workload or clarity reason.

### 3. Hygiene and style

- Use one name for one concept. Rename stale or generic names when behavior
  changes.
- Remove dead imports, commented-out code, duplicate logic, import-time side
  effects, and speculative extension points.
- Keep public APIs typed. Document non-obvious contracts, failure behavior,
  units, ownership, and lifetime.
- Use structured logger fields or deferred formatting. Do not build log text
  when the log level will discard it.
- Keep tests at the owner boundary. Test observable behavior and credible
  regressions. Avoid assertion-free probes, copied expected values, broad
  mocks, and tests coupled to private call shape.
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

## Sources

This review combines patterns from these public references. Use the repository
code and project standards as the current source of truth.

- <https://github.com/ludo-technologies/python-best-practices>
- <https://github.com/nathan-gage/python-skills>
- <https://github.com/0xbigboss/claude-code>
