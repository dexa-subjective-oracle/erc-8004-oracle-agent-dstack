"""Utilities for loading contract ABIs and deployment metadata."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

ABI_DIR = Path(__file__).resolve().parent.parent.parent / "contracts" / "abis"
BROADCAST_ENV = "DEXA_BROADCAST_PATH"


def load_abi(name: str) -> Dict[str, Any]:
    """Return the ABI json content for the given contract name."""
    path = ABI_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"ABI not found for {name} at {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    # Flatten to actual abi payload (Forge JSON includes metadata)
    if "abi" in data:
        return data["abi"]
    return data


def load_broadcast(path: Optional[str] = None) -> Dict[str, Any]:
    """Load broadcast artifacts from forge script output."""
    target = path or os.getenv(BROADCAST_ENV)
    if not target:
        raise RuntimeError("No broadcast path provided via argument or DEXA_BROADCAST_PATH")
    broadcast_path = Path(target)
    if not broadcast_path.exists():
        raise FileNotFoundError(f"Broadcast file not found: {broadcast_path}")
    with broadcast_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def extract_contract_addresses(broadcast: Dict[str, Any]) -> Dict[str, str]:
    """Parse the broadcast JSON produced by forge script and extract deployed addresses."""
    transactions = broadcast.get("transactions", [])
    deployments = {}
    for tx in transactions:
        contract_name = tx.get("contractName")
        address = tx.get("contractAddress")
        if contract_name and address:
            deployments[contract_name] = address
    return deployments
