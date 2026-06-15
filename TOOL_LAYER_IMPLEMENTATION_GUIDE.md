# Tool Layer Implementation Guide

## Quick Start

### 1. Install Dependencies

All required dependencies are already in `requirements.txt`. The tool layer uses:
- `pydantic` - Input/output validation
- `aiohttp` - Async HTTP
- `asyncpg` - Async database  (optional, for future extension)
- `PyYAML` - YAML processing
- Standard library: `asyncio`, `subprocess`, `json`, `xml`

### 2. Initialize Container

The tool layer is automatically initialized in the bootstrap container:

```python
from salesforce_ai_engineer.core.bootstrap import container

# Get the tool executor (main entry point)
executor = container.resolve("tool_executor")

# Get the registry (for discovery)
registry = container.resolve("tool_registry")
```

### 3. Execute Your First Tool

```python
import asyncio
from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus

async def main():
    executor = container.resolve("tool_executor")
    
    # Request
    request = ToolRequest(
        workflow_id="demo-001",
        tool_name="json",
        input={
            "operation": "parse",
            "content": '{"hello": "world"}'
        }
    )
    
    # Execute
    response = await executor.execute(request)
    
    # Check result
    if response.status == ToolStatus.SUCCESS:
        print(f"Result: {response.output}")
    else:
        print(f"Error: {response.error}")

asyncio.run(main())
```

---

## Architecture Overview

### Layer 1: Agents

Your agents (Orchestrator, Planner, Recovery) do NOT directly call:
- `subprocess.run()`
- `open()` or `Path.write_text()`
- `requests.get()` or `httpx.post()`
- Any external API

Instead, they create `ToolRequest` objects.

### Layer 2: Tool Executor

The `ToolExecutor` is the ONLY interface agents use:

```
Agent → ToolRequest → ToolExecutor → ToolRegistry → BaseTool._run()
                                           ↓
                                    Tool Implementation
                                    (Git, Http, Filesystem, etc.)
```

### Layer 3: Tools

Each tool implements `BaseTool`:
- Input validation (Pydantic)
- Execution with timeout
- Automatic retry with exponential backoff
- Error classification
- Metrics collection

---

## Tool Implementation Pattern

### Step 1: Create Input Model

```python
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    """Input for my custom tool."""
    
    action: str = Field(..., description="Action to perform")
    param: str = Field(default="default", description="Optional parameter")
    timeout: int = Field(default=30, ge=1, le=3600)
```

### Step 2: Implement Tool Class

```python
from salesforce_ai_engineer.tools.base import BaseTool
from salesforce_ai_engineer.models.domain import ToolRequest
from typing import Any

class MyTool(BaseTool):
    """My custom tool implementation."""
    
    name = "my_tool"
    description = "Does something useful"
    input_model = MyToolInput
    
    async def _run(self, payload: MyToolInput, request: ToolRequest) -> dict[str, Any]:
        """
        Implement tool logic here.
        
        Args:
            payload: Validated input (already parsed by input_model)
            request: Original ToolRequest with metadata
            
        Returns:
            dict with tool output (JSON-serializable)
            
        Raises:
            Any exception - will be caught, classified, and possibly retried
        """
        
        # Your implementation
        result = do_something(payload.action, payload.param)
        
        return {
            "success": True,
            "action": payload.action,
            "result": result
        }
```

### Step 3: Register Tool

```python
# In factory.py or bootstrap.py
registry.register(MyTool(), "my", "custom")  # Multiple aliases
```

### Step 4: Use in Agent

```python
async def my_agent_task():
    executor = container.resolve("tool_executor")
    
    request = ToolRequest(
        workflow_id="wf-001",
        tool_name="my_tool",
        input={
            "action": "process",
            "param": "value"
        }
    )
    
    response = await executor.execute(request)
    # Response is guaranteed to have status, output/error, metrics
```

---

## Error Handling Patterns

