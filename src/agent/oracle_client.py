"""Oracle client for interacting with TeeOracle contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from eth_account import Account
from eth_typing import HexStr
from web3 import Web3

from src.utils.contract_loader import load_abi


@dataclass
class OracleRequest:
    request_id: bytes
    requester: str
    reward_token: str
    reward: int
    timestamp: int
    identifier: bytes
    ancillary_data: bytes
    settled: bool
    settled_price: int
    evidence_hash: bytes


class OracleClient:
    def __init__(self, w3: Web3, oracle_address: str, account: Account, adapter_address: Optional[str] = None):
        self.w3 = w3
        self.account = account
        self.oracle_contract = w3.eth.contract(address=Web3.to_checksum_address(oracle_address), abi=load_abi("TeeOracle"))
        self.adapter_contract = None
        if adapter_address:
            self.adapter_contract = w3.eth.contract(
                address=Web3.to_checksum_address(adapter_address),
                abi=load_abi("TeeOracleAdapter")
            )

    def pending_request_ids(self) -> List[bytes]:
        return list(self.oracle_contract.functions.pendingRequests().call())

    def fetch_request(self, request_id: bytes) -> OracleRequest:
        raw = self.oracle_contract.functions.getRequest(request_id).call()
        return OracleRequest(
            request_id=request_id,
            requester=raw[0],
            reward_token=raw[1],
            reward=raw[2],
            timestamp=raw[3],
            identifier=raw[4],
            ancillary_data=raw[5],
            settled=raw[6],
            settled_price=raw[7],
            evidence_hash=raw[8]
        )

    def pending_requests(self) -> List[OracleRequest]:
        return [self.fetch_request(req_id) for req_id in self.pending_request_ids()]

    def settle_price(self, request: OracleRequest, price: int, evidence_hash: bytes) -> HexStr:
        tx = self.oracle_contract.functions.settlePrice(
            request.identifier,
            request.timestamp,
            request.ancillary_data,
            price,
            evidence_hash
        ).build_transaction(self._tx_params())
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise RuntimeError(f"settlePrice failed: tx={tx_hash.hex()}")
        return tx_hash.hex()

    def _tx_params(self) -> Dict[str, Any]:
        return {
            "chainId": self.w3.eth.chain_id,
            "gas": 800000,
            "gasPrice": self.w3.eth.gas_price,
            "nonce": self.w3.eth.get_transaction_count(self.account.address)
        }

    @staticmethod
    def compute_request_id(identifier: bytes, timestamp: int, ancillary_data: bytes) -> bytes:
        return Web3.solidity_keccak(["bytes32", "uint256", "bytes"], [identifier, timestamp, ancillary_data])
