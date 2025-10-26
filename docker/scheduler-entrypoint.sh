#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${STATE_DIR:-/app/state}"
ln -sfn /app /app/erc-8004-oracle-agent-dstack
ln -sfn /app /erc-8004-oracle-agent-dstack
mkdir -p "${STATE_DIR}"

export PYTHONPATH=${PYTHONPATH:-/app}

exec python scripts/schedule_oracle_requests.py
