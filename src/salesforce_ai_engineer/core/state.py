"""Persistent local state manager."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from salesforce_ai_engineer.core.json import read_json, write_json


class StateManager:
    """Thread-safe JSON-backed key/value state."""

    def __init__(self, state_path: str | Path) -> None:
        # Tests sometimes pass a directory path (e.g. TemporaryDirectory()).
        # In that case we store JSON state in a deterministic file inside the directory.
        raw_path = Path(state_path)
        if raw_path.exists() and raw_path.is_dir():
            self.state_path = raw_path / "state.json"
        else:
            # If it's intended to be a directory but doesn't exist yet, treat it as a directory anyway
            # when it has no suffix.
            if raw_path.suffix == "":
                self.state_path = raw_path / "state.json"
            else:
                self.state_path = raw_path

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._state: dict[str, Any] = self._load()


    def get(self, key: str, default: Any | None = None) -> Any:
        with self._lock:
            return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._state[key] = value
            self.flush()

    def delete(self, key: str) -> None:
        with self._lock:
            self._state.pop(key, None)
            self.flush()

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._state.update(values)
            self.flush()

    def flush(self) -> None:
        write_json(self.state_path, self._state)

    def _load(self) -> dict[str, Any]:
        loaded = read_json(self.state_path, default={})
        if not isinstance(loaded, dict):
            raise ValueError(f"State file must contain a JSON object: {self.state_path}")
        return loaded

