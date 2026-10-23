
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
