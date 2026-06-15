"""Factory for building the production tool registry.

This module provides factory functions to construct a fully-initialized ToolRegistry
with all built-in tool implementations, along with the ToolExecutor for safe dispatch.

The factory pattern enables:
- Centralized tool registration without coupling agents to implementations
- Easy addition of new tools without modifying agent code
- Support for dependency injection with settings/configuration
- Future extensibility with custom tool factories

Usage:
    registry = build_tool_registry(settings, workspace_root)
    executor = build_tool_executor(registry, event_bus)
    
    # Agents interact only through executor
    response = await executor.execute(tool_request)
"""

from __future__ import annotations

import logging
from pathlib import Path

from salesforce_ai_engineer.config.settings import Settings
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.tools.command import GitTool, ShellCommandTool
from salesforce_ai_engineer.tools.executor import ToolExecutor
from salesforce_ai_engineer.tools.filesystem.tool import FilesystemTool
from salesforce_ai_engineer.tools.http import HttpTool
from salesforce_ai_engineer.tools.ollama.tool import OllamaTool
from salesforce_ai_engineer.tools.registry import ToolRegistry
from salesforce_ai_engineer.tools.salesforce.cli import SalesforceCliTool
from salesforce_ai_engineer.tools.shell.executor import CommandTool, ShellTool
from salesforce_ai_engineer.tools.sqlite import SQLiteTool
from salesforce_ai_engineer.tools.structured_data import JSONTool, XMLTool, YAMLTool

logger = logging.getLogger(__name__)


def build_tool_registry(settings: Settings, workspace_root: Path) -> ToolRegistry:
    """Build the complete tool registry with all built-in tools.
    
    This factory registers all tools that agents can invoke:
    - Salesforce CLI (sf) - sf commands, org management, deployment
    - Git - version control operations
    - Filesystem (fs) - safe file system access with sandbox
    - Shell - arbitrary shell command execution (use with caution)
    - Command - structured command execution (safer alternative)
    - SQLite - database operations
    - HTTP/REST - API calls
    - Ollama (llm) - local LLM interactions
    - JSON - JSON parsing/formatting
    - YAML/YML - YAML parsing/formatting
    - XML - XML parsing/formatting
    
    Args:
        settings: Application settings (for tool-specific config like Ollama)
        workspace_root: Root path for filesystem sandboxing
        
    Returns:
        Fully initialized ToolRegistry
        
    Example:
        registry = build_tool_registry(settings, Path.cwd())
        names = registry.names()  # List available tools
        schema = registry.schema_for("git")  # Introspect tool
    """

    registry = ToolRegistry()

    # Salesforce tools
    registry.register(SalesforceCliTool(), "sf", "sfdx", "salesforce")

    # Version control
    registry.register(GitTool(), "vcs")

    # Filesystem (sandboxed)
    registry.register(FilesystemTool(workspace_root), "fs", "file")

    # Shell and command execution
    registry.register(ShellTool(), "bash", "powershell", "cmd")
    registry.register(CommandTool(), "exec", "run")

    # Legacy command tools (backward compatibility)
    registry.register(ShellCommandTool())

    # Database
    registry.register(SQLiteTool(), "db", "sqlite")

    # HTTP/API
    registry.register(HttpTool(), "rest", "http", "api")

    # Ollama/LLM
    registry.register(OllamaTool(settings.ollama), "llm", "ai")

    # Structured data
    registry.register(JSONTool())
    registry.register(YAMLTool(), "yml", "yaml")
    registry.register(XMLTool())

    logger.info(
        "Tool registry initialized with %d tools",
        len(registry.names()),
        extra={"tools": registry.names()},
    )

    return registry


def build_tool_executor(
    registry: ToolRegistry,
    event_bus: EventBus,
    logger_instance: logging.Logger | None = None,
) -> ToolExecutor:
    """Build the ToolExecutor facade for dispatch.
    
    The executor wraps the registry and adds:
    - Event emission for lifecycle tracking
    - Structured logging
    - Correlation ID propagation
    
    Args:
        registry: ToolRegistry with registered tools
        event_bus: EventBus for lifecycle events
        logger_instance: Logger for execution events
        
    Returns:
        ToolExecutor ready for agent use
        
    Example:
        executor = build_tool_executor(registry, event_bus)
        response = await executor.execute(request)
    """

    return ToolExecutor(registry, event_bus, logger_instance or logger)

