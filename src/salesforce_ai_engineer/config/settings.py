"""Typed application settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl


class AppConfig(BaseModel):
    name: str = "local-salesforce-ai-engineer"
    environment: str = "local"
    version: str = "0.1.0"


class CorsConfig(BaseModel):
    """CORS allowlist. Empty list disables CORS entirely."""

    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:8000",
        ]
    )
    allowed_methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )
    allowed_headers: list[str] = Field(
        default_factory=lambda: [
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-API-Key",
        ]
    )
    expose_headers: list[str] = Field(default_factory=lambda: ["X-Request-ID"])
    max_age_seconds: int = 600


class SecurityConfig(BaseModel):
    """Runtime security knobs."""

    max_request_bytes: int = 1 * 1024 * 1024
    enable_metrics_endpoint: bool = True


class LoggingConfig(BaseModel):
    level: str = "INFO"
    directory: Path = Path("logs")
    rich_tracebacks: bool = True


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///state/agent.db"
    echo: bool = False


class OllamaConfig(BaseModel):
    base_url: HttpUrl = Field(default="http://localhost:11434")
    model: str = "llama3.1"
    api_key: str = ""


class MemoryConfig(BaseModel):
    directory: Path = Path("memory")
    db_name: str = "system.db"

    @property
    def db_path(self) -> Path:
        return self.directory / self.db_name


class StateConfig(BaseModel):
    directory: Path = Path("state")
    file_name: str = "runtime_state.json"

    @property
    def path(self) -> Path:
        return self.directory / self.file_name


class SalesforceConfig(BaseModel):
    """Salesforce org and CLI connection settings."""

    default_org_alias: str = ""
    auth_type: str = "sfdx"
    org_id: str = ""
    instance_url: str = "https://login.salesforce.com"
    api_version: str = "60.0"
    is_production: bool = False
    cli_enabled: bool = True
    access_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    username: str = ""
    password: str = ""
    security_token: str = ""


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    state: StateConfig = Field(default_factory=StateConfig)
    salesforce: SalesforceConfig = Field(default_factory=SalesforceConfig)
