# Secure Subjective Oracle – Initial Specification

## 1. Goals
- Resolve time-bound prediction market questions that require subjective or interpretive judgments (e.g., parsing FOMC policy statements) with high integrity.
- Provide cryptographic assurance that resolution logic executed inside a trusted enclave (Intel TDX via dstack) and that the produced outcome corresponds to published resolution criteria.
- Support repeatable resolution attempts that only execute after a market-defined deadline, while continuously monitoring elapsed time using a trustworthy clock source (Cloudflare Roughtime).

## 2. Scope & Non‑Goals
- **In scope:** single-market resolution workflow, UMA CTF adapter integration, scheduling & polling loop in the agent, TEE attestation logging.
- **Out of scope (initial release):** multi-oracle consensus, economic staking/slashing, automated dispute resolution, advanced human-in-the-loop tooling.

## 3. Actors & Components
- **Prediction Market Contract** – emits resolution requests and awaits callback with `true|false|invalid` (or bucketed numeric outcome) plus supporting metadata.
- **Oracle Adapter Contract (UMA CTF Adapter)** – existing Polymarket adapter that stores ancillary question data and mediates between markets and oracles. We will swap its dependency on UMA’s Optimistic Oracle with our TEE agent callbacks.
- **TEE Agent (this repo)** – polls the adapter, enforces timing rules using Cloudflare time, generates and executes task-specific resolution code inside the sandbox, verifies outputs, and submits on-chain transactions.
- **External Data Sources** – official FOMC statement pages, archive endpoints, fallbacks (e.g., press releases RSS); time source endpoints (`https://time.cloudflare.com/`).

## 4. Request Lifecycle (Replacing UMA OO with TEE Agent)
1. **Question Registration (on-chain):**
   - Market contract calls `UmaCtfAdapter.initialize(...)`, attaching ancillary data that fully specifies resolution rules, sources, timing and rounding policies for that question.
   - Adapter persists `QuestionData` (request timestamp, liveness, bonds, metadata) and prepares the Conditional Tokens condition.
2. **Polling & Scheduling (off-chain agent):**
   - Agent runs a scheduler coroutine that:
     - Fetches Cloudflare Roughtime periodically to maintain an accurate clock.
     - Reads pending UMA questions via `ready()` / `getQuestion()` to identify markets awaiting resolution.
     - Sleeps until the minimum of (earliestResolveTime, next poll window), respecting `timeoutBuffer`.
3. **Resolution Attempt:**
   - After `cloudflare_time >= earliestResolveTime`, agent retrieves metadata, builds a deterministic prompt for the AI code generator **OR** selects a vetted resolver template.
   - Generated resolver script executes in sandbox, fetching authoritative sources, applying parsing/rounding rules, and producing a candidate outcome `{"status": "true|false|invalid", "evidence": {...}}`.
   - Execution artifacts, HTTP transcripts, and hashes are persisted for auditing.
4. **Verification & Submission:**
   - Agent validates the resolver output, attaches TDX attestation (including AI attestation if code was generated), and calls the TEE-backed oracle contract that conforms to UMA’s Optimistic Oracle interface.
   - The TEE oracle contract verifies that the caller matches the registered enclave pubkey, stores the outcome, and exposes it to the adapter so `resolve()` succeeds without UMA involvement.
5. **Retries & Failures:**
   - If parsing fails or sources unavailable, agent marks attempt as `pending` and schedules a retry with exponential backoff until `timeoutBuffer` expires, after which it defaults to `invalid/no change`.

## 5. Timekeeping
- Leverage Cloudflare Roughtime:
  - Maintain a local monotonic time anchor updated every few minutes.
  - Compare market deadlines against `cloudflare_time` instead of local clock.
  - Record the time proofs in the evidence bundle for on-chain consumers.

## 6. On-Chain Integration Notes (UMA CTF Adapter + TEE Oracle)
- Reuse `UmaCtfAdapter` ancillary data requirements; resolution rules stay embedded in ancillary text.
- Deploy a **TEE Oracle Contract** that implements the UMA Optimistic Oracle interface (e.g., `getRequest`, `setCustomLiveness`, `requestPrice`, `settle`, etc.) but gates settlement through TEE-enforced access control.
  - Contract tracks a registry of authorized enclave-derived addresses (via our TEE key registration flow).
  - On `settle`/`publishPrice` calls, it verifies proofs/attestations and records the resolved price that the adapter reads.
- Redeploy the adapter pointing to this TEE oracle address; no changes required to the adapter ABI, ensuring drop-in replacement for Polymarket markets.
- Bonds/rewards can be set to zero or kept as fees, but UMA-specific dispute hooks become no-ops unless we add our own dispute logic.

## 7. Agent Workflow Enhancements
- **Task Manager**: maintain async queue keyed by `questionId` with states: `scheduled`, `resolving`, `waiting_retry`, `finalized`.
- **Resolver Library**: start with typed templates (e.g., rate-change resolver) before allowing free-form AI code generation. Store templates in repo with tests.
- **Execution Guardrails**:
  - Limit outbound HTTP domains to pre-approved list.
  - Capture request/response logs.
  - Enforce deterministic configuration (e.g., fixed user-agent, set timeouts).
- **Evidence Packaging**: persist artifacts to IPFS (attestation JSON, page snapshot hash) and include CID in `resultPayload`.

## 8. Security & Integrity Considerations
- TDX attestation must commit to code measurement of the agent release; include measurement hash in documentation.
- AI-generated scripts must themselves produce attestation (RedPill) to counter tampering.
- Double-check rounding rules (e.g., 12.5 → 25 bps) inside resolver logic.
- Implement replay protection on adapter contract to prevent result re-submission.
- Provide audit logs and optional observer endpoints for replication.

## 9. Open Questions / Next Steps
1. **Determinism vs. AI Generated Code:** Do we require pre-reviewed resolvers per market archetype before enabling dynamic code generation?
2. **Dispute Mechanism:** How will disputes be triggered and adjudicated if multiple oracles disagree?
3. **Data Source Availability:** Plan for outages (cached snapshots, multiple mirrors).
4. **Market Compatibility:** Define ABI for prediction markets expecting numeric buckets vs. boolean outcomes.
5. **Economic Incentives:** Determine staking/slashing requirements to align oracle incentives.

## 10. Implementation Roadmap (High-Level)
1. Extend UMA adapter with TEE resolution entry point and authorization checks.
2. Extend agent to poll adapter, integrate Cloudflare Roughtime, and maintain job lifecycle state.
3. Implement first resolver template (FOMC rate change) with unit/integration tests and sandbox execution.
4. Wire on-chain submission path with evidence bundling and TDX attestation payload.
5. Add monitoring, logging, and manual override tooling.
6. Conduct end-to-end dry runs with simulated market requests on Base Sepolia.
