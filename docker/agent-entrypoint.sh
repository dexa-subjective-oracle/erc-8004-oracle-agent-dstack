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

exec python deployment/local_agent_server.py
