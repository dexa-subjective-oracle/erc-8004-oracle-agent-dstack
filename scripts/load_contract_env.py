#!/usr/bin/env python3
"""Load forge broadcast JSON and print export statements or .env entries."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.utils.contract_loader import load_broadcast, extract_contract_addresses


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Dexa broadcast file for env setup")
    parser.add_argument("broadcast", help="Path to run-latest.json")
    parser.add_argument("--format", choices=["env", "export"], default="export")
    args = parser.parse_args()

    broadcast = load_broadcast(args.broadcast)
    deploys = extract_contract_addresses(broadcast)

    env_map = {
        "IdentityRegistry": "IDENTITY_REGISTRY_ADDRESS",
        "TEERegistry": "TEE_REGISTRY_ADDRESS",
        "TeeOracle": "TEE_ORACLE_ADDRESS",
        "TeeOracleAdapter": "TEE_ORACLE_ADAPTER_ADDRESS",
    }

    for contract, env_name in env_map.items():
        address = deploys.get(contract)
        if not address:
            continue
        if args.format == "env":
            print(f"{env_name}={address}")
        else:
            print(f"export {env_name}={address}")


if __name__ == "__main__":
    main()
