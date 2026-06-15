"""Comprehensive tests for the tool layer architecture.

This test suite covers:
- BaseTool execution with retry and timeout logic
- Error classification and recovery
- Tool registry and discovery API
- Structured request/response models
- Exponential backoff behavior
- Response size limits
- Tool-specific implementations
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel

from salesforce_ai_engineer.models.domain import ToolErrorType, ToolRequest, ToolResponse, ToolStatus, utc_now
from salesforce_ai_engineer.tools.base import BaseTool, ToolRuntimeConfig
from salesforce_ai_engineer.tools.errors import (
    ToolNotFoundError,
    ToolTimeoutError,
    ToolValidationError,
    classify_error,
)
from salesforce_ai_engineer.tools.registry import ToolRegistry, ToolSchema
from salesforce_ai_engineer.tools.structured_data import JSONTool, YAMLTool, XMLTool
from salesforce_ai_engineer.tools.shell.executor import ShellTool, CommandTool
from salesforce_ai_engineer.tools.http import HttpTool


# ============================================================================
# Test Models
# ============================================================================


class MockToolInput(BaseModel):
    """Simple input model for testing."""

    action: str
    should_fail: bool = False
    should_timeout: bool = False
    delay: float = 0.0


class MockTool(BaseTool):
    """Mock tool for testing BaseTool behavior."""

    name = "mock"
    description = "Mock tool for testing"
    input_model = MockToolInput

    async def _run(self, payload: MockToolInput, request: ToolRequest) -> dict[str, any]:
        """Simulate tool execution with configurable behavior."""

        await asyncio.sleep(payload.delay)

        if payload.should_timeout:
            await asyncio.sleep(100)  # Will be interrupted by timeout

        if payload.should_fail:
            raise ValueError(f"Mock tool error: {payload.action}")

        return {
            "action": payload.action,
            "result": "success",
            "timestamp": utc_now().isoformat(),
        }


# ============================================================================
# BaseTool Tests
# ============================================================================


class TestBaseToolExecution:
    """Test BaseTool execution framework."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Test successful tool execution."""

        tool = MockTool()
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="mock",
            input={"action": "test", "should_fail": False},
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.SUCCESS
        assert response.tool_name == "mock"
        assert response.output["result"] == "success"
        assert response.output["action"] == "test"
        assert response.error is None
        assert response.attempts == 1

    @pytest.mark.asyncio
    async def test_execution_with_metrics(self):
        """Test that metrics are collected during execution."""

        tool = MockTool()
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="mock",
            input={"action": "test"},
        )

        response = await tool.execute(request)

        assert "duration_seconds" in response.metrics
        assert "started_at" in response.metrics
        assert "completed_at" in response.metrics
        assert "tool_name" in response.metrics
        assert response.metrics["tool_name"] == "mock"

    @pytest.mark.asyncio
    async def test_input_validation(self):
        """Test that input validation occurs before execution."""

        tool = MockTool()

        # Invalid input (missing required field)
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="mock",
            input={"should_fail": False},  # Missing 'action'
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.FAILED
        assert response.error is not None
        assert "action" in response.error.lower()

    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self):
        """Test retry logic for transient errors."""

        tool = MockTool(config=ToolRuntimeConfig(default_retries=2))
        
        call_count = 0

        async def mock_run(payload, request):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise asyncio.TimeoutError("Transient timeout")
            return {"result": "success", "attempts": call_count}

        tool._run = mock_run

        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="mock",
            input={"action": "test"},
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.SUCCESS
        assert response.attempts == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test that retries are exhausted after max attempts."""

        tool = MockTool(config=ToolRuntimeConfig(default_retries=1))
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="mock",
            input={"action": "test", "should_fail": True},
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.FAILED
        assert response.attempts == 2  # 1 retry = 2 attempts

    @pytest.mark.asyncio
    async def test_timeout_protection(self):
        """Test timeout protection during execution."""

        tool = MockTool(config=ToolRuntimeConfig(default_timeout_seconds=0.1))
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="mock",
            input={"action": "test", "delay": 1.0},  # Will exceed timeout
            timeout_seconds=0.1,
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.TIMEOUT
        assert "timed out" in response.error.lower()

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test exponential backoff computation."""

        tool = MockTool(
            config=ToolRuntimeConfig(
                base_retry_delay_seconds=0.1,
                max_retry_delay_seconds=1.0,
                backoff_multiplier=2.0,
            )
        )

        # Test backoff progression
        delay_1 = tool._compute_backoff(1)
        delay_2 = tool._compute_backoff(2)
        delay_3 = tool._compute_backoff(3)

        assert 0.05 < delay_1 < 0.1  # base * jitter (0.5-1.0)
        assert 0.1 < delay_2 < 0.2   # base * 2 * jitter
        assert 0.2 < delay_3 < 0.4   # base * 4 * jitter

    @pytest.mark.asyncio
    async def test_response_size_validation(self):
        """Test response size limit enforcement."""

        tool = MockTool(config=ToolRuntimeConfig(max_response_size_bytes=100))

        # Create large output
        large_output = {"data": "x" * 1000}

        with pytest.raises(ValueError, match="exceeds limit"):
            tool._validate_response_size(large_output)

    def test_retryable_error_classification(self):
        """Test error classification for retry decisions."""

        tool = MockTool()

        # Retryable errors
        assert tool.is_retryable(asyncio.TimeoutError("timeout"))
        assert tool.is_retryable(ConnectionError("network"))
        assert tool.is_retryable(RuntimeError("unknown"))

        # Non-retryable errors
        assert not tool.is_retryable(ValueError("validation"))
        assert not tool.is_retryable(FileNotFoundError("not found"))
        assert not tool.is_retryable(PermissionError("permission"))


