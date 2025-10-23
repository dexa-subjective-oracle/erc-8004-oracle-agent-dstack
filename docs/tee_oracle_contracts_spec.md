# TEE Subjective Oracle – Minimal Contract Specification

This document lays out the proof-of-concept contracts that replace UMA’s Optimistic Oracle in the Polymarket UMA CTF adapter flow with a TEE-attested resolver.

## Overview
We introduce two thin contracts:
1. **`TeeOracle`** – stores price requests and resolved outcomes. Only an authorized enclave address (registered via TEE key registry) may fulfill requests. It exposes the subset of UMA Optimistic Oracle view/mutation methods used by the adapter (`requestPrice`, `hasPrice`, `settleAndGetPrice`).
2. **`TeeOracleAdapter`** – minimal wrapper mirroring the UMA CTF adapter logic but delegating oracle calls to `TeeOracle`. For the PoC it forwards `initialize`, `ready`, and `resolve` to showcase end-to-end flow without integrating the full adapter codebase.

Existing prediction markets can redeploy the UMA adapter pointing to `TeeOracle`, or we can use `TeeOracleAdapter` for testing.

## Contract Specifications

### 1. TeeOracle

**State**
- `struct Request`:
  - `address requester` – original caller.
  - `IERC20 rewardToken` – ERC20 used for rewards/bonds (for PoC can be informational).
  - `uint256 reward` – reward amount.
  - `uint256 timestamp` – request timestamp (block time recorded when request submitted).
  - `bool settled` – flag indicating outcome has been posted.
  - `int256 settledPrice` – final resolved price (1 for YES, 0 for NO, -1 for INVALID).
- `mapping(bytes32 => Request) public requests` – keyed by `keccak256(abi.encode(identifier, timestamp, ancillaryData))`.
- `mapping(address => bool) public isTrustedResolver` – addresses derived from attested TEEs.

**Events**
- `event PriceRequested(bytes32 indexed requestId, address indexed requester, bytes ancillaryData);`
- `event PriceSettled(bytes32 indexed requestId, int256 price, address indexed resolver);`
- `event ResolverAuthorized(address indexed resolver, bool allowed);`

**Access Control**
- Owner (deployer) can call `setTrustedResolver(address resolver, bool allowed)`. For production, owner is the TEE registry contract.

**Functions**
- `function requestPrice(bytes32 identifier, uint256 timestamp, bytes calldata ancillaryData, IERC20 rewardToken, uint256 reward) external returns (bytes32 requestId);`
  - Computes `requestId`.
  - Requires request not already initialized.
  - Stores request metadata; reward transfers optional for PoC.
  - Emits `PriceRequested`.
- `function hasPrice(address, bytes32 identifier, uint256 timestamp, bytes calldata ancillaryData) external view returns (bool);`
  - Returns `requests[requestId].settled`.
  - Adapter passes `address(this)` in place of UMA’s oracle address; we ignore the requester argument.
- `function settleAndGetPrice(bytes32 identifier, uint256 timestamp, bytes calldata ancillaryData) external view returns (int256);`
  - Reverts if `settled == false`, otherwise returns `settledPrice`.
- `function settlePrice(bytes32 identifier, uint256 timestamp, bytes calldata ancillaryData, int256 price) external;`
  - Only callable by trusted resolver.
  - Marks request settled and stores `price`.
  - Emits `PriceSettled`.
- **Optional helpers**: expose `getRequest(bytes32 requestId)` for debugging/monitoring.

### 2. TeeOracleAdapter (PoC)

Purpose: Minimal reproduction of the UMA CTF adapter flow focusing on the oracle interactions we’re replacing.

**State**
- `struct Question` mirroring relevant UmaCtfAdapter fields:
  - `bytes ancillaryData`
  - `uint256 requestTimestamp`
  - `bool resolved`
- `mapping(bytes32 => Question) public questions;`
- `ITeeOracle public teeOracle;`

**Events**
- `event QuestionInitialized(bytes32 indexed questionId, uint256 requestTimestamp);`
- `event QuestionResolved(bytes32 indexed questionId, int256 price);`

**Functions**
- `constructor(address oracle)` – sets oracle reference.
- `function initialize(bytes calldata ancillaryData) external returns (bytes32 questionId);`
  - Derives `questionId = keccak256(ancillaryData)`.
  - Stores `Question` with `requestTimestamp = block.timestamp`.
  - Calls `teeOracle.requestPrice(identifier, requestTimestamp, ancillaryData, IERC20(0), 0);`
    - Identifier constant: `YES_OR_NO_QUERY`.
  - Emits `QuestionInitialized`.
- `function ready(bytes32 questionId) external view returns (bool);`
  - Reads `Question` and returns `teeOracle.hasPrice(address(this), identifier, question.requestTimestamp, question.ancillaryData)`.
- `function resolve(bytes32 questionId) external returns (int256);`
  - Requires not already resolved and `ready(questionId)` is true.
  - Calls `teeOracle.settleAndGetPrice(identifier, requestTimestamp, ancillaryData)`.
  - Marks question resolved, emits `QuestionResolved`, and returns price.

The adapter intentionally omits reward, bond, pause/flag mechanics to keep the PoC focused on resolution flow.

### 3. Constants & Identifiers
- Use UMA’s `bytes32 constant YES_OR_NO_IDENTIFIER = keccak256("YES_OR_NO_QUERY");`
- For invalid outcomes, adopt UMA’s convention: 1e18 (YES), 0 (NO), or `INT256_MIN` for “Ignore”. For PoC we can pin: YES = 1e18, NO = 0, INVALID = type(int256).min + 1.

## Interaction Flow
1. Market (or test harness) calls `TeeOracleAdapter.initialize(ancillaryData)` – stores question & forwards request to `TeeOracle`.
2. Agent monitors adapter or directly polls `TeeOracle.requests`.
3. When resolution criteria met, agent computes price and calls `TeeOracle.settlePrice(...)` from its enclave-derived address.
4. `TeeOracleAdapter.ready(questionId)` becomes true.
5. Continue the usual UMA resolution flow by invoking `resolve(questionId)` to fetch the outcome and drive payouts.

## Future Extensions
- Integrate with full `UmaCtfAdapter` contract rather than PoC wrapper.
- Add staking/slashing logic to `TeeOracle`.
- Replace owner-based resolver authorization with TEE registry contract calls.
- Support multi-option (non-binary) payouts by expanding price schema or storing arrays directly.
- Include attestation data hash in `settledPrice` event for on-chain verification.
