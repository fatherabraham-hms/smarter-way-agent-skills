
```python
# Bad: broad type escape and a test that proves only a call shape.
def decode(payload: Any) -> Any:
    return cast(Any, json.loads(payload))

def test_calls_parser(mocker):
    parser = mocker.patch("app.parse")
    decode("{}")
    parser.assert_called_once()

# Better: validate at the boundary and assert the contract.
@dataclass(frozen=True)
class Message:
    kind: Literal["created"]
    id: str

def decode(payload: str) -> Message:
    value = json.loads(payload)
    if value.get("kind") != "created" or not isinstance(value.get("id"), str):
        raise ValueError("invalid message")
    return Message(kind="created", id=value["id"])

def test_decode_rejects_missing_kind():
    with pytest.raises(ValueError):
        decode('{"id": "x"}')
```

Check the real adapter and test owner before accepting or rejecting this shape.
