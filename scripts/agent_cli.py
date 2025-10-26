#!/usr/bin/env python3
"""Command-line utilities for interacting with the Dexa agent stack."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import click
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.agent.base import AgentConfig, RegistryAddresses, AgentRole
from src.agent.tee_auth import TEEAuthenticator
from src.agent.tee_verifier import TEEVerifier
from src.templates.server_agent import ServerAgent
from src.utils.contract_loader import load_deployment


async def _build_agent() -> tuple[ServerAgent, TEEVerifier, str]:
    load_dotenv()

    domain = os.getenv("AGENT_DOMAIN", "localhost:8000")
    salt = os.getenv("AGENT_SALT", "local-development-salt")
    use_tee_auth = os.getenv("USE_TEE_AUTH", "false").lower() == "true"

    resolver_private_key = os.getenv("RESOLVER_PRIVATE_KEY") or os.getenv("DEPLOYER_PRIVATE_KEY")
    if not use_tee_auth and not resolver_private_key:
        raise RuntimeError("RESOLVER_PRIVATE_KEY must be set when USE_TEE_AUTH=false")

    tee_auth = TEEAuthenticator(
        domain=domain,
        salt=salt,
        use_tee=use_tee_auth,
        private_key=None if use_tee_auth else resolver_private_key
    )
    address = await tee_auth.derive_address()

    chain_id = int(os.getenv("CHAIN_ID", "84532"))
    rpc_url = os.getenv("RPC_URL", "http://127.0.0.1:8545")

    deployment_payload: Dict[str, Any] = {}
    try:
        deployment_payload = load_deployment()
    except FileNotFoundError:
        deployment_payload = {}

    deployment_contracts = deployment_payload.get("contracts", {})

    registries = RegistryAddresses(
        identity=os.getenv("IDENTITY_REGISTRY_ADDRESS", deployment_contracts.get("IdentityRegistry", "")),
        reputation=os.getenv("REPUTATION_REGISTRY_ADDRESS"),
        validation=os.getenv("VALIDATION_REGISTRY_ADDRESS"),
        tee_verifier=os.getenv("TEE_VERIFIER_ADDRESS", deployment_contracts.get("DstackOffchainVerifier")),
        tee_oracle=os.getenv("TEE_ORACLE_ADDRESS", deployment_contracts.get("TeeOracle")),
        tee_oracle_adapter=os.getenv("TEE_ORACLE_ADAPTER_ADDRESS", deployment_contracts.get("TeeOracleAdapter"))
    )

    agent_config = AgentConfig(
        domain=domain,
        salt=salt,
        role=AgentRole.SERVER,
        rpc_url=rpc_url,
        chain_id=chain_id,
        use_tee_auth=use_tee_auth,
        private_key=tee_auth.private_key
    )

    agent = ServerAgent(agent_config, registries)

    tee_registry_addr = os.getenv("TEE_REGISTRY_ADDRESS", deployment_contracts.get("TEERegistry"))
    if not tee_registry_addr:
        raise RuntimeError("TEE_REGISTRY_ADDRESS must be set")

    tee_verifier = TEEVerifier(
        w3=agent._registry_client.w3,
        tee_registry_address=tee_registry_addr,
        account=tee_auth.account,
        verifier_address=os.getenv("TEE_VERIFIER_ADDRESS", deployment_contracts.get("DstackOffchainVerifier")),
        mode=os.getenv("TEE_REGISTRATION_MODE", "manual"),
        tee_arch_label=os.getenv("TEE_ARCH_LABEL", "INTEL_TDX"),
        manual_config_uri=os.getenv("TEE_MANUAL_CONFIG_URI", "manual://dev")
    )

    return agent, tee_verifier, address


@click.group()
def cli() -> None:
    """Manage the local Dexa oracle agent."""


@cli.command()
def status() -> None:
    """Show agent registration and resolver status."""

    async def _run() -> None:
        agent, _, address = await _build_agent()
        agent_id = await agent.register()
        print(f"Agent address: {address}")
        print(f"Agent ID: {agent_id}")
        if agent.oracle_client:
            pending = agent.oracle_client.pending_requests()
            print(f"Pending requests: {len(pending)}")
        else:
            print("Oracle client not configured (missing TEE_ORACLE_ADDRESS)")

    asyncio.run(_run())


@cli.command()
@click.option(
    "--price-override",
    type=int,
    default=None,
    help="Force a specific settlement price (omit to use AI resolution)"
)
def run(price_override: Optional[int]) -> None:
    """Settle pending oracle requests (AI by default, optional manual override)."""

    async def _run() -> None:
        agent, tee_verifier, address = await _build_agent()
        agent_id = await agent.register()
        if os.getenv("TEE_REGISTRATION_MODE", "manual").lower() == "manual":
            await tee_verifier.register_tee_key(agent_id, address)
        if not agent.oracle_client:
            print("Oracle client not configured")
            return
        mode = "manual override" if price_override is not None else "AI resolver"
        print(f"Running oracle cycle using {mode}...")
        results = await settle_pending_requests(agent, price_override)
        if not results:
            print("No pending requests")
        else:
            for res in results:
                print(f"Settled {res['requestId']} -> tx {res['txHash']}")

    asyncio.run(_run())


@cli.group()
def manual_key() -> None:
    """Manage manual resolver keys."""


@manual_key.command("add")
@click.option("--agent-id", type=int, default=None)
def manual_add(agent_id: Optional[int]) -> None:
    """Force-add the resolver key using manual mode."""

    async def _run() -> None:
        agent, tee_verifier, address = await _build_agent()
        agent_id_local = agent_id or await agent.register()
        receipt = await tee_verifier.register_tee_key(agent_id_local, address)
        print(f"Manual key registered: {receipt}")

    asyncio.run(_run())


@manual_key.command("remove")
@click.argument("resolver")
def manual_remove(resolver: str) -> None:
    """Remove a manually registered resolver key."""

    async def _run() -> None:
        _, tee_verifier, _ = await _build_agent()
        tx_hash = await tee_verifier.manual_remove_key(resolver)
        print(f"Manual key removed in tx {tx_hash}")

    asyncio.run(_run())


async def settle_pending_requests(agent: ServerAgent, price_override: Optional[int] = None):
    if not agent.oracle_client:
        return []

    if price_override is None:
        return await agent.run_oracle_cycle()
    return await agent.run_oracle_cycle(price_override=price_override)


if __name__ == "__main__":
    cli()