### Pattern 1: Check Status

```python
if response.status == ToolStatus.SUCCESS:
    data = response.output
elif response.status == ToolStatus.TIMEOUT:
    # Retry manually or escalate
elif response.status == ToolStatus.FAILED:
    if response.error_type == ToolErrorType.VALIDATION:
        # Fix input
    elif response.error_type == ToolErrorType.NOT_FOUND:
        # Handle missing resource
    else:
        # Log and escalate
```

### Pattern 2: Automatic Retry

```python
# Tool layer handles retries automatically
request = ToolRequest(
    tool_name="http",
    input={
        "url": "...",
        "retries": 3  # Retry transient errors up to 3 times
    },
    timeout_seconds=10
)

response = await executor.execute(request)
# Will retry automatically on TIMEOUT, NETWORK, EXTERNAL_PROCESS, DATABASE
```

### Pattern 3: Error Classification

```python
from salesforce_ai_engineer.models.domain import ToolErrorType

retryable_errors = {
    ToolErrorType.TIMEOUT,
    ToolErrorType.NETWORK,
    ToolErrorType.EXTERNAL_PROCESS,
    ToolErrorType.DATABASE,
    ToolErrorType.UNKNOWN,
}

if response.error_type in retryable_errors:
    # Safe to retry
    return await retry_operation()
else:
    # Don't retry
    raise ToolError(response.error)
```

---

## Testing Tools

### Test with Pytest

```python
import pytest
from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus

@pytest.mark.asyncio
async def test_my_tool():
    """Test custom tool."""
    
    tool = MyTool()
    request = ToolRequest(
        workflow_id="test-001",
        tool_name="my_tool",
        input={
            "action": "test",
            "param": "value"
        }
    )
    
    response = await tool.execute(request)
    
    assert response.status == ToolStatus.SUCCESS
    assert response.output["action"] == "test"
    assert "duration_seconds" in response.metrics
```

### Test Error Handling

```python
@pytest.mark.asyncio
async def test_tool_timeout():
    """Test timeout handling."""
    
    tool = MyTool()
    request = ToolRequest(
        tool_name="my_tool",
        input={"action": "test"},
        timeout_seconds=0.1  # Very short
    )
    
    response = await tool.execute(request)
    
    assert response.status == ToolStatus.TIMEOUT
    assert response.error_type == ToolErrorType.TIMEOUT
```

### Test Input Validation

```python
@pytest.mark.asyncio
async def test_invalid_input():
    """Test input validation."""
    
    tool = MyTool()
    request = ToolRequest(
        tool_name="my_tool",
        input={"missing_required_field": "value"}
    )
    
    response = await tool.execute(request)
    
    assert response.status == ToolStatus.FAILED
    assert response.error_type == ToolErrorType.VALIDATION
```

---

## Configuration

### Override Default Timeouts

In your agent or request:

```python
# Per-request override
request = ToolRequest(
    tool_name="git",
    input={...},
    timeout_seconds=60  # 1 minute instead of default 30s
)
```

### Configure Tool Runtime

```python
from salesforce_ai_engineer.tools.base import ToolRuntimeConfig

config = ToolRuntimeConfig(
    default_timeout_seconds=45,
    default_retries=2,
    base_retry_delay_seconds=0.5,
    max_retry_delay_seconds=20,
    backoff_multiplier=3.0,
    max_response_size_bytes=50 * 1024 * 1024  # 50MB
)

tool = MyTool(config=config)
```

---

## Debugging

### Enable Debug Logging

```python
import logging

logging.getLogger("salesforce_ai_engineer.tools").setLevel(logging.DEBUG)
logging.getLogger("salesforce_ai_engineer.tools.base").setLevel(logging.DEBUG)
```

### Inspect Tool Metadata

```python
registry = container.resolve("tool_registry")

# List all tools
print(registry.names())

# Get schema
schema = registry.schema_for("git")
print(schema.input_schema)
print(schema.input_example)
```

