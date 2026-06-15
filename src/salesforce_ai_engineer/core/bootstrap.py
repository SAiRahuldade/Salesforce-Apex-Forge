"""Application infrastructure assembly.

This module bootstraps the dependency injection container with all components
including the Tool Layer (ToolRegistry, ToolExecutor) that agents use.
"""

from __future__ import annotations

from pathlib import Path

from salesforce_ai_engineer.agent import AgentRegistry, OllamaPlannerAgent, OrchestratorAgent
from salesforce_ai_engineer.agent.adapters import (
    DeploymentTaskAdapter,
    SalesforceEngineerTaskAdapter,
    VerifierTaskAdapter,
    WorkflowRecoveryAdapter,
)
from salesforce_ai_engineer.config import ConfigurationManager
from salesforce_ai_engineer.config.settings import Settings
from salesforce_ai_engineer.core.container import Container
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.core.files import FileManager
from salesforce_ai_engineer.core.logging import configure_logging
from salesforce_ai_engineer.core.state import StateManager
from salesforce_ai_engineer.deployment.agent import DeploymentAgent
from salesforce_ai_engineer.deployment.cli_helper import SalesforceCliHelper
from salesforce_ai_engineer.deployment.models import (
    ConnectionType,
    DeploymentConnection,
    DeploymentEnvironment,
)
from salesforce_ai_engineer.memory import MemoryManager, SQLiteMemoryStore
from salesforce_ai_engineer.recovery.agent import RecoveryAgent
from salesforce_ai_engineer.reward_learning import build_reward_learning_engine
from salesforce_ai_engineer.salesforce_engineer.agent import SalesforceEngineerAgent
from salesforce_ai_engineer.tools.factory import build_tool_executor, build_tool_registry
from salesforce_ai_engineer.verifier.agent import VerifierAgent
from salesforce_ai_engineer.workflow import WorkflowExecutionEngine
from salesforce_ai_engineer.db import DatabaseManager


def _build_default_connection(settings: Settings) -> DeploymentConnection | None:
    sf = settings.salesforce
    if not sf.default_org_alias and not sf.org_id:
        return None
    try:
        connection_type = ConnectionType(sf.auth_type.lower())
    except ValueError:
        connection_type = ConnectionType.SFDX
    return DeploymentConnection(
        connection_type=connection_type,
        org_id=sf.org_id or "local-org",
        org_name=sf.default_org_alias or "default",
        environment=(
            DeploymentEnvironment.PRODUCTION if sf.is_production else DeploymentEnvironment.SANDBOX
        ),
        instance_url=sf.instance_url,
        api_version=sf.api_version,
        is_production=sf.is_production,
    )


def _build_agent_registry(services: Container) -> AgentRegistry:
    settings = services.resolve("settings", Settings)
    event_bus = services.resolve("event_bus", EventBus)
    memory_manager = services.resolve("memory_manager", MemoryManager)
    tool_executor = services.resolve("tool_executor")
    logger = services.resolve("logger")

    cli_helper = SalesforceCliHelper(
        tool_executor=tool_executor,
        default_org=settings.salesforce.default_org_alias,
        enabled=settings.salesforce.cli_enabled,
    )
    default_connection = _build_default_connection(settings)

    engineer = SalesforceEngineerAgent(
        event_bus=event_bus,
        memory_manager=memory_manager,
        logger=logger,
        tool_executor=tool_executor,
    )
    verifier = VerifierAgent(event_bus=event_bus, memory_manager=memory_manager)
    deployment = DeploymentAgent(
        event_bus=event_bus,
        memory_manager=memory_manager,
        tool_executor=tool_executor,
        cli_helper=cli_helper,
        default_connection=default_connection,
    )

    registry = AgentRegistry()
    registry.register("salesforce_engineer", SalesforceEngineerTaskAdapter(engineer, tool_executor))
    registry.register("verifier", VerifierTaskAdapter(verifier))
    registry.register_aliases("deployment", DeploymentTaskAdapter(deployment, default_connection), "deployment_agent")
    return registry


