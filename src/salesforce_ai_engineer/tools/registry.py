"""Registry for tool implementations.

The ToolRegistry provides:
1. Tool registration with alias support
2. Tool resolution by name (normalized case-insensitive)
3. Tool discovery API for agents to introspect available tools
4. Tool schema generation for agents to understand tool inputs

This enables the tool layer to be truly extensible - new tools can be
registered without modifying the core agent logic.
"""

from __future__ import annotations

from typing import Any, get_type_hints

from pydantic import BaseModel

from salesforce_ai_engineer.tools.base import BaseTool
from salesforce_ai_engineer.tools.errors import ToolNotFoundError


class ToolSchema(BaseModel):
    """Schema describing a tool's interface for agent discovery."""

    name: str
    """Tool name used in ToolRequest.tool_name"""

    description: str
    """Human-readable description of tool purpose and behavior"""

    input_schema: dict[str, Any] | None = None
    """JSON Schema for tool input validation (from Pydantic model)"""

    input_example: dict[str, Any] | None = None
    """Example input demonstrating tool usage"""


class ToolRegistry:
    """Open-ended registry mapping tool names to implementations.
    
    Features:
    - Case-insensitive tool name resolution
    - Alias support (one tool, multiple names)
    - Discovery API for agent introspection
    - Schema generation from Pydantic models
    
    Usage:
        registry = ToolRegistry()
        registry.register(FilesystemTool(), "file", "fs")  # Multiple names
        tool = registry.resolve("file")  # Case-insensitive
        schemas = registry.all_schemas()  # Discover tools
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool, *aliases: str) -> None:
        """Register tool with primary name and optional aliases.
        
        Args:
            tool: BaseTool implementation
            aliases: Additional names for the tool (e.g., "file", "fs")
            
        Raises:
            ValueError: If tool name is empty
        """

        for name in (tool.name, *aliases):
            normalized = self._normalize(name)
            self._tools[normalized] = tool

    def resolve(self, name: str) -> BaseTool:
        """Resolve tool by name (case-insensitive).
        
        Args:
            name: Tool name (normalized internally)
            
        Returns:
            BaseTool implementation
            
        Raises:
            ToolNotFoundError: If tool not registered
        """

        normalized = self._normalize(name)
        try:
            return self._tools[normalized]
        except KeyError as exc:
            raise ToolNotFoundError(f"No tool registered for {name!r}") from exc

    def names(self) -> list[str]:
        """Return all registered tool names (alphabetically sorted).
        
        Returns:
            List of normalized tool names
        """

        return sorted(set(self._tools.keys()))

    def all_schemas(self) -> list[ToolSchema]:
        """Generate schema for all registered tools.
        
        Returns:
            List of ToolSchema describing each unique tool
            (deduplicates aliases)
        """

        seen: set[str] = set()
        schemas: list[ToolSchema] = []

        for tool in self._tools.values():
            if tool.name in seen:
                continue
            seen.add(tool.name)
            schemas.append(self._schema_for(tool))

        return sorted(schemas, key=lambda s: s.name)

    def schema_for(self, name: str) -> ToolSchema:
        """Generate schema for a specific tool.
        
        Args:
            name: Tool name
            
        Returns:
            ToolSchema describing the tool's interface
            
        Raises:
            ToolNotFoundError: If tool not registered
        """

        tool = self.resolve(name)
        return self._schema_for(tool)

    def _schema_for(self, tool: BaseTool) -> ToolSchema:
        """Build ToolSchema from tool metadata and Pydantic model.
        
        Args:
            tool: BaseTool implementation
            
        Returns:
            ToolSchema with input specification
        """

        input_schema = None
        input_example = None

        if tool.input_model and issubclass(tool.input_model, BaseModel):
            # Extract JSON Schema from Pydantic model
            input_schema = tool.input_model.model_json_schema()

            # Generate example from model schema
            example_data = {}
            for field_name, field_info in tool.input_model.model_fields.items():
                if field_info.default is not None:
                    example_data[field_name] = field_info.default
                else:
                    # Use type annotation as hint
                    type_hint = field_info.annotation
                    if type_hint in (str, int, float, bool):
                        example_data[field_name] = type_hint.__name__.lower()
                    elif hasattr(type_hint, "__origin__"):
                        if type_hint.__origin__ is list:
                            example_data[field_name] = []
                        elif type_hint.__origin__ is dict:
                            example_data[field_name] = {}
                    else:
                        example_data[field_name] = None

            input_example = example_data

        return ToolSchema(
            name=tool.name,
            description=tool.description,
            input_schema=input_schema,
            input_example=input_example,
        )

    def _normalize(self, name: str) -> str:
        """Normalize tool name to lowercase, stripped.
        
        Args:
            name: Raw tool name
            
        Returns:
            Normalized name
            
        Raises:
            ValueError: If name is empty after normalization
        """

        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("Tool name cannot be empty")
        return normalized