### Troubleshoot Tool Execution

```python
response = await executor.execute(request)

print(f"Status: {response.status}")
print(f"Error Type: {response.error_type}")
print(f"Error Message: {response.error}")
print(f"Attempts: {response.attempts}")
print(f"Duration: {response.metrics['duration_seconds']}s")
```

---

## Performance Tuning

### Optimize Timeout Values

```python
# Too short = more timeouts
request1 = ToolRequest(tool_name="http", input={...}, timeout_seconds=5)

# Too long = slow failures
request2 = ToolRequest(tool_name="http", input={...}, timeout_seconds=300)

# Balanced (depends on tool)
request3 = ToolRequest(tool_name="http", input={...}, timeout_seconds=30)
```

### Balance Retries

```python
# No retries = fail fast
request1 = ToolRequest(tool_name="http", input={"retries": 0, ...})

# Many retries = handle transient errors
request2 = ToolRequest(tool_name="http", input={"retries": 5, ...})

# Exponential backoff handles thundering herd
# No need for manual jitter
```

### Monitor Response Sizes

```python
# Large responses
response1 = ToolRequest(
    tool_name="sqlite",
    input={
        "sql": "SELECT * FROM large_table",  # Millions of rows?
    }
)

# Paginate if needed
response2 = ToolRequest(
    tool_name="sqlite",
    input={
        "sql": "SELECT * FROM large_table LIMIT 1000 OFFSET 0",
    }
)
```

---

## Security Considerations

### Input Validation

All inputs are validated via Pydantic before reaching tool implementation:

```python
class ToolInput(BaseModel):
    path: str = Field(..., min_length=1, max_length=1000)
    mode: Literal["read", "write", "append"]  # Restrict choices
```

### Filesystem Sandbox

FilesystemTool is sandboxed to workspace root:

```python
from salesforce_ai_engineer.tools.filesystem.tool import FilesystemTool

tool = FilesystemTool(workspace_root=Path("/workspace"))

# Safe: within workspace
request1 = ToolRequest(
    tool_name="fs",
    input={"operation": "read", "path": "src/config.json"}
)

# Blocked: path escape attempt
request2 = ToolRequest(
    tool_name="fs",
    input={"operation": "read", "path": "../../etc/passwd"}
)
```

### Shell Command Safety

Use `CommandTool` instead of `ShellTool` when possible:

```python
# Unsafe: Shell metacharacters
unsafe = ToolRequest(
    tool_name="shell",
    input={"command": "echo " + user_input}
)

# Safe: No injection risk
safe = ToolRequest(
    tool_name="command",
    input={
        "command_name": "echo",
        "args": [user_input]  # Passed as argv, not parsed
    }
)
```

### Response Size Limits

Prevent OOM attacks:

```python
config = ToolRuntimeConfig(max_response_size_bytes=10 * 1024 * 1024)
# Tools will fail if output exceeds 10MB
```

---

## Troubleshooting

### Issue: Tool Not Found

```
ToolNotFoundError: No tool registered for 'my_tool'
```

**Solution:**
```python
# Check available tools
registry = container.resolve("tool_registry")
print(registry.names())

# Ensure tool is registered in factory.py
# registry.register(MyTool(), "my_tool")
```

### Issue: Validation Error

```
"Tool request validation must be a non-negative integer"
```

**Solution:**
```python
# Check input matches model
request = ToolRequest(
    tool_name="tool",
    input={
        "retries": 3,  # Must be int, not string
        "action": "test"
    }
)
```

### Issue: Timeout Too Frequent

```
Tool 'git' timed out after 30 seconds
```

**Solution:**
```python
# Increase timeout for slow operations
request = ToolRequest(
    tool_name="git",
    input={"args": ["clone", "large-repo"]},
    timeout_seconds=300  # 5 minutes for big clones
)
```

