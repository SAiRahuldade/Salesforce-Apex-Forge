from pathlib import Path

import pytest

from salesforce_ai_engineer.core import FileManager, StateManager


def test_state_manager_persists_values(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    manager = StateManager(state_file)

    manager.set("run_id", "abc")
    reloaded = StateManager(state_file)

    assert reloaded.get("run_id") == "abc"


def test_file_manager_blocks_path_escape(tmp_path: Path) -> None:
    manager = FileManager(tmp_path)

    with pytest.raises(ValueError):
        manager.read_text("../outside.txt")

