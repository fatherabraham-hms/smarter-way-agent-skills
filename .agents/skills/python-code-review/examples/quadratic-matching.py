
```python
# Bad: O(n * m) work.
matches = [a for a in accounts if any(a.id == row.account_id for row in rows)]

# Better: O(n + m) membership checks.
row_account_ids = {row.account_id for row in rows}
matches = [a for a in accounts if a.id in row_account_ids]
```

Keep the original form when the collections are tiny by contract or when
ordering and duplicate semantics require it.
