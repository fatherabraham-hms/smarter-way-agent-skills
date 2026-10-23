
```python
# Bad: one remote call per item.
for order in orders:
    order.customer = await customers.get(order.customer_id)

# Better: one bounded batch and one lookup.
ids = {order.customer_id for order in orders}
customers_by_id = await customers.get_many(ids)
for order in orders:
    order.customer = customers_by_id[order.customer_id]
```

Flag the bad form when `orders` can grow and the client supports batching.
