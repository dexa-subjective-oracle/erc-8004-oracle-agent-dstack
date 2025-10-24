import json
from pathlib import Path

from src.utils.contract_loader import extract_contract_addresses


def test_extract_contract_addresses(tmp_path: Path):
    data = {
        "transactions": [
            {"contractName": "IdentityRegistry", "contractAddress": "0xABC"},
            {"contractName": "TEERegistry", "contractAddress": "0xDEF"},
            {"contractName": "Other", "contractAddress": "0x123"}
        ]
    }
    result = extract_contract_addresses(data)
    assert result["IdentityRegistry"] == "0xABC"
    assert result["TEERegistry"] == "0xDEF"
    assert "Other" in result
