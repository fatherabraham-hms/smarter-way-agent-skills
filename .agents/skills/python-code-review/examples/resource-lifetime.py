
```python
# Bad: creates a client for every request.
async def send(payload: Payload) -> Response:
    async with httpx.AsyncClient(timeout=5) as client:
        return await client.post(URL, json=payload.model_dump())

# Better: create one client in application lifespan and inject it.
async def send(client: httpx.AsyncClient, payload: Payload) -> Response:
    return await client.post(URL, json=payload.model_dump())
```

Check that the application closes the injected client and sets connect and
read timeouts.
