
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