### Issue: Connection Refused

```
Network error: Connection refused
```

**Solution:**
```python
# Retry with backoff
request = ToolRequest(
    tool_name="http",
    input={
        "method": "GET",
        "url": "http://service:8000/api",
        "retries": 3  # Try up to 3 times
    }
)
```

---

## Best Practices

### 1. Always Check Response Status

```python
response = await executor.execute(request)

if response.status != ToolStatus.SUCCESS:
    logger.error(f"Tool failed: {response.error_type} - {response.error}")
    # Handle error appropriately
```

### 2. Use Correlation IDs

```python
request = ToolRequest(
    workflow_id="wf-001",
    correlation_id="trace-xyz",  # For tracing through logs
    tool_name="git",
    input={...}
)
```

### 3. Provide Meaningful Tool Names

```python
# Good
registry.register(SalesforceCliTool(), "sf", "sfdx", "salesforce")

# Avoid
registry.register(SalesforceCliTool(), "tool1")
```

### 4. Document Tool Inputs

```python
class MyToolInput(BaseModel):
    """Input for my tool."""
    
    query: str = Field(..., description="SQL query to execute", min_length=1)
    limit: int = Field(default=100, ge=1, le=10000, description="Max rows")
    timeout: int = Field(default=30, ge=1, le=300, description="Query timeout")
```

### 5. Log Important Tool Operations

```python
async def _run(self, payload: MyToolInput, request: ToolRequest):
    logger.info(f"Executing tool with action={payload.action}")
    try:
        result = await do_work(payload)
        logger.info(f"Tool succeeded, result_size={len(result)}")
        return result
    except Exception as e:
        logger.error(f"Tool failed: {e}", exc_info=True)
        raise
```

### 6. Use Tool Discovery

```python
# Before using a tool, check if it's available
registry = container.resolve("tool_registry")

if "my_tool" not in registry.names():
    raise RuntimeError("my_tool not registered")

schema = registry.schema_for("my_tool")
# Validate input matches schema
```

---

## Monitoring and Observability

### Metrics Available

Every tool response includes metrics:

```python
response.metrics = {
    "duration_seconds": 0.123,
    "started_at": "2024-06-12T10:30:45.123Z",
    "completed_at": "2024-06-12T10:30:45.246Z",
    "tool_name": "git",
    "correlation_id": "trace-xyz",
    "error_type": None,  # On errors
}
```

### Export Metrics

```python
# Prometheus-style metrics
def export_metrics(response: ToolResponse):
    duration = response.metrics["duration_seconds"]
    tool = response.metrics["tool_name"]
    status = response.status
    
    metric_name = f"tool_execution_duration_seconds{{tool='{tool}',status='{status}'}}"
    print(f"{metric_name} {duration}")
```

### Track Retries

```python
if response.attempts > 1:
    logger.warning(f"Tool required {response.attempts} attempts (retried {response.attempts - 1} times)")
```

---

## Next Steps

1. **Review** [TOOL_LAYER_GUIDE.md](./TOOL_LAYER_GUIDE.md) for comprehensive reference
2. **Study** [TOOL_LAYER_EXAMPLES.py](./TOOL_LAYER_EXAMPLES.py) for 10 practical examples
3. **Reference** [TOOL_LAYER_API_REFERENCE.md](./TOOL_LAYER_API_REFERENCE.md) for detailed API docs
4. **Run** tests in `tests/tools/test_tool_layer.py`
5. **Integrate** tools into your agents

---

## Support and Issues

### Getting Help

- Check the comprehensive guides in this directory
- Review test cases in `tests/tools/`
- Enable debug logging: `logging.getLogger("salesforce_ai_engineer.tools").setLevel(logging.DEBUG)`

### Reporting Issues

When reporting tool layer issues, include:
- ToolRequest input
- ToolResponse status, error_type, and error
- Tool metrics (duration, attempts)
- Debug logs
