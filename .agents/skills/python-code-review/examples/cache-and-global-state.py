
```python
# Bad: unbounded process-local state has unclear ownership.
responses: dict[str, Response] = {}

def remember(key: str, response: Response) -> None:
    responses[key] = response
```

Flag this when keys or response sizes can grow, workers do not share state, or
stale data is unsafe. Use a bounded cache with an invalidation contract, or
inject a shared store with explicit ownership.
