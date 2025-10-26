# ERC-8004 TEE Agent Template

Build trustless AI agents with [dstack](https://github.com/dstack-tee/dstack), ERC-8004 compliance, and seamless deployment on Phala Cloud.

## Current Flow Summary

The template has been narrowed to a single opinionated workflow that mirrors how we operate the subjective oracle stack today:

1. **Request Scheduler** (`scripts/schedule_oracle_requests.py`) runs continuously, pulling BTC spot data from DiaData and calling `TeeOracle.requestPrice` on Base Sepolia. The cadence, lookahead, and spread are controlled through environment variables (see `docker/.env.docker.example`).
2. **Agent Service** (`deployment/local_agent_server.py`) boots a FastAPI server, ensures the resolver key is registered (manual mode), watches `pendingRequests()`, and immediately generates + analyses a settlement script for each new question, logging the code and confidence score while it waits for the grace period to expire.
3. **AI Resolution** is handled locally through Ollama (Gemma 3 4B). When the execution window opens, the pre-generated script runs to fetch DIA prices, produces structured evidence (including the analysis metadata), and submits `settlePrice`. Evidence is persisted under `state/evidence/` and exposed via the `/evidence` explorer.
4. **Docker Compose** (`docker-compose.yml`) bundles both components (agent + scheduler) so a developer can simply run `docker compose --env-file docker/.env.docker up --build` and observe the full loop end-to-end.

The sections below are being updated to match this more focused setup and to flag legacy scaffolding slated for removal.

## Features

- 🔄 **Automated UMA Flow** – scheduler + AI settlements run continuously on Base Sepolia.
- 🧠 **Local AI Resolver** – default Gemma3 Ollama backend, no external API dependency.
- 🧾 **Evidence Explorer** – browse/download settlement artifacts via `/evidence`.
- 🐳 **Docker-First Runtime** – single compose file with shared named volume for agent state.
- ⚙️ **Configurable Runtime** – `.env` / `docker/.env.docker` control RPC URLs, cadence, and AI parameters.

## Quick Start

### Quick Start (Docker)

1. **Copy the Docker env template**
   ```bash
   cp docker/.env.docker.example docker/.env.docker
   ```
   Fill in the Base Sepolia RPC URL and the funded resolver private key. Optional knobs (cadence, spread, AI temperature) live in the same file.

2. **Bring up the stack**
   ```bash
   docker compose --env-file docker/.env.docker up --build
   ```
   This starts three services: `ollama` (Gemma backend), `agent` (FastAPI + resolver), and `scheduler` (price requests). The agent and scheduler share the `agent-state` volume.

3. **Observe the flow**
   - `docker compose logs -f agent`
   - `docker compose logs -f scheduler`
   - http://localhost:8000/health, http://localhost:8000/evidence, http://localhost:8000/docs

4. **Shut down**
   ```bash
   docker compose down
   docker volume rm erc-8004-oracle-agent-dstack_agent-state  # optional reset
   rm docker/.env.docker                                      # optional cleanup
   ```

### Docker Setup Guide (Detailed)

1. **Seed configuration**
   - Run `cp docker/.env.docker.example docker/.env.docker`.
   - Fill in `BASE_SEPOLIA_RPC_URL`, `RPC_URL`, and `RESOLVER_PRIVATE_KEY` with funded credentials. Keep this file out of git.
   - Optional: set `OLLAMA_BOOTSTRAP_MODELS` (comma separated) to preload additional models.
2. **Launch the stack**
   - Execute `docker compose --env-file docker/.env.docker up --build`.
   - The first boot downloads ~3.3 GB for `gemma3:4b`; expect a several-minute pull before the agent starts.
3. **Confirm readiness**
   - `docker compose ps` should show `ollama`, `agent`, and `scheduler` as `Up`.
   - `docker compose logs -f ollama` ends with `Ready. Serving models.`; the agent log shows `✅ AGENT SERVER READY`.
   - Visit http://localhost:8000/evidence to ensure the FastAPI service responds.
4. **Monitor activity**
   - Tail `docker compose logs -f scheduler` for `Queued question` entries and `docker compose logs -f agent` for `Settlement submitted` lines.
   - Evidence artifacts appear under the `agent-state` volume (`state/evidence/` inside the container).
5. **Clean up safely**
   - Use `docker compose down` to stop services.
   - Remove `erc-8004-oracle-agent-dstack_agent-state` to reset agent state and `erc-8004-oracle-agent-dstack_ollama-data` to reclaim model storage.


## Operational Touchpoints

| Component / Endpoint               | Purpose                                                                 | Notes |
|------------------------------------|-------------------------------------------------------------------------|-------|
| `docker/.env.docker`               | Central configuration (RPC URLs, cadence, AI parameters, resolver key). | Copy from `.example`; never commit real secrets. |
| `ollama` service                   | Hosts the local Gemma3 model (`ollama/ollama` container).               | Exposes `${OLLAMA_HOST_PORT:-11434}`; edit compose for GPU flags if needed. |
| `scripts/schedule_oracle_requests.py` | Issues `requestPrice` calls against TeeOracle on a schedule.              | Uses DIA BTC price feed; interval/lookahead configurable. |
| FastAPI `/health`                  | Liveness probe for the agent container.                                 | Returns JSON heartbeat. |
| FastAPI `/api/status`              | Displays on-chain registration & resolver status.                        | Useful when debugging manual CLI runs. |
| FastAPI `/evidence`                | HTML explorer for `state/evidence/` artifacts (view/download).           | Evidence includes AI script, metadata, and `txHash`. |
| CLI `python scripts/agent_cli.py run` | Manually trigger a settlement cycle (AI by default, optional override).   | Reads the same environment variables as the container. |
| Named volume `agent-state`         | Persists agent ID, evidence, debug files between restarts.               | Remove via `docker volume rm …` for a clean slate. |

## Project Structure

```
erc-8004-oracle-agent-dstack/
├── docker-compose.yml         # Agent + scheduler services
├── docker/                    # Entrypoints and env templates
├── scripts/                   # CLI utilities and scheduler
├── deployment/                # FastAPI application
├── src/                       # Core agent libraries
├── docs/                      # Runbooks and references
└── state/                     # (ignored) runtime state for local/dev runs
```

## Deployed Contracts

We target the Base Sepolia deployment published in `contracts/deployments/base_sepolia_deployment.json`. The scheduler and agent expect those addresses unless overridden in the environment.

## Cleanup Plan

The repository still contains template-era scaffolding that we intend to remove. The following tasks are queued so the agent remains lightweight:

1. **Drop RedPill/attestation code paths** – `src/agent/ai_generator.py` and the verifier helpers (`verify_ai_attestation.py`) still contain unused logic. Remove once we fully commit to Ollama-only flows.
2. **Cull unused FastAPI routes** – endpoints like `/tasks`, `/api/metadata/update`, and legacy A2A flows are dormant. Audit and remove to reduce attack surface.
3. **Retire legacy front-end assets** – the dashboards in `static/` and references to `/developer` are stale; simplify to `/health` and `/evidence`.
4. **Trim documentation** – files such as `DEPLOYMENT.md`, `agent_config.json`, and VibeVM instructions describe superseded workflows. Update or archive.
5. **Simplify TEE verifier proof mode** – proof registration is still stubbed. Either implement fully or cut until we have a concrete requirement.

Please open a GitHub issue before tackling any of these so we can coordinate sequencing.
See [`docs/cleanup-plan.md`](docs/cleanup-plan.md) for the detailed scope and owners.

## Legacy Reference (Under Review)

> The sections below are carried over from the broader template. Treat them as background only until the cleanup plan above retires or rewrites them.

## Documentation

- **[DEV_GUIDE.md](DEV_GUIDE.md)** - Comprehensive developer guide covering:
  - Local development with VibeVM
  - Customizing your agent
  - Testing and debugging
  - Production deployment workflow

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment checklist:
  - Pre-deployment requirements
  - Phala CVM configuration
  - Post-deployment validation

- **[QUICKSTART.md](QUICKSTART.md)** - Get started in 3 minutes

## How It Works

1. **Key Derivation** - TEE derives wallet from `domain + salt`
2. **Local Development** - Test in VibeVM with simulated TEE
3. **Funding** - Add Base Sepolia ETH to derived wallet
4. **Registration** - Register agent on-chain (0.0001 ETH fee)
5. **TEE Attestation** - Submit cryptographic proof to verifier
6. **Production** - Deploy to Phala CVM with real TEE attestation
7. **Agent Live** - Accessible at `/agent.json` endpoint

## Tech Stack

- **TEE**: Intel TDX via Phala CVM/dstack
- **Blockchain**: Base Sepolia (testnet) / Base (mainnet)
- **Backend**: Python 3, FastAPI
- **Contracts**: Solidity ^0.8.20
- **Development**: VibeVM for local testing
- **Deployment**: Docker, Phala Cloud

## ERC-8004 Compliance

✅ Standard `/agent.json` endpoint (registration-v1)
✅ CAIP-10 wallet address format
✅ A2A protocol endpoints
✅ TEE attestation support
✅ On-chain registry integration
✅ Verifiable code measurement

## Customization

### Agent Metadata

Edit [agent_config.json](agent_config.json):

```json
{
  "name": "Your Agent Name",
  "description": "What your agent does",
  "endpoints": {
    "a2a": {"enabled": true},
    "mcp": {"enabled": false}
  }
}
```

### Agent Logic

Modify files in [src/agent/](src/agent/):

- Add custom endpoints in `deployment/local_agent_server.py`
- Implement custom logic in `src/agent/base.py`
- Configure blockchain interactions in `src/agent/registry.py`

### Build Process

Update [entrypoint.sh](entrypoint.sh) for custom setup:

```bash
# Add model downloads, DB initialization, etc.
echo "🤖 Downloading ML model..."
wget https://example.com/model.bin -O /app/model.bin
```

See [DEV_GUIDE.md](DEV_GUIDE.md) for detailed customization instructions.

## Deployment Checklist

Before deploying to production:

- [ ] Test thoroughly in VibeVM
- [ ] Update `agent_config.json` with production values
- [ ] Ensure `entrypoint.sh` has all required setup steps
- [ ] Commit production code to GitHub
- [ ] Note commit hash for deployment
- [ ] Set secrets on Phala: `GITHUB_REPO`, `GIT_COMMIT_HASH`, `AGENT_SALT`
- [ ] Configure CVM (2+ CPU, 4GB+ RAM, 10GB+ storage)
- [ ] Fund agent wallet with Base Sepolia ETH

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete checklist.

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/YOUR_USERNAME/erc-8004-tee-agent/issues)
- **Discussions**: [GitHub Discussions](https://github.com/YOUR_USERNAME/erc-8004-tee-agent/discussions)
- **Phala Discord**: [discord.gg/phala](https://discord.gg/phala)
- **VibeVM Docs**: [github.com/Phala-Network/VibeVM](https://github.com/Phala-Network/VibeVM)

## License

MIT

## Links

- **ERC-8004 Spec**: [eips.ethereum.org/EIPS/eip-8004](https://eips.ethereum.org/EIPS/eip-8004)
- **Phala Network**: [phala.network](https://phala.network)
- **VibeVM**: [github.com/Phala-Network/VibeVM](https://github.com/Phala-Network/VibeVM)
- **Base Sepolia**: [base.org](https://base.org)
- **Reference Implementation**: [dstack-erc8004-poc](https://github.com/h4x3rotab/dstack-erc8004-poc)

---

**Ready to build?** Start with [DEV_GUIDE.md](DEV_GUIDE.md) or jump into [QUICKSTART.md](QUICKSTART.md) 🚀
