from salesforce_ai_engineer.config.settings import DatabaseConfig
from salesforce_ai_engineer.db import DatabaseManager


async def test_database_manager_health_check() -> None:
    database = DatabaseManager(DatabaseConfig(url="sqlite+aiosqlite:///:memory:"))

    try:
        assert await database.health_check() is True
    finally:
        await database.dispose()
