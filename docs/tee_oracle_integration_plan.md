# TEE Oracle Integration Plan with Identity & TEE Registries

This document details how to extend the proof-of-concept oracle so only agents that have completed on-chain registration (identity NFT + TEE key) can finalize prediction-market outcomes.

---

## 1. Current Building Blocks

### IdentityRegistry
- ERC-721 where each agent mints a unique `agentId`.
- Owners/operators can update metadata and tokenURI.
- No direct linkage to TEE keys yet, but ownership proves agent identity.

### TEERegistry
- Tracks whitelisted verifiers and TEE keys.
- `addKey(agentId, teeArch, codeMeasurement, pubkey, codeConfigUri, verifier, proof)` stores the enclave public key and associates it with an `agentId`.
- TODOs exist for ownership validation (ensuring only the agent owner can register a key) and for calling verifier contracts (e.g., `DstackVerifier`).
- `hasKey(agentId, pubkey)` checks membership, but there is no helper to ask “is this pubkey registered anywhere?” nor to return the `agentId`.

### DstackVerifier
- Validates DCAP quotes/proofs off-chain and verifies enclave measurement + pubkey.
- Intended to be invoked by `TEERegistry.addKey`.

### TeeOracle (PoC)
- Tracks price requests and allows any caller to settle them after `setTrustedResolver`.
- No awareness of registries yet.

---

## 2. Target Behavior
- Any enclave key that has been registered in `TEERegistry` (after IdentityRegistry ownership check + proof verification) may settle oracle requests.
- Unregistered addresses must not be able to call `settlePrice`, regardless of earlier `setTrustedResolver` calls.
- We do not need to embed the `agentId` in each request initially; global authorization is sufficient for PoC.

---

## 3. Contract Changes

### 3.1 TEERegistry Enhancements
- **Add pubkey lookup helper**
  ```solidity
  function isRegisteredKey(address pubkey) external view returns (bool);
  ```
  Returns true when `_keys[pubkey].verifier != address(0)`.
- **Persist agent linkage (optional now, useful later)**
  - Extend the `Key` struct or store an auxiliary mapping `pubkey => agentId`.
  - Enables event emissions and future authorization rules (e.g., only specific agents may settle certain requests).
- **Finish ownership check TODOs**
  - In `addKey`/`removeKey`, require that `msg.sender` is the owner or operator of `agentId` in `IdentityRegistry`.
- **Integrate verifier proof (optional for PoC)**
  - Hook in `DstackVerifier` to validate proofs before adding key. Can stay a no-op until off-chain flow is ready.

### 3.2 TeeOracle Updates
- **Constructor dependencies**
  ```solidity
  constructor(address teeRegistry_, address identityRegistry_) { ... }
  ```
  The oracle needs the TEE registry (mandatory) and optionally the identity registry for future extensions.
- **Authorization check in `settlePrice`**
  ```solidity
  if (!teeRegistry.isRegisteredKey(msg.sender)) revert UnauthorizedResolver();
  ```
  - Remove or gate the previous `setTrustedResolver`; rely on TEE registry instead.
  - Optionally fetch `agentId` (if registry exposes it) to include in events.
- **Events**
  - Emit `PriceRequested(requestId, ancillaryData)` and `PriceSettled(requestId, price, msg.sender)` so the agent and observers can monitor activity. Include `agentId` if available.
- **Request struct**
  - No change needed now. If we later need to restrict settlements per request, add an `agentId` field.

### 3.3 Adapter Adjustments
- Not strictly required for this step. It continues to submit `requestPrice` and poll `hasPrice`.
- Future enhancement: feed `agentId` metadata from the Adapter to the agent so it knows which key should settle each question.

---

## 4. Testing Plan (Foundry)

### Setup Fixtures
1. Deploy `IdentityRegistry`, `TEERegistry(identityRegistry)`, and a mock verifier (can be a simple contract returning true).
2. Deploy `TeeOracle` pointing at the TEE registry.

### Test Scenarios
1. **Key registration flow**
   - Mint an agent NFT in IdentityRegistry.
   - Register a pubkey via TEERegistry (simulate successful verifier call).
   - Assert `teeRegistry.isRegisteredKey(pubkey)` returns true.
2. **Oracle settlement authorization**
   - Submit a price request through the adapter (or directly).
   - Attempt to call `settlePrice` from the registered pubkey (expect success).
   - Attempt from an unregistered address (expect revert `UnauthorizedResolver`).
3. **Key revocation (if implemented)**
   - Remove the key via `TEERegistry.removeKey`.
   - Verify `settlePrice` now reverts for the previously authorized address.
4. **Event assertions**
   - Check that the oracle emits expected events with correct request IDs.

---

## 5. Implementation Steps

1. **Update TEERegistry**
   - Add ownership checks using `IdentityRegistry`.
   - Add `pubkey => agentId` mapping and `isRegisteredKey`.
   - (Optional) Wire verifier proof validation.
2. **Modify TeeOracle**
   - Inject registries in constructor.
  - Gate `settlePrice` with `isRegisteredKey`.
   - Emit events for requests and settlements.
   - Remove `setTrustedResolver` if no longer needed.
3. **Refactor tests**
   - Extend existing Foundry tests to deploy registries and register keys before settlement.
   - Add negative tests for unauthorized settlement.
4. **Update documentation**
   - Reflect new oracle behavior in `tee_oracle_contracts_spec.md`.
   - Document key registration flow in `subjective_oracle_spec.md`.

---

## 6. Future Extensions
- Store agentId in each request to enforce per-question authorization.
- Support multi-TEE consensus (e.g., quorum of keys required).
- Integrate slashing/dispute logic using registry metadata.
- Surface TEE attestation data (code measurement) in settlement events for on-chain verification.
- Automate off-chain flows to register agent + key from the TEE server on startup.

---

With these steps, the oracle’s settlement path becomes tightly coupled to the on-chain registration system, ensuring only attested agents can resolve prediction markets.
