
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
