
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
