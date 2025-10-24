# Remaining Dexa Integration Work Items

## Feature/Flow Gaps
- [ ] Implement real proof-based key registration path in `TEEVerifier` (fetch proof service URL from config, validate response).  
- [ ] Add background watcher to `ServerAgent` (or a FastAPI background task) that continuously monitors `pendingRequests()` and triggers settlement.  
- [ ] Support TeeOracleAdapter interactions (`initialize`, `resolve`) when ancillary workflows depend on it.  
- [ ] Build oracle settlement strategy (price computation + evidence hash generation) instead of the current dummy constant price.

## CLI & Tooling
- [ ] Expand `scripts/agent_cli.py` with subcommands to:  
  - request price via adapter,  
  - dump agent metadata,  
  - tail Anvil logs.  
- [ ] Package CLI entry-point in `setup.py` (console_script) so it is installable.

## Testing
- [ ] Mock-based unit tests for `TEEVerifier` (manual + proof) and `OracleClient`.  
- [ ] Integration test harness that spins up Anvil, uses the CLI to register, add manual key, request price, and settle.  
- [ ] CI wiring: add pytest to GitHub workflow, optional nightly integration run with Anvil fork.

## Documentation
- [ ] Update README/DEV_GUIDE with new commands, `.env` flags, sample workflow (deploy → register → manual key → settle).  
- [ ] Document security considerations for manual resolver mode vs proof mode.  
- [ ] Note limitations around mock evidence and manual pricing for the PoC.

## Operational Enhancements
- [ ] Add logging/metrics around settlement outcomes and queue state.  
- [ ] Persist oracle settlement history (e.g., simple JSON log) for debugging.  
- [ ] Provide helper script to reseed `.env` from latest broadcast output automatically.

## Stretch
- [ ] Optional UI dashboard showing pending requests, settlement history, and key status.  
- [ ] Consider splitting proof-verifier interactions into dedicated service or Rust microservice once proof mode is fully supported.

