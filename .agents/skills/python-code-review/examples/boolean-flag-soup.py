
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
