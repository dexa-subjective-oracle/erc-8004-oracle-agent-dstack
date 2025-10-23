"""TEE Verification and Registration"""

import httpx
from typing import Dict, Any, Optional
from web3 import Web3
from eth_account import Account
from eth_utils import keccak

from src.utils.contract_loader import load_abi


class TEEVerifier:
    def __init__(
        self,
        w3: Web3,
        tee_registry_address: str,
        account: Account,
        verifier_address: Optional[str] = None,
        mode: str = "proof",
        tee_arch_label: str = "INTEL_TDX",
        manual_config_uri: str = "manual://dev"
    ):
        self.w3 = w3
        self.registry_address = Web3.to_checksum_address(tee_registry_address)
        self.account = account
        self.verifier_address = Web3.to_checksum_address(verifier_address) if verifier_address else None
        self.mode = mode
        self.tee_arch_label = tee_arch_label
        self.manual_config_uri = manual_config_uri
        self.tee_arch = keccak(text=tee_arch_label)
        self.manual_measurement = keccak(text=manual_config_uri)

        self.registry_contract = w3.eth.contract(
            address=self.registry_address,
            abi=load_abi("TEERegistry")
        )

    async def check_tee_registered(self, agent_id: int, pubkey_address: str) -> bool:
        """Check if a key is already in the registry."""
        checksum_pubkey = Web3.to_checksum_address(pubkey_address)
        try:
            return self.registry_contract.functions.isRegisteredKey(checksum_pubkey).call()
        except ValueError:
            return self.registry_contract.functions.hasKey(agent_id, checksum_pubkey).call()

    async def register_tee_key(
        self,
        agent_id: int,
        agent_address: str,
        tdx_quote: Optional[str] = None,
        app_id: Optional[str] = None,
        dstack_domain: Optional[str] = None,
        event_log: Optional[object] = None,
        mock_mode: bool = True
    ) -> Dict[str, Any]:
        """Register a resolver key with either proof or manual mode."""

        pubkey = Web3.to_checksum_address(agent_address)
        if await self.check_tee_registered(agent_id, pubkey):
            return {"success": True, "agent_id": agent_id, "pubkey": pubkey, "already_registered": True}

        if self.mode == "manual":
            return self._register_manual(agent_id, pubkey)

        return await self._register_with_proof(
            agent_id,
            pubkey,
            tdx_quote=tdx_quote,
            app_id=app_id,
            dstack_domain=dstack_domain,
            event_log=event_log,
            mock_mode=mock_mode,
        )

    async def manual_remove_key(self, pubkey_address: str) -> str:
        """Remove a manually registered resolver key."""
        checksum_pubkey = Web3.to_checksum_address(pubkey_address)
        tx = self.registry_contract.functions.forceRemoveKey(checksum_pubkey)
        tx_hash = self._send_transaction(tx)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise RuntimeError(f"forceRemoveKey failed: tx={tx_hash.hex()}")
        return tx_hash.hex()

    def _register_manual(self, agent_id: int, pubkey: str) -> Dict[str, Any]:
        tx = self.registry_contract.functions.forceAddKey(
            agent_id,
            self.tee_arch,
            self.manual_measurement,
            pubkey,
            self.manual_config_uri,
        )
        tx_hash = self._send_transaction(tx)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise RuntimeError(f"forceAddKey failed: tx={tx_hash.hex()}")
        return {
            "success": True,
            "tx_hash": tx_hash.hex(),
            "agent_id": agent_id,
            "pubkey": pubkey,
            "mode": "manual",
            "code_measurement": self.manual_measurement.hex(),
            "code_config_uri": self.manual_config_uri,
        }

    async def _register_with_proof(
        self,
        agent_id: int,
        pubkey: str,
        *,
        tdx_quote: Optional[str],
        app_id: Optional[str],
        dstack_domain: Optional[str],
        event_log: Optional[object],
        mock_mode: bool,
    ) -> Dict[str, Any]:
        if not self.verifier_address:
            raise RuntimeError("Verifier address required for proof mode")

        if not all([tdx_quote, app_id, dstack_domain]):
            raise ValueError("Proof mode requires tdx_quote, app_id, and dstack_domain")

        payload = {
            "agentId": agent_id,
            "agentPubkey": pubkey,
            "tdxQuote": tdx_quote,
            "appId": app_id,
            "dstackDomain": dstack_domain,
        }

        print(f"📤 Requesting offchain proof with payload: {payload}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://194622febfc33d67e4a98f365dbc2fe9d0d53933-3000.dstack-pha-prod9.phala.network/getOffchainProof",
                    json=payload,
                )
                print(f"📥 Offchain proof response status: {resp.status_code}")
                print(f"📥 Offchain proof response: {resp.text[:500]}")
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            print(f"❌ Offchain proof request failed: {exc}")
            raise RuntimeError(f"Failed to get offchain proof: {exc}") from exc

        code_measurement = data["codeMeasurement"]
        code_config_uri = data["codeConfigUri"]
        proof = data["proof"]

        tx = self.registry_contract.functions.addKey(
            agent_id,
            self.tee_arch,
            code_measurement,
            pubkey,
            code_config_uri,
            self.verifier_address,
            proof,
        )
        tx_hash = self._send_transaction(tx)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise RuntimeError(f"TEE registration failed: tx={tx_hash.hex()}")

        return {
            "success": True,
            "tx_hash": tx_hash.hex(),
            "agent_id": agent_id,
            "pubkey": pubkey,
            "code_measurement": code_measurement,
            "code_config_uri": code_config_uri,
            "mode": "proof",
        }

    def _send_transaction(self, fn) -> bytes:
        tx = fn.build_transaction(
            {
                "chainId": self.w3.eth.chain_id,
                "gas": 500000,
                "gasPrice": self.w3.eth.gas_price,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
            }
        )
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"📤 Registry tx: {tx_hash.hex()}")
        return tx_hash
