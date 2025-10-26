# Docker Quickstart

This guide packages the Base Sepolia subjective-oracle demo into two containers—one for the FastAPI agent and one for the price-request scheduler—so you can launch the full stack with a single `docker compose up`.

## 1. Prepare configuration

1. Copy the example environment file and fill in the blanks (RPC endpoint + resolver key):
   ```bash
   cd erc-8004-oracle-agent-dstack
   cp docker/.env.docker.example docker/.env.docker
   ```
2. Edit `docker/.env.docker` and set:
   - `BASE_SEPOLIA_RPC_URL` and `RPC_URL` to your Base Sepolia endpoint.
   - `RESOLVER_PRIVATE_KEY` to the funded wallet that will register the manual key and pay for gas.
   - Optional: update AI/OLLAMA settings if you use a different provider.

The contract addresses already match `contracts/deployments/base_sepolia_deployment.json`.

## 2. Build & launch

From the agent directory:
```bash
docker compose --env-file docker/.env.docker up --build
```

Compose spins up three services using the shared image built from the local sources:

- **ollama** — serves the Gemma 3 4B model on `OLLAMA_HOST_PORT` (default `11434`).
- **agent** — runs `deployment/local_agent_server.py`, registers the manual resolver key, starts the oracle worker, and exposes FastAPI on port `AGENT_HOST_PORT` (default `8000`).
- **scheduler** — runs `scripts/schedule_oracle_requests.py` on the configured cadence, queueing new UMA requests against the Base Sepolia contracts.

The agent and scheduler share the `agent-state` named volume, which holds `state/` artifacts (agent ID, evidence, debug files). The Ollama container uses the `ollama-data` volume to cache downloaded models.

## 3. Monitor & interact

- Tail logs:
  ```bash
  docker compose logs -f agent
  docker compose logs -f scheduler
  docker compose logs -f ollama
  ```
- Browse evidence artifacts: http://localhost:8000/evidence
- Inspect pending requests or settled txs with `cast`, using the environment variables from `docker/.env.docker`.
- The FastAPI docs remain reachable at http://localhost:8000/docs.

## 4. Shutdown & cleanup

```bash
docker compose down
docker volume rm erc-8004-oracle-agent-dstack_agent-state  # optional: clear state
docker volume rm erc-8004-oracle-agent-dstack_ollama-data   # optional: clear Ollama cache
rm docker/.env.docker                                       # optional: remove secrets
```

### GPU Notes

- **NVIDIA**: install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) and add `--gpus all` (or `runtime: nvidia`) to the `ollama` service in `docker-compose.yml`.
- **AMD**: swap the image for `ollama/ollama:rocm` and mount `/dev/kfd` + `/dev/dri` per Ollama’s documentation.

You now have a single-command workflow to run the Base Sepolia subjective-oracle demo end to end in Docker.
