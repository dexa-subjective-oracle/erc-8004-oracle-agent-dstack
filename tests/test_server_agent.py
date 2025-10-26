from typing import Dict

from src.templates.server_agent import ServerAgent


def _build_placeholder_agent() -> ServerAgent:
    # Bypass BaseAgent initialization for stateless helpers
    return ServerAgent.__new__(ServerAgent)  # type: ignore[misc]


def test_sanitize_ancillary_replaces_long_hex() -> None:
    agent = _build_placeholder_agent()
    long_hex = "0x" + "abc123" * 8  # 48 hex chars
    text = f"Check value {long_hex} in ancillary payload."

    sanitized, placeholders = agent._sanitize_ancillary(text)

    assert "__PLACEHOLDER_HEX_1__" in sanitized
    assert placeholders
    meta: Dict[str, str] = placeholders["__PLACEHOLDER_HEX_1__"]
    assert meta["value"] == long_hex
    assert meta["const"] == "PLACEHOLDER_HEX_1"
    assert meta["description"].startswith(long_hex[:10])


def test_restore_placeholders_round_trip() -> None:
    agent = _build_placeholder_agent()
    placeholder = "__PLACEHOLDER_HEX_1__"
    meta = {
        placeholder: {
            "value": "0x" + "ab" * 32,
            "description": "sample value",
            "const": "PLACEHOLDER_HEX_1",
        }
    }
    code_with_token = f"url = \"https://example/{placeholder}\""

    restored = agent._restore_placeholders(code_with_token, meta)

    assert placeholder not in restored
    assert meta[placeholder]["value"] in restored