def build_container(config_manager: ConfigurationManager | None = None) -> Container:
    """Create the shared dependency graph used by API, CLI, and agents."""

    manager = config_manager or ConfigurationManager()
    manager.ensure_runtime_directories()
    settings = manager.settings

    container = Container()

    container.register_instance("config_manager", manager)
    container.register_instance("settings", settings)
    container.register_instance("logger", configure_logging(settings.logging, settings.app.name))
    container.register_instance("event_bus", EventBus())
    container.register_instance("file_manager", FileManager(Path.cwd()))

    container.register_factory(
        "tool_registry",
        lambda services: build_tool_registry(settings, Path.cwd()),
        singleton=True,
    )
    container.register_factory(
        "tool_executor",
        lambda services: build_tool_executor(
            registry=services.resolve("tool_registry"),
            event_bus=services.resolve("event_bus", EventBus),
            logger_instance=services.resolve("logger"),
        ),
        singleton=True,
    )

    container.register_factory(
        "state_manager",
        lambda _: StateManager(settings.state.path),
        singleton=True,
    )
    container.register_factory(
        "database",
        lambda _: DatabaseManager(settings.database) if DatabaseManager is not None else None,
        singleton=True,
    )

    container.register_factory(
        "memory_store",
        lambda _: SQLiteMemoryStore(Path(settings.memory.db_path)),
        singleton=True,
    )
    container.register_factory(
        "memory_manager",
        lambda services: MemoryManager(
            store=services.resolve("memory_store", SQLiteMemoryStore),
            event_bus=services.resolve("event_bus", EventBus),
            logger_instance=services.resolve("logger"),
        ),
        singleton=True,
    )
    container.register_factory(
        "reward_learning_engine",
        lambda services: build_reward_learning_engine(
            memory_manager=services.resolve("memory_manager", MemoryManager),
            event_bus=services.resolve("event_bus", EventBus),
        ),
        singleton=True,
    )

    container.register_factory("agent_registry", _build_agent_registry, singleton=True)

    container.register_factory(
        "recovery_agent",
        lambda services: WorkflowRecoveryAdapter(
            RecoveryAgent(
                event_bus=services.resolve("event_bus", EventBus),
                memory_manager=services.resolve("memory_manager", MemoryManager),
                tool_layer=services.resolve("tool_executor"),
            )
        ),
        singleton=True,
    )

    container.register_factory(
        "planner_agent",
        lambda services: OllamaPlannerAgent(
            services.resolve("settings").ollama,
            registered_agents=services.resolve("agent_registry", AgentRegistry).registered_names(),
            memory_manager=services.resolve("memory_manager", MemoryManager),
            reward_learning_engine=services.resolve("reward_learning_engine"),
        ),
        singleton=True,
    )

    container.register_factory(
        "workflow_engine",
        lambda services: WorkflowExecutionEngine(
            agent_registry=services.resolve("agent_registry", AgentRegistry),
            recovery_agent=services.resolve("recovery_agent"),
            event_bus=services.resolve("event_bus", EventBus),
            memory_manager=services.resolve("memory_manager", MemoryManager),
            state_manager=services.resolve("state_manager", StateManager),
        ),
        singleton=True,
    )

    container.register_factory(
        "orchestrator_agent",
        lambda services: OrchestratorAgent(
            planner=services.resolve("planner_agent"),
            recovery_agent=services.resolve("recovery_agent"),
            agent_registry=services.resolve("agent_registry", AgentRegistry),
            state_manager=services.resolve("state_manager", StateManager),
            event_bus=services.resolve("event_bus", EventBus),
            memory_manager=services.resolve("memory_manager", MemoryManager),
            reward_learning_engine=services.resolve("reward_learning_engine"),
            workflow_engine=services.resolve("workflow_engine", WorkflowExecutionEngine),
        ),
        singleton=True,
    )

    return container


# NOTE: Do NOT eagerly build the container at module import time.
# Building opens SQLite, connects events, and triggers heavy agent module imports,
# which breaks test isolation and slows cold starts. Callers should use
# `get_container()` or pass an explicit `container=` to `APIContainer.initialize()`.
_container_instance: "Container | None" = None


def get_container() -> Container:
    """Return the lazily-initialized singleton container."""

    global _container_instance
    if _container_instance is None:
        _container_instance = build_container()
    return _container_instance


def reset_container() -> None:
    """Reset the singleton container (test helper)."""

    global _container_instance
    _container_instance = None
