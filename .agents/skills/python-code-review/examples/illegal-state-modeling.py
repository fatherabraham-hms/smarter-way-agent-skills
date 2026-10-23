
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
