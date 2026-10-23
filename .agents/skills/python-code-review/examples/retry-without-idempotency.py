
```python
# Bad: a retry can create the same order twice.
for attempt in range(3):
    await client.post("/orders", json=order)

# Better: retry only transient failures and send an idempotency key.
await retry(
    lambda: client.post(
        "/orders",
        json=order,
        headers={"Idempotency-Key": order.id},
    ),
    retries=3,
    retry_on=(TimeoutError, TransientHTTPError),
)
```

Check that the server honors the key. A retry without idempotency is safe only
for a read or a fully idempotent write.
