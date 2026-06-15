"""FastAPI dependency providers."""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from salesforce_ai_engineer.config import Settings
from salesforce_ai_engineer.core.bootstrap import get_container as _bootstrap_get_container
from salesforce_ai_engineer.core.container import Container

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class APIContainer:
    """Container for API-level dependencies."""

    _instance: "APIContainer | None" = None
    _container: Container | None = None

    def __new__(cls) -> "APIContainer":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self, container: Container) -> None:
        """Initialize with core container."""
        self._container = container

    @property
    def container(self) -> Container:
        """Get the core container."""
        if self._container is None:
            raise RuntimeError("APIContainer not initialized. Call initialize() first.")
        return self._container

    @property
    def orchestrator(self):
        """Get the orchestrator agent."""
        return self.container.resolve("orchestrator_agent")

    @property
    def workflow_engine(self):
        """Get the workflow execution engine."""
        return self.container.resolve("workflow_engine")

    @property
    def agent_registry(self):
        """Get the agent registry."""
        return self.container.resolve("agent_registry")

    @property
    def memory_manager(self):
        """Get the memory manager."""
        return self.container.resolve("memory_manager")

    @property
    def event_bus(self):
        """Get the event bus."""
        return self.container.resolve("event_bus")

    @property
    def state_manager(self):
        """Get the state manager."""
        return self.container.resolve("state_manager")

    @property
    def reward_learning_engine(self):
        """Get the reward learning engine."""
        return self.container.resolve("reward_learning_engine")


_api_container = APIContainer()


async def get_container_dep() -> AsyncIterator[APIContainer]:
    """Dependency injection for container."""
    yield _api_container


def get_api_container() -> APIContainer:
    """Get the API container instance."""
    return _api_container


def get_container() -> Container:
    return _bootstrap_get_container()


def get_settings() -> Settings:
    return _bootstrap_get_container().resolve("settings", Settings)
