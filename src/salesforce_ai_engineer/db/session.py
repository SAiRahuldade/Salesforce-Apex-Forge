"""Async SQLite database layer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from salesforce_ai_engineer.config.settings import DatabaseConfig
from salesforce_ai_engineer.db.base import Base


class DatabaseManager:
    """Owns the async SQLAlchemy engine and session factory."""

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config
        self.engine: AsyncEngine = create_async_engine(
            config.url,
            echo=config.echo,
            future=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def drop_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)

    async def health_check(self) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar_one() == 1

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_session(database: DatabaseManager) -> AsyncIterator[AsyncSession]:
    async with database.session() as session:
        yield session

