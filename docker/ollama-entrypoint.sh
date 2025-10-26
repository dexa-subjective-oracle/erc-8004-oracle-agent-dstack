#!/bin/sh
set -eu

MODEL="${OLLAMA_MODEL:-gemma3:4b}"
EXTRA_MODELS="${OLLAMA_BOOTSTRAP_MODELS:-}"

log() {
  printf '%s %s\n' "[ollama-entrypoint]" "$*"
}

pull_model() {
  name="$1"
  if [ -z "$name" ]; then
    return
  fi
  log "Pulling model '${name}'..."
  /bin/ollama pull "$name" || log "Warning: failed to pull '${name}' (continuing)"
}

log "Starting ollama serve (model preload: ${MODEL})..."
/bin/ollama serve &
SERVER_PID=$!

cleanup() {
  log "Shutting down ollama (PID ${SERVER_PID})"
  kill "${SERVER_PID}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

log "Waiting for Ollama API to become responsive..."
until /bin/ollama list >/dev/null 2>&1; do
  sleep 1
done

pull_model "${MODEL}"

if [ -n "${EXTRA_MODELS}" ]; then
  for extra in $(printf '%s' "${EXTRA_MODELS}" | tr ',' ' '); do
    pull_model "${extra}"
  done
fi

log "Ready. Serving models."

wait "${SERVER_PID}"
