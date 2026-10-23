
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
