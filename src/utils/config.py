"""Environment helpers for Dexa contract integration."""

from __future__ import annotations

import os
from typing import Dict, Optional

from .contract_loader import load_broadcast, extract_contract_addresses

CONTRACT_ENV_VARS = {
    "IdentityRegistry": "IDENTITY_REGISTRY_ADDRESS",
    "TEERegistry": "TEE_REGISTRY_ADDRESS",
    "TeeOracle": "TEE_ORACLE_ADDRESS",
    "TeeOracleAdapter": "TEE_ORACLE_ADAPTER_ADDRESS",
    "DstackOffchainVerifier": "TEE_VERIFIER_ADDRESS",
}


def load_contract_addresses(broadcast_path: Optional[str] = None) -> Dict[str, str]:
    """Return a mapping of env var names to addresses, optionally hydrating from a broadcast file."""
    resolved: Dict[str, str] = {}

    # Start with environment variables
    for contract, env_name in CONTRACT_ENV_VARS.items():
        value = os.getenv(env_name)
        if value:
            resolved[env_name] = value

    if broadcast_path:
        _merge_broadcast(resolved, broadcast_path)
    elif os.getenv("DEXA_BROADCAST_PATH"):
        _merge_broadcast(resolved, os.getenv("DEXA_BROADCAST_PATH") or "")

    missing = [env for env in CONTRACT_ENV_VARS.values() if env not in resolved]
    if missing:
        raise RuntimeError(f"Missing contract addresses for: {', '.join(missing)}. Set env vars or provide broadcast file.")

    return resolved


def _merge_broadcast(dest: Dict[str, str], path: str) -> None:
    broadcast = load_broadcast(path)
    contracts = extract_contract_addresses(broadcast)
    for contract, env_name in CONTRACT_ENV_VARS.items():
        address = contracts.get(contract)
        if address and env_name not in dest:
            dest[env_name] = address
