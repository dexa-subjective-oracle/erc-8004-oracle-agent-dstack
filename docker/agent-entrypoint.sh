#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${STATE_DIR:-/app/state}"
ln -sfn /app /app/erc-8004-oracle-agent-dstack
ln -sfn /app /erc-8004-oracle-agent-dstack
mkdir -p "${STATE_DIR}" "${STATE_DIR}/evidence" "${STATE_DIR}/debug"

export PYTHONPATH=${PYTHONPATH:-/app}
export AGENT_STATE_FILE="${AGENT_STATE_FILE:-${STATE_DIR}/agent.json}"

if [ ! -f "${AGENT_STATE_FILE}" ]; then
  mkdir -p "$(dirname "${AGENT_STATE_FILE}")"
  echo '{}' > "${AGENT_STATE_FILE}"
fi

echo "[agent-entrypoint] AI_PROVIDER=${AI_PROVIDER:-unset}"

if [[ "${AI_PROVIDER:-}" == "ollama" ]]; then
  python - <<'PY'
import os
import time
import requests

base = os.getenv("AI_API_BASE") or "http://ollama:11434"
if base.endswith("/v1"):
    base = base[:-3]
base = base.rstrip("/")
model = os.getenv("AI_MODEL") or os.getenv("OLLAMA_MODEL") or "gemma3:4b"
timeout = float(os.getenv("OLLAMA_WAIT_TIMEOUT", "900"))
deadline = time.time() + timeout
url = f"{base}/api/show"
payload = {"name": model}

print(f"[agent-entrypoint] Waiting for Ollama model '{model}' at {url} (timeout {timeout}s)...", flush=True)
poll_interval = float(os.getenv("OLLAMA_WAIT_INTERVAL", "5"))

while True:
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("[agent-entrypoint] Ollama model is ready.", flush=True)
            break
        msg = response.text.strip()
        print(f"[agent-entrypoint] Ollama responded {response.status_code}: {msg[:120]}", flush=True)
    except Exception as exc:  # pragma: no cover - best effort logging
        print(f"[agent-entrypoint] Ollama probe failed: {exc}", flush=True)

    if time.time() > deadline:
        raise SystemExit(f"Timed out waiting for Ollama model '{model}' after {timeout} seconds")

    time.sleep(poll_interval)
PY
fi

exec python deployment/local_agent_server.py
