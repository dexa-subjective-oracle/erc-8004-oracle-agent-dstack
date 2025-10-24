"""Utilities for loading contract ABIs and deployment metadata."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENT_ROOT = PROJECT_ROOT / "erc-8004-oracle-agent-dstack"
AGENT_DEPLOYMENTS_DIR = AGENT_ROOT / "deployments"
ABI_DIR = AGENT_ROOT / "contracts" / "abis"
DEPLOYMENTS_DIR = PROJECT_ROOT / "contracts" / "deployments"
BROADCAST_ENV = "DEXA_BROADCAST_PATH"
DEPLOYMENT_ENV = "DEXA_DEPLOYMENT"
DEPLOYMENT_PATH_ENV = "DEXA_DEPLOYMENT_PATH"


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


def _resolve_deployment_path(name: Optional[str], path: Optional[str]) -> Path:
    if path:
        return Path(path).expanduser()

    env_path = os.getenv(DEPLOYMENT_PATH_ENV)
    if env_path:
        return Path(env_path).expanduser()

    deployment_name = name or os.getenv(DEPLOYMENT_ENV) or "base_sepolia"
    filename = deployment_name if deployment_name.endswith(".json") else f"{deployment_name}_deployment.json"

    # Search agent-local deployments first, then shared contracts repo
    for base in (AGENT_DEPLOYMENTS_DIR, DEPLOYMENTS_DIR):
        candidate = base / filename
        if candidate.exists():
            return candidate

    # Fall back to contracts/deployments even if missing to maintain error message upstream
    return DEPLOYMENTS_DIR / filename


def load_deployment(name: Optional[str] = None, path: Optional[str] = None) -> Dict[str, Any]:
    """Load deployment metadata (addresses + extras) for the given network."""
    deployment_path = _resolve_deployment_path(name, path)
    if not deployment_path.exists():
        raise FileNotFoundError(f"Deployment file not found: {deployment_path}")
    with deployment_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_deployment_addresses(name: Optional[str] = None, path: Optional[str] = None) -> Dict[str, str]:
    """Return contract address map from deployment metadata."""
    deployment = load_deployment(name=name, path=path)
    return deployment.get("contracts", {})


def load_deployment_metadata(name: Optional[str] = None, path: Optional[str] = None) -> Dict[str, Any]:
    """Return additional metadata (tee arch, verifier, etc.) from deployment file."""
    deployment = load_deployment(name=name, path=path)
    return deployment.get("metadata", {})
