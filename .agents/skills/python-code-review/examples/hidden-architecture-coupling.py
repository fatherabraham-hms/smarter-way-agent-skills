
```python
# Bad: transport code owns business rules and storage construction.
@router.post("/orders")
async def create_order(data: OrderIn) -> OrderOut:
    repo = SqlOrderRepository(ENGINE)
    if data.total <= 0:
        raise HTTPException(400, "invalid total")
    return await repo.insert(data)

# Better: the adapter calls an injected use case.
@router.post("/orders")
async def create_order(data: OrderIn, use_case: CreateOrder) -> OrderOut:
    return await use_case.execute(data)
```

Flag the bad form when it prevents alternate storage, isolated tests, or a
consistent transaction boundary. Do not require layers without a real seam.
