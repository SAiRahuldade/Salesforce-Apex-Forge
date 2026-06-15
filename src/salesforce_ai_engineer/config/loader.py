"""Structured configuration file loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigLoadError(RuntimeError):
    """Raised when a configuration file cannot be loaded."""


class YAMLConfigLoader:
    """Load YAML configuration documents into dictionaries."""

    def load(self, path: str | Path) -> dict[str, Any]:
        config_path = Path(path)
        if not config_path.exists():
            raise ConfigLoadError(f"Configuration file does not exist: {config_path}")
        if not config_path.is_file():
            raise ConfigLoadError(f"Configuration path is not a file: {config_path}")

        try:
            with config_path.open("r", encoding="utf-8") as file:
                loaded = yaml.safe_load(file) or {}
        except yaml.YAMLError as exc:
            raise ConfigLoadError(f"Invalid YAML in {config_path}: {exc}") from exc
        except OSError as exc:
            raise ConfigLoadError(f"Unable to read {config_path}: {exc}") from exc

        if not isinstance(loaded, dict):
            raise ConfigLoadError(f"Root YAML document must be a mapping: {config_path}")
        return loaded

