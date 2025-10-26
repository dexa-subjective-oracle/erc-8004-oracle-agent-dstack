# Remaining Dexa Integration Work Items

## Feature/Flow Gaps
- [ ] Implement real proof-based key registration path in `TEEVerifier` (fetch proof service URL from config, validate response).  
- [x] Add background watcher to `ServerAgent` (or a FastAPI background task) that continuously monitors `pendingRequests()` and triggers settlement.  ✅ Implemented via `ServerAgent.start_oracle_worker()` and invoked on FastAPI startup (`deployment/local_agent_server.py`).
- [ ] Support TeeOracleAdapter interactions (`initialize`, `resolve`) when ancillary workflows depend on it.  
- [x] Build oracle settlement strategy (price computation + evidence hash generation) instead of the current dummy constant price.  ✅ AI-generated resolver now fetches DiaData prices, persists evidence (including `txHash`), and runs automatically via the oracle worker.

## CLI & Tooling
- [ ] Expand `scripts/agent_cli.py` with subcommands to:  
  - request price via adapter,  
  - dump agent metadata,  
  - tail Anvil logs.  
- [ ] Package CLI entry-point in `setup.py` (console_script) so it is installable.
- [x] Make `agent_cli run` use AI settlement by default with optional `--price-override` for manual ops.

## Testing
- [ ] Mock-based unit tests for `TEEVerifier` (manual + proof) — Oracle client decode and ancillary sanitizer tests now exist, extend coverage to verifier flows.  
- [ ] Integration test harness that spins up Anvil, uses the CLI to register, add manual key, request price, and settle.  
- [ ] CI wiring: add pytest to GitHub workflow, optional nightly integration run with Anvil fork.

## Documentation
- [ ] Update README/DEV_GUIDE with new commands, `.env` flags, sample workflow (deploy → register → manual key → settle).  
- [ ] Document security considerations for manual resolver mode vs proof mode.  
- [ ] Note limitations around mock evidence and manual pricing for the PoC.

## Operational Enhancements
- [ ] Add logging/metrics around settlement outcomes and queue state.  
- [x] Persist oracle settlement history (e.g., simple JSON log) for debugging.  ✅ Evidence persisted under `state/evidence/` per settlement.
- [ ] Provide helper script to reseed `.env` from latest broadcast output automatically.
- [x] Add retry/backoff to scheduler submissions so transient requestPrice failures do not halt the loop.

## Stretch
- [ ] Optional UI dashboard showing pending requests, settlement history, and key status.  
- [ ] Consider splitting proof-verifier interactions into dedicated service or Rust microservice once proof mode is fully supported.
