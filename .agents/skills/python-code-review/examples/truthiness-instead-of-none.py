
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
