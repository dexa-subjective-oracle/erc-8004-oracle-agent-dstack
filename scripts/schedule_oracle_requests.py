#!/usr/bin/env python3
"""
Periodic oracle question scheduler.

Every INTERVAL (default 5 minutes) fetch the current BTC price from Diadata,
picks a random +/-0.1% threshold, and submits a TeeOracle request that resolves
five minutes in the future asking whether BTC will be above that target.
"""

import os
import sys
import time
import random
import logging
from typing import Optional, Dict

import requests
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import HexAddress
from web3 import Web3
from web3.contract import Contract

IDENTIFIER = Web3.keccak(text="YES_OR_NO_QUERY")
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
DIA_DEFAULT_URL = "https://api.diadata.org/v1/assetQuotation/Bitcoin/0x0000000000000000000000000000000000000000"
DEFAULT_DEPLOYMENT = os.getenv("QUESTION_DEPLOYMENT", "base_sepolia")


def load_env(key: str) -> Optional[str]:
    value = os.getenv(key)
    if value:
        return value
    return None


def load_env_or_fail(key: str) -> str:
    value = load_env(key)
    if not value:
        raise RuntimeError(f"{key} must be set")
    return value


def init_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("scheduler")


def init_web3(rpc_url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise RuntimeError(f"Failed to connect to RPC at {rpc_url}")
    return w3


def init_account(private_key: str) -> LocalAccount:
    acct = Account.from_key(private_key)
    logging.info("Using account %s", acct.address)
    return acct


def resolve_addresses() -> Dict[str, str]:
    oracle_address = load_env("TEE_ORACLE_ADDRESS")
    registry_address = load_env("TEE_REGISTRY_ADDRESS")
    identity_address = load_env("IDENTITY_REGISTRY_ADDRESS")

    if oracle_address and registry_address and identity_address:
        return {
            "TeeOracle": oracle_address,
            "TEERegistry": registry_address,
            "IdentityRegistry": identity_address,
        }

    # Fallback to deployment artifacts
    from src.utils.contract_loader import load_deployment_addresses, load_deployment  # pragma: no cover - optional path

    deployment_name = DEFAULT_DEPLOYMENT
    deployment = load_deployment(name=deployment_name)
    contracts = deployment.get("contracts", {})

    if "TeeOracle" not in contracts:
        raise RuntimeError(f"TeeOracle address not found in deployment '{deployment_name}'")

    return contracts


def init_oracle_contract(w3: Web3, address: HexAddress) -> Contract:
    from src.utils.contract_loader import load_abi  # pragma: no cover - optional path

    abi = load_abi("TeeOracle")
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)


def fetch_btc_price(url: str, timeout: float = 10.0) -> float:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    for key in ("price", "Price"):
        if key in data:
            return float(data[key])

    raise RuntimeError(f"Price key not found in response: {data}")


def random_threshold(base_price: float, spread: float) -> float:
    """
    Return a price perturbed by +/- spread fraction (spread=0.001 -> +/-0.1%).
    """
    delta = random.uniform(-spread, spread)
    return base_price * (1.0 + delta)


def build_ancillary(threshold: float) -> str:
    formatted = f"{threshold:,.2f}".replace(",", "")
    return (
        f"Is BTC price above {formatted}? "
        f"Resolve YES if price (USD) from DiaData API "
        f"{DIA_DEFAULT_URL} is greater than {formatted} at the reported timestamp."
    )


def submit_request(
    w3: Web3,
    contract: Contract,
    account: LocalAccount,
    identifier: bytes,
    timestamp: int,
    ancillary: bytes,
    reward_token: str,
    reward: int,
) -> str:
    tx = contract.functions.requestPrice(
        identifier,
        timestamp,
        ancillary,
        Web3.to_checksum_address(reward_token),
        reward,
    ).build_transaction(
        {
            "chainId": w3.eth.chain_id,
            "gas": int(os.getenv("QUESTION_GAS_LIMIT", "500000")),
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(account.address),
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError(f"requestPrice reverted: tx={tx_hash.hex()}")
    return tx_hash.hex()


def main() -> int:
    logger = init_logger()

    rpc_url = load_env_or_fail("RPC_URL")
    addresses = resolve_addresses()
    oracle_address = addresses["TeeOracle"]
    private_key = (
        os.getenv("REQUESTER_PRIVATE_KEY")
        or os.getenv("RESOLVER_PRIVATE_KEY")
        or os.getenv("DEPLOYER_PRIVATE_KEY")
    )
    if not private_key:
        raise RuntimeError("REQUESTER_PRIVATE_KEY (or RESOLVER/DEPLOYER) must be set")

    interval_seconds = int(os.getenv("QUESTION_INTERVAL_SECONDS", "300"))
    lookahead_seconds = int(os.getenv("QUESTION_LOOKAHEAD_SECONDS", "300"))
    spread_fraction = float(os.getenv("QUESTION_PRICE_SPREAD", "0.001"))  # +/-0.1%
    dia_url = os.getenv("DIA_API_URL", DIA_DEFAULT_URL)
    reward_token = os.getenv("QUESTION_REWARD_TOKEN", ZERO_ADDRESS)
    reward_amount = int(os.getenv("QUESTION_REWARD_AMOUNT", "0"))

    w3 = init_web3(rpc_url)
    account = init_account(private_key)
    oracle_contract = init_oracle_contract(w3, oracle_address)

    logger.info(
        "Scheduler running (interval=%ss, lookahead=%ss, spread=%s%%)",
        interval_seconds,
        lookahead_seconds,
        spread_fraction * 100,
    )

    max_submit_attempts = max(1, int(os.getenv("QUESTION_SUBMIT_RETRIES", "2")))
    retry_backoff = max(1, int(os.getenv("QUESTION_RETRY_BACKOFF_SECONDS", "30")))

    try:
        while True:
            try:
                price = fetch_btc_price(dia_url)
                threshold = random_threshold(price, spread_fraction)
                timestamp = int(time.time()) + lookahead_seconds
                ancillary_text = build_ancillary(threshold)
                ancillary_bytes = ancillary_text.encode("utf-8")

                last_error = None
                for attempt in range(1, max_submit_attempts + 1):
                    try:
                        tx_hash = submit_request(
                            w3,
                            oracle_contract,
                            account,
                            IDENTIFIER,
                            timestamp,
                            ancillary_bytes,
                            reward_token,
                            reward_amount,
                        )
                        last_error = None
                        break
                    except Exception as exc:  # pragma: no cover - operational logging
                        last_error = exc
                        logger.warning(
                            "requestPrice failed (attempt %d/%d): %s",
                            attempt,
                            max_submit_attempts,
                            exc,
                        )
                        if attempt < max_submit_attempts:
                            delay = retry_backoff * attempt
                            logger.info("Retrying in %d seconds...", delay)
                            time.sleep(delay)

                if last_error:
                    raise last_error

                logger.info(
                    "Queued question | price=%.2f threshold=%.2f timestamp=%d tx=%s",
                    price,
                    threshold,
                    timestamp,
                    tx_hash,
                )
            except Exception as exc:  # pragma: no cover - operational logging
                logger.error("Failed to create question: %s", exc)

            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped via CTRL+C")
        return 0


if __name__ == "__main__":
    sys.exit(main())