# ============================================================================
# Tool Registry Tests
# ============================================================================


class TestToolRegistry:
    """Test tool registry and discovery."""

    def test_tool_registration(self):
        """Test basic tool registration."""

        registry = ToolRegistry()
        tool = MockTool()

        registry.register(tool)

        resolved = registry.resolve("mock")
        assert resolved.name == "mock"

    def test_case_insensitive_resolution(self):
        """Test case-insensitive tool name resolution."""

        registry = ToolRegistry()
        tool = MockTool()

        registry.register(tool)

        assert registry.resolve("mock") is tool
        assert registry.resolve("MOCK") is tool
        assert registry.resolve("Mock") is tool

    def test_tool_aliases(self):
        """Test registering tool with multiple aliases."""

        registry = ToolRegistry()
        tool = MockTool()

        registry.register(tool, "m", "test")

        assert registry.resolve("mock") is tool
        assert registry.resolve("m") is tool
        assert registry.resolve("test") is tool

    def test_tool_not_found(self):
        """Test error when tool not registered."""

        registry = ToolRegistry()

        with pytest.raises(ToolNotFoundError):
            registry.resolve("nonexistent")

    def test_list_tool_names(self):
        """Test listing all registered tool names."""

        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(JSONTool())
        registry.register(YAMLTool())

        names = registry.names()
        assert "mock" in names
        assert "json" in names
        assert "yaml" in names

    def test_tool_discovery_schema(self):
        """Test schema generation for tool discovery."""

        registry = ToolRegistry()
        registry.register(MockTool())

        schemas = registry.all_schemas()
        assert len(schemas) >= 1

        mock_schema = next((s for s in schemas if s.name == "mock"), None)
        assert mock_schema is not None
        assert mock_schema.description == "Mock tool for testing"
        assert mock_schema.input_schema is not None
        assert mock_schema.input_example is not None

    def test_schema_for_specific_tool(self):
        """Test schema generation for specific tool."""

        registry = ToolRegistry()
        tool = MockTool()
        registry.register(tool)

        schema = registry.schema_for("mock")

        assert isinstance(schema, ToolSchema)
        assert schema.name == "mock"
        assert "action" in schema.input_schema["properties"]


# ============================================================================
# Tool-Specific Tests
# ============================================================================


