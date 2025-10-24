from pathlib import Path

from src.utils.state import load_agent_state, save_agent_state


def test_state_roundtrip(tmp_path: Path):
    state_file = tmp_path / "agent.json"
    assert load_agent_state(state_file) == {}
    save_agent_state({"agent_id": 5}, state_file)
    assert load_agent_state(state_file)["agent_id"] == 5
