"""Simple state persistence helpers for storing agent metadata locally."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Any

DEFAULT_STATE_FILE = Path("state/agent.json")


def load_agent_state(path: Path | None = None) -> Dict[str, Any]:
    file_path = path or DEFAULT_STATE_FILE
    if not file_path.exists():
        return {}
    try:
        with file_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return {}


def save_agent_state(state: Dict[str, Any], path: Path | None = None) -> None:
    file_path = path or DEFAULT_STATE_FILE
    if not file_path.parent.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