class TestStructuredDataTools:
    """Test JSON, YAML, and XML tools."""

    @pytest.mark.asyncio
    async def test_json_parse(self):
        """Test JSON parsing."""

        tool = JSONTool()
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="json",
            input={
                "operation": "parse",
                "content": '{"key": "value", "number": 42}',
            },
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.SUCCESS
        assert response.output["data"]["key"] == "value"
        assert response.output["data"]["number"] == 42

    @pytest.mark.asyncio
    async def test_json_format(self):
        """Test JSON formatting."""

        tool = JSONTool()
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="json",
            input={
                "operation": "format",
                "data": {"key": "value", "nested": {"a": 1}},
            },
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.SUCCESS
        assert '"key": "value"' in response.output["content"]

    @pytest.mark.asyncio
    async def test_yaml_parse(self):
        """Test YAML parsing."""

        tool = YAMLTool()
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="yaml",
            input={
                "operation": "parse",
                "content": "key: value\nnumber: 42\n",
            },
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.SUCCESS
        assert response.output["data"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_xml_parse(self):
        """Test XML parsing."""

        tool = XMLTool()
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="xml",
            input={
                "operation": "parse",
                "content": '<root attr="value"><child>text</child></root>',
            },
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.SUCCESS
        assert response.output["data"]["tag"] == "root"


# ============================================================================
# Shell Tool Tests
# ============================================================================


class TestShellTools:
    """Test shell and command execution tools."""

    @pytest.mark.asyncio
    async def test_command_execution(self):
        """Test command execution."""

        tool = CommandTool()
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="command",
            input={
                "command_name": "echo",
                "args": ["hello", "world"],
                "timeout": 10,
            },
        )

        response = await tool.execute(request)

        if response.status == ToolStatus.SUCCESS:
            assert "hello" in response.output.get("stdout", "").lower() or "hello" in response.output.get(
                "stderr", ""
            ).lower()

    @pytest.mark.asyncio
    async def test_command_timeout(self):
        """Test command timeout handling."""

        import platform
        cmd_name = "ping" if platform.system() == "Windows" else "sleep"
        args = ["-n", "10", "127.0.0.1"] if platform.system() == "Windows" else ["10"]

        tool = CommandTool()
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="command",
            input={
                "command_name": cmd_name,
                "args": args,
                "timeout": 1,  # Will timeout
            },
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_invalid_working_directory(self):
        """Test handling of invalid working directory."""

        tool = CommandTool()
        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="command",
            input={
                "command_name": "echo",
                "args": ["test"],
                "cwd": "/nonexistent/path",
            },
        )

        response = await tool.execute(request)

        assert response.status == ToolStatus.FAILED


# ============================================================================
# Error Classification Tests
# ============================================================================


class TestErrorClassification:
    """Test error type classification."""

    def test_timeout_error_classification(self):
        """Test timeout error classification."""

        assert classify_error(asyncio.TimeoutError("timeout")) == ToolErrorType.TIMEOUT

    def test_network_error_classification(self):
        """Test network error classification."""

        assert classify_error(ConnectionError("network")) == ToolErrorType.NETWORK
        assert classify_error(ConnectionRefusedError("refused")) == ToolErrorType.NETWORK

    def test_validation_error_classification(self):
        """Test validation error classification."""

        from pydantic import ValidationError

        assert classify_error(ValueError("validation")) == ToolErrorType.VALIDATION

    def test_permission_error_classification(self):
        """Test permission error classification."""

        assert classify_error(PermissionError("denied")) == ToolErrorType.PERMISSION

    def test_not_found_error_classification(self):
        """Test not found error classification."""

        assert classify_error(FileNotFoundError("not found")) == ToolErrorType.NOT_FOUND


# ============================================================================
# Integration Tests
# ============================================================================


class TestToolLayerIntegration:
    """Test tool layer integration scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_tools_in_registry(self):
        """Test working with multiple tools in registry."""

        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(JSONTool())
        registry.register(YAMLTool())

        # Execute different tools
        mock_tool = registry.resolve("mock")
        json_tool = registry.resolve("json")
        yaml_tool = registry.resolve("yaml")

        mock_request = ToolRequest(
            workflow_id="wf-1", tool_name="mock", input={"action": "test"}
        )
        mock_response = await mock_tool.execute(mock_request)

        json_request = ToolRequest(
            workflow_id="wf-1",
            tool_name="json",
            input={"operation": "parse", "content": "{}"},
        )
        json_response = await json_tool.execute(json_request)

        assert mock_response.status == ToolStatus.SUCCESS
        assert json_response.status == ToolStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_correlation_id_propagation(self):
        """Test correlation ID propagation through tool execution."""

        registry = ToolRegistry()
        registry.register(MockTool())

        tool = registry.resolve("mock")
        correlation_id = "corr-123"

        request = ToolRequest(
            workflow_id="wf-1",
            tool_name="mock",
            input={"action": "test"},
            correlation_id=correlation_id,
        )

        response = await tool.execute(request)

        assert response.metrics["correlation_id"] == correlation_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
