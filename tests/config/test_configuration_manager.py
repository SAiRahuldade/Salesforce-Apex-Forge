from pathlib import Path

from salesforce_ai_engineer.config import ConfigurationManager


def test_configuration_manager_loads_yaml_and_environment(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
app:
  name: test-agent
logging:
  directory: test-logs
database:
  url: sqlite+aiosqlite:///test-state/test.db
ollama:
  base_url: http://localhost:11434
  model: llama3.1
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_NAME", "env-agent")

    manager = ConfigurationManager(config_file)
    settings = manager.load()

    assert settings.app.name == "env-agent"
    assert settings.database.url == "sqlite+aiosqlite:///test-state/test.db"

