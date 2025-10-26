from typing import Any, Callable

from src.agent.oracle_client import OracleClient


class DummyCall:
    def __init__(self, value: Any):
        self._value = value

    def call(self) -> Any:
        return self._value


class DummyFunctions:
    def __init__(self, response_factory: Callable[[], Any]):
        self._response_factory = response_factory

    def getRequest(self, *_args) -> DummyCall:
        return DummyCall(self._response_factory())


def _build_request_tuple(include_resolver: bool) -> list[Any]:
    base = [
        "0x1111111111111111111111111111111111111111",
        "0x2222222222222222222222222222222222222222",
        0,
        123,
        b"\x01" * 32,
        b"ancillary-data",
        False,
        0,
        b"\x02" * 32,
    ]
    if include_resolver:
        base.append("0x3333333333333333333333333333333333333333")
    return base


def test_fetch_request_trims_extra_field() -> None:
    client = OracleClient.__new__(OracleClient)  # type: ignore[misc]
    response = _build_request_tuple(include_resolver=True)
    client.oracle_contract = type(
        "DummyContract",
        (),
        {"functions": DummyFunctions(lambda: response)},
    )()
    client._has_get_request = True  # type: ignore[attr-defined]
    client._call_requests_with_fallback = lambda *_: response  # type: ignore[attr-defined]

    request_id = b"\x10" * 32
    result = client.fetch_request(request_id)

    assert result.request_id == request_id
    assert result.requester == response[0]
    assert result.ancillary_data == response[5]
    assert result.evidence_hash == response[8]


def test_fetch_request_uses_fallback_tuple() -> None:
    client = OracleClient.__new__(OracleClient)  # type: ignore[misc]
    response = tuple(_build_request_tuple(include_resolver=True))
    client._has_get_request = False  # type: ignore[attr-defined]
    client._call_requests_with_fallback = lambda *_: response  # type: ignore[attr-defined]

    request_id = b"\x20" * 32
    result = client.fetch_request(request_id)

    assert result.request_id == request_id
    assert result.requester == response[0]
    assert result.evidence_hash == response[8]
