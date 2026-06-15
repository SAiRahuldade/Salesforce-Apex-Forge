"""Configuration manager shared across application entry points."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from salesforce_ai_engineer.config.loader import YAMLConfigLoader
from salesforce_ai_engineer.config.settings import Settings


class ConfigurationError(RuntimeError):
    """Raised when application configuration cannot be assembled."""


class ConfigurationManager:
    """Load typed settings from YAML with environment variable overrides."""

    ENV_TO_PATH = {
        "APP_NAME": ("app", "name"),
        "APP_ENV": ("app", "environment"),
        "LOG_LEVEL": ("logging", "level"),
        "DATABASE_URL": ("database", "url"),
        "OLLAMA_BASE_URL": ("ollama", "base_url"),
        "OLLAMA_MODEL": ("ollama", "model"),
        "MEMORY_DIR": ("memory", "directory"),
        "STATE_DIR": ("state", "directory"),
        "STATE_FILE_NAME": ("state", "file_name"),
        "SF_DEFAULT_ORG_ALIAS": ("salesforce", "default_org_alias"),
        "SF_AUTH_TYPE": ("salesforce", "auth_type"),
        "SF_ORG_ID": ("salesforce", "org_id"),
        "SF_INSTANCE_URL": ("salesforce", "instance_url"),
        "SF_API_VERSION": ("salesforce", "api_version"),
        "SF_IS_PRODUCTION": ("salesforce", "is_production"),
        "SF_CLI_ENABLED": ("salesforce", "cli_enabled"),
        "SF_CLIENT_ID": ("salesforce", "client_id"),
        "SF_CLIENT_SECRET": ("salesforce", "client_secret"),
        "SF_USERNAME": ("salesforce", "username"),
        "SF_PASSWORD": ("salesforce", "password"),
        "SF_SECURITY_TOKEN": ("salesforce", "security_token"),
    }

    def __init__(
        self,
        config_path: str | Path = "config/settings.yaml",
        loader: YAMLConfigLoader | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.loader = loader or YAMLConfigLoader()
        self._settings: Settings | None = None

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = self.load()
        return self._settings

    def load(self) -> Settings:
        raw = self.loader.load(self.config_path)
        merged = self._apply_environment(raw)
        try:
            settings = Settings.model_validate(merged)
        except ValidationError as exc:
            raise ConfigurationError(f"Invalid application configuration: {exc}") from exc
        self._settings = settings
        return settings

    def reload(self) -> Settings:
        self._settings = None
        return self.settings

    def ensure_runtime_directories(self) -> None:
        settings = self.settings
        directories = [
            settings.logging.directory,
            settings.memory.directory,
            settings.state.directory,
        ]
        database_directory = self._sqlite_directory(settings.database.url)
        if database_directory is not None:
            directories.append(database_directory)

        for directory in directories:
            if str(directory) and str(directory) != ".":
                directory.mkdir(parents=True, exist_ok=True)

    def _sqlite_directory(self, database_url: str) -> Path | None:
        parsed = urlparse(database_url)
        if not parsed.scheme.startswith("sqlite"):
            return None
        if database_url.endswith(":memory:"):
            return None
        path = parsed.path.lstrip("/")
        if not path:
            return None
        return Path(path).parent

    def _apply_environment(self, raw: dict[str, Any]) -> dict[str, Any]:
        merged = dict(raw)
        for env_name, path in self.ENV_TO_PATH.items():
            value = os.getenv(env_name)
            if value is None:
                continue
            cursor = merged
            for key in path[:-1]:
                cursor = cursor.setdefault(key, {})
            if path[-1] in {"is_production", "cli_enabled"}:
                cursor[path[-1]] = value.lower() in {"1", "true", "yes", "on"}
            else:
                cursor[path[-1]] = value
        return merged


config_manager = ConfigurationManager()
