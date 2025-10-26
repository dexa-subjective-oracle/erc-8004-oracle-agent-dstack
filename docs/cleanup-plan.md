# Lightweight Agent Cleanup Plan

This document tracks the work needed to trim the FastAPI agent down to the single Base Sepolia subjective-oracle loop (scheduler ➜ agent ➜ Ollama resolver). The goals are:

- Eliminate dead code paths that reference RedPill / AIO sandbox flows.
- Remove unused endpoints and UI pages so the surface area matches the current product.
- Simplify documentation so new contributors land directly on the supported workflow.
- Confirm that the Docker stack remains the canonical runtime (`docker compose up`).

## Repo Health Checklist

| Area | Current State | Action | Notes |
| --- | --- | --- | --- |
| AI generation (`src/agent/ai_generator.py`, `src/templates/server_agent.py`) | Still supports RedPill/OpenAI providers and attestation payloads we no longer ingest. | Strip non-Ollama branches, collapse configuration to `AI_PROVIDER=ollama`, and delete attestation helpers (`verify_ai_attestation.py`). | Ensure the scheduler/agent integration test stubs keep working with the slimmer API. |
| TEE auth/verifier (`src/agent/tee_auth.py`, `src/agent/tee_verifier.py`) | Implements multiple registration modes and DCAP plumbing that the docker stack bypasses. | Document minimal path (manual key) and move the rest behind a `tee/` legacy module or delete once on-chain requirements are confirmed. | Update `deployment/local_agent_server.py` constructors to avoid instantiating unused verifiers. |
| FastAPI endpoints (`deployment/local_agent_server.py`) | Legacy routes (`/tasks`, `/api/metadata/update`, `/register`, `/attestation`, etc.) remain. | Audit route usage (check `src/templates/frontend`, `scripts/agent_cli.py`) and remove everything except `/health`, `/api/status`, `/evidence`, and UMA settlement helpers. | Add FastAPI tests to lock down the minimal surface. |
| Static front-end (`static/`, `src/templates/frontend`) | Contains dashboards and RedPill onboarding screens. | Delete pages that are no longer linked; keep only assets used by `/evidence`. | Verify HTML references when pruning (search for `StaticFiles`). |
| CLI utilities (`scripts/`) | Includes interactive CLI flows for registration, attestation, and sandbox tasks. | Keep `schedule_oracle_requests.py`; move the rest to `../archive/` or delete after confirming nobody relies on them. | Update README quick start to point exclusively at docker-compose + optional manual CLI. |
| Documentation (`DEV_GUIDE.md`, `DEPLOYMENT.md`, `AI_GENERATION_GUIDE.md`, etc.) | Reference VibeVM, RedPill API keys, legacy Docker instructions. | Create focused quick start (Docker), reference architecture (scheduler↔agent), and archive old guides under `docs/legacy/`. | Add changelog entry summarizing deprecations. |
| Configuration templates (`.env.example`, `docker/.env.docker.example`, `agent_config.json`) | Contain knobs for unused flows and attestation toggles. | Remove redundant envs (e.g. `USE_TEE_AUTH`, RedPill API keys) once the code paths disappear. | Ensure contract addresses still flow from `contracts/deployments/base_sepolia_deployment.json`. |
| Tests (`tests/`) | Sparse coverage; no assertions for `/evidence` explorer or scheduler loop. | Add pytest coverage for the evidence explorer, UMA settlement happy path, and docker-compose smoke (pytest mark + doc). | Coordinate with contracts repo for any integration fixtures needed. |

## Execution Order

1. **Lock the runtime** – Add a smoke test (or documented manual step) that `docker compose up` settles at least one request with Gemma via Ollama.
2. **Prune unused AI paths** – Update `ai_generator` and `ServerAgent` first; this removes the need for RedPill env vars and simplifies evidence payloads.
3. **Trim HTTP surface** – Remove unused FastAPI routes and matching templates, then update the docs/tests.
4. **Archive documentation** – Rewrite README sections, move long-form guides that no longer apply into `docs/legacy/`, and link to them from a short note.
5. **Config tidy-up** – After code deletion, drop the unused env keys and regenerate `.env.example` artifacts.
6. **Regression sweep** – Run `pytest`, `docker compose build`, and a manual settlement to confirm the stack still works end-to-end.

Track each milestone with a GitHub issue so we can assign owners and capture context that does not belong in the codebase.
