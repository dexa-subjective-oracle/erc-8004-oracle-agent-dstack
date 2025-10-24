# Dexa Contracts Integration Plan

This document captures the implementation plan for wiring the ERC-8004 Oracle Agent (Python) to the new Dexa subjective-oracle contracts. Tasks are grouped by milestone so we can stage work, track dependencies, and parallelize safely.

---

## Phase 0 – Prep & Alignment
- **Export ABIs**  
  - [ ] Copy the compiled ABIs for `IdentityRegistry`, `TEERegistry`, `TeeOracle`, and `TeeOracleAdapter` from the Solidity repo (e.g. `contracts/out/...`) into `erc-8004-oracle-agent-dstack/contracts/abis/`.  
  - [ ] Add a small loader (`src/utils/abis.py`) to fetch ABIs from disk and expose them to the registry/oracle clients.  
  - [ ] Introduce a config module that reads `.env`/JSON deployment artifacts produced by the forge script (`broadcast/.../run-latest.json`) and delivers typed addresses to the agent at startup.

- **Environment wiring**  
  - [ ] Extend `.env.example` with `IDENTITY_REGISTRY_ADDRESS`, `TEE_REGISTRY_ADDRESS`, `TEE_ORACLE_ADDRESS`, `TEE_ORACLE_ADAPTER_ADDRESS`, `BASE_SEPOLIA_RPC_URL`, and reuse `RESOLVER_PRIVATE_KEY` (fallback: `DEPLOYER_PRIVATE_KEY`) for local dev.  
  - [ ] Add helper script (`scripts/load_contract_env.py`) so contributors can point the agent at a specific broadcast folder.

---

## Phase 1 – Registry Client Refresh
- **Identity Registry support**  
  - [ ] Replace inline ABI fragments in `RegistryClient` with the Dexa ABI.  
  - [ ] Ensure registration uses `register(string tokenUri)` (only path we support).  
  - [ ] Keep metadata helpers but rename/trim to match contract interface.

- **Wallet management**  
  - [ ] Introduce a unified account loader that shares credentials between `RegistryClient`, `TEEVerifier`, and upcoming oracle client.  
  - [ ] Ensure chain ID + gas settings come from config/env (no hardcoded numbers).

---

## Phase 2 – TEE Registry & Manual Mode
- **Production path**  
  - [ ] Refactor `TEEVerifier` so it consumes the Dexa ABI (not hardcoded fragments) and calls `addKey` exactly once per registration.  
  - [ ] Keep off-chain proof request logic, but move endpoint/headers to config; fail fast on non-200 responses.

- **Manual registration (dev mode)**  
  - [ ] Add a `mode` flag (e.g. `TEE_REGISTRATION_MODE=manual|proof`).  
  - [ ] When in manual mode, invoke `TEERegistry.forceAddKey` using the owner key (uses `MANUAL_VERIFIER`).  
  - [ ] Add `forceRemoveKey` support so developers can clean up.  
  - [ ] Surface these actions via CLI (`python -m deployment.manual_key add/remove`) and FastAPI endpoints for convenience.

---

## Phase 3 – Oracle Interaction Layer
- **Client implementation**  
  - [ ] Create `src/agent/oracle_client.py` that wraps the `TeeOracle` ABI with methods: `request_price(...)`, `settle_price(...)`, and `pending_requests()` (using the new on-chain `pendingRequests()` view).  
  - [ ] Add optional adapter support (call `initialize`, `resolve`) so agents can drive the helper contract when needed.

- **Server integration**  
  - [ ] In `ServerAgent`, register background tasks (e.g. `asyncio.create_task`) to watch for outstanding requests and trigger settlement once a task completes.  
  - [ ] Expose a FastAPI endpoint `/oracle/settle` that accepts `{identifier, timestamp, ancillaryData, price, evidenceHash}` and delegates to the oracle client.

---

## Phase 4 – Agent Workflow & CLI
- **Startup sequence**  
  - [ ] On boot, check identity registration; if missing, register and store `agent_id` locally (`state/agent.json`).  
  - [ ] Verify the registry already has a resolver key: if not, run manual/proof registration automatically based on the mode.  
  - [ ] Query `TeeOracle.pendingRequests()` on startup and process anything outstanding before idling.  
  - [ ] Log the addresses and agent ID so operators have a clear view.

- **Command-line tooling**  
  - [ ] Build a `click` CLI (`erc8004-agent`) with subcommands: `register`, `manual-key add/remove`, `oracle settle`, `status`.  
  - [ ] Ensure CLI shares the config loader so the FastAPI server and command tooling stay in sync.

---

## Phase 5 – Testing & Automation
- **Unit tests**  
  - [ ] Mock web3 interactions for the registry/oracle clients (pytest + `pytest-asyncio`).  
  - [ ] Ensure manual mode flows, proof mode fallback, and error paths have coverage.

- **E2E test harness**  
  - [ ] Add a pytest fixture that spins up Anvil fork, deploys the Dexa contracts via the existing forge script, and returns addresses.  
  - [ ] Register an agent, call `forceAddKey`, run `oracle_client.settle_price`, and assert storage updates in `TeeOracle`.  
  - [ ] Gate the test behind an env flag so it only runs when Anvil is available in CI.

- **CI updates**  
  - [ ] Add lint/test jobs for the Python project (black, flake8, mypy, pytest).  
  - [ ] Optionally add a nightly job that runs the Anvil E2E with manual mode.

---

## Phase 6 – Documentation & Ops
- **Developer docs**  
  - [ ] Update `README.md` and `DEV_GUIDE.md` to reference the Dexa contracts, env vars, manual mode, and CLI commands.  
  - [ ] Add a “First Run” walkthrough (deploy contracts → source `.env` → `python deployment/local_agent_server.py` → `manual-key add`).  
  - [ ] Document rollback/recovery: how to remove manual keys, reset agent state, and redeploy.

- **Operational guidance**  
  - [ ] Provide a checklist for switching from manual mode to real DCAP verification (update env, restart with proof mode).  
  - [ ] Note limitations (manual key not suitable for mainnet) and monitoring hooks (log streaming, contract event watching).

---

## Stretch Goals (Post-integration)
- [ ] Optional Rust/Alloy microservice that mirrors the python client for performance-sensitive tasks (leverage only after MVP).  
 - [ ] UI dashboard to surface agent status, outstanding oracle requests, and manual key state.

---

### Dependencies
- Dexa contracts repo (main branch) with `DeployOracleSuite` script and up-to-date ABIs.  
- Off-chain proof endpoint (if proof mode enabled).  
- Accessible RPC endpoint (Base Sepolia fork or mainnet equivalent).

### Risks / Mitigations
- **dstack SDK behavior**: keep Python flow; add mocks for tests.  
- **Proof service downtime**: default to manual mode for dev/test.  
- **ABI drift**: automate ABI export with a script in the contracts repo to keep both sides in sync.

---

Tracking issue: _Create GH project board once sprint scheduling is decided._
