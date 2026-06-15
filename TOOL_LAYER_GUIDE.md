# Production-Grade Tool Layer Architecture

## Overview

The Tool Layer is the **only component** allowed to interact with external resources in the multi-agent AI system. This ensures:

- **Isolation**: No agent directly touches the filesystem, network, or external APIs
- **Observability**: All external interactions are logged, metered, and traced
- **Resilience**: Automatic retry with exponential backoff and comprehensive error handling
- **Safety**: Input validation, response size limits, and execution timeouts
- **Extensibility**: New tools can be added without modifying agent code

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Agents Layer                          │
│  (Orchestrator, Planner, Recovery, etc.)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
              ToolRequest (JSON)
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    ToolExecutor                              │
│  - Dispatches requests to tool implementations               │
│  - Emits lifecycle events for observability                 │
│  - Handles correlation IDs and logging                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   ToolRegistry                               │
│  - Maps tool names to implementations                        │
│  - Provides discovery API for agent introspection           │
│  - Case-insensitive resolution with aliases                 │
└────────────────────┬────────────────────────────────────────┘
                     │
           ┌─────────┼─────────┬─────────────┬──────────┐
           │         │         │             │          │
           ▼         ▼         ▼             ▼          ▼
        ┌─────────────────────────────────────────────────────┐
        │              BaseTool (Abstract)                     │
        │                                                      │
        │  execute()                                           │
        │  ├─ validate_input()           [Pydantic]           │
        │  ├─ _run()                    [Tool-specific]       │
        │  ├─ retry_with_backoff()      [Exponential]         │
        │  ├─ timeout_protection()      [asyncio.wait_for]    │
        │  ├─ error_classification()    [9 error types]       │
        │  └─ _response()               [Metrics collection]  │
        └─────────────────────────────────────────────────────┘
           │
           └──────┬──────────┬──────────┬──────────┬──────────┐
                  │          │          │          │          │
                  ▼          ▼          ▼          ▼          ▼
              Salesforce   Filesystem  SQLite    HTTP      Shell
              CLI Tool      Tool       Tool      Tool      Tools
              (sf)         (fs)       (db)      (rest)    (bash,
                           (safe)                         cmd,
                           sandbox                        pwsh)
                           with ACL
                           checks

                          + 5 more tools
                           (Git, JSON,
                            YAML, XML,
                            Ollama)
```

### Request/Response Models

```python
# Agent submits ToolRequest
ToolRequest {
  id: str                           # Unique request ID (auto-generated)
  workflow_id: str                  # Workflow context
  task_id: str | None              # Task within workflow
  tool_name: str                    # Name of tool to invoke
  input: dict[str, Any]            # Tool-specific input
  timeout_seconds: float | None    # Override default timeout
  correlation_id: str              # Tracing ID
  created_at: datetime             # Request timestamp
}

# Tool returns ToolResponse
ToolResponse {
  id: str                           # Auto-generated response ID
  request_id: str                   # Links to original request
  workflow_id: str
  tool_name: str
  status: ToolStatus                # SUCCESS | FAILED | TIMEOUT
  output: dict[str, Any]           # Tool output (on success)
  error: str | None                # Error message (on failure)
  error_type: ToolErrorType | None # TIMEOUT | NETWORK | VALIDATION | ...
  metrics: dict                     # duration_seconds, started_at, etc.
  attempts: int                     # Number of retries used
  started_at: datetime
  completed_at: datetime
}
```

## Supported Tools

### 1. **Salesforce CLI Tool** (`sf`, `sfdx`, `salesforce`)

Execute Salesforce CLI commands for org management, metadata operations, and deployments.

```python
# Operation types
"org_list"           # List available orgs
"org_info"           # Display org details
"org_open"           # Open org in browser
"org_create"         # Create scratch/demo org
"project_deploy"     # Deploy metadata
"project_retrieve"   # Retrieve metadata
"apex_execute"       # Run Apex code
"data_query"         # Execute SOQL
"data_upsert"        # Upsert records
"custom_command"     # Execute arbitrary sf command

# Example
request = ToolRequest(
    tool_name="sf",
    input={
        "operation": "org_list",
        "json_output": True,
    }
)
```

**Supported Flags**: `-target-org`, `-manifest`, `-wait`, `-test-level`, `-test`, `-ignore-warnings`, etc.

### 2. **Filesystem Tool** (`fs`, `file`)

Safe file system access with sandbox and ACL checks.

```python
# Operations
"read"               # Read file contents
"write"              # Write/create file
"delete"             # Delete file
"list"               # List directory
"exists"             # Check existence
"mkdir"              # Create directory
"get_info"           # File metadata

# Example
request = ToolRequest(
    tool_name="fs",
    input={
        "operation": "read",
        "path": "src/config.json",
    }
)
```

**Features**:
- Sandbox confined to workspace root
- Path escape detection
- Maximum file size limits
- Safe text encoding

### 3. **Shell Tools** (`shell`, `bash`, `powershell`, `cmd`)

Execute shell commands with cross-platform support.

```python
# ShellTool - arbitrary shell commands
request = ToolRequest(
    tool_name="shell",
    input={
        "command": "docker ps --format json",
        "shell": "bash",      # or "auto" for OS-specific
        "timeout": 30,
    }
)

# CommandTool - structured command execution (safer)
request = ToolRequest(
    tool_name="command",
    input={
        "command_name": "docker",
        "args": ["ps", "--format", "json"],
        "timeout": 30,
    }
)
```

**Features**:
- Cross-platform shell support (bash, powershell, cmd)
- Input/output capture
- Environment variable passing
- Timeout protection
- Command injection prevention (CommandTool)

### 4. **Git Tool** (`git`, `vcs`)

Version control operations via git commands.

```python
request = ToolRequest(
    tool_name="git",
    input={
        "args": ["clone", "https://github.com/repo.git"],
        "cwd": "/workspace",
    }
)
```

### 5. **HTTP/REST Tool** (`http`, `rest`, `api`)

Make HTTP requests to APIs.

```python
request = ToolRequest(
    tool_name="http",
    input={
        "method": "POST",
        "url": "https://api.example.com/endpoint",
        "headers": {"Authorization": "Bearer token"},
        "body": {"data": "value"},
        "timeout": 30,
    }
)
```

### 6. **SQLite Tool** (`sqlite`, `db`)

Execute database queries.

```python
request = ToolRequest(
    tool_name="sqlite",
    input={
        "operation": "query",
        "database": "data.db",
        "sql": "SELECT * FROM users WHERE id = ?",
        "params": [123],
    }
)
```

### 7. **Ollama Tool** (`ollama`, `llm`, `ai`)

Interact with local Ollama LLM instances.

```python
request = ToolRequest(
    tool_name="llm",
    input={
        "model": "mistral",
        "prompt": "Explain recursion",
        "temperature": 0.7,
    }
)
```

### 8-10. **Data Format Tools** (`json`, `yaml`, `xml`)

Parse and format structured data.

```python
# JSON
request = ToolRequest(
    tool_name="json",
    input={
        "operation": "parse",
        "content": '{"key": "value"}',
    }
)

# YAML
request = ToolRequest(
    tool_name="yaml",
    input={
        "operation": "format",
        "data": {"key": "value"},
    }
)
```

## Error Handling & Retry Strategy

### Error Classification (9 Types)

| Error Type | Retryable | Example | Action |
|-----------|-----------|---------|--------|
| `TIMEOUT` | ✅ Yes | Request exceeded timeout | Retry with backoff |
| `NETWORK` | ✅ Yes | Connection refused | Retry with backoff |
| `EXTERNAL_PROCESS` | ✅ Yes | External service down | Retry with backoff |
| `DATABASE` | ✅ Yes | Lock timeout | Retry with backoff |
| `UNKNOWN` | ✅ Yes | Unclassified error | Retry as fallback |
| `VALIDATION` | ❌ No | Invalid input | Fail immediately |
| `NOT_FOUND` | ❌ No | File not found | Fail immediately |
| `PERMISSION` | ❌ No | Access denied | Fail immediately |
| `SERIALIZATION` | ❌ No | JSON parse error | Fail immediately |

### Exponential Backoff with Jitter

```
Delay = min(base * (multiplier ^ attempt) * (0.5-1.0 jitter), max)

Default:
- base_delay: 0.25s
- multiplier: 2.0x
- max_delay: 10.0s

Progression:
- Attempt 1: 0.125-0.25s
- Attempt 2: 0.25-0.5s
- Attempt 3: 0.5-1.0s
- Attempt 4+: capped at 10s
```

## Configuration

### ToolRuntimeConfig

```python
@dataclass(frozen=True)
class ToolRuntimeConfig:
    default_timeout_seconds: float = 30.0      # Per-attempt timeout
    default_retries: int = 0                   # Number of retries
    base_retry_delay_seconds: float = 0.25     # Initial backoff
    max_retry_delay_seconds: float = 10.0      # Maximum backoff
    backoff_multiplier: float = 2.0            # Exponential multiplier
    max_response_size_bytes: int = 10 * 1024 * 1024  # 10MB limit
```

## Tool Discovery API

Agents can dynamically discover available tools and their interfaces:

```python
registry = build_tool_registry(settings, workspace_root)

# List all tools
tool_names = registry.names()  # ["sf", "git", "fs", ...]

# Get schema for all tools
schemas = registry.all_schemas()  # List[ToolSchema]
for schema in schemas:
    print(f"{schema.name}: {schema.description}")
    print(f"Input schema: {schema.input_schema}")
    print(f"Example: {schema.input_example}")

# Get schema for specific tool
schema = registry.schema_for("git")
```

## Usage Patterns

### 1. Agent Integration

```python
class MyAgent:
    def __init__(self, executor: ToolExecutor):
        self.executor = executor
    
    async def execute_task(self):
        request = ToolRequest(
            workflow_id=self.workflow_id,
            tool_name="git",
            input={"args": ["clone", url]},
            correlation_id=self.correlation_id,
        )
        response = await self.executor.execute(request)
        
        if response.status == ToolStatus.SUCCESS:
            return response.output
        else:
            raise ToolError(f"{response.error_type}: {response.error}")
```

### 2. Tool-Specific Invocation

```python
# Direct tool usage (advanced, usually not recommended)
tool = registry.resolve("fs")
response = await tool.execute(request)
```

### 3. Discovery and Validation

```python
# Check if tool exists before using
try:
    schema = registry.schema_for(tool_name)
    # Validate input against schema
except ToolNotFoundError:
    # Handle missing tool
```

## Testing

```python
@pytest.mark.asyncio
async def test_tool_execution():
    request = ToolRequest(
        workflow_id="test-wf",
        tool_name="json",
        input={
            "operation": "parse",
            "content": '{"test": true}'
        }
    )
    
    response = await tool.execute(request)
    assert response.status == ToolStatus.SUCCESS
```

## Security Considerations

### Input Validation

- All inputs validated via Pydantic models before execution
- Strongly-typed schema prevents injection attacks
- Max size limits on strings and requests

### Output Limits

- Maximum response size: 10MB (configurable)
- Prevents OOM from large tool outputs
- Validation occurs before response

### Filesystem Sandbox

- Filesystem tool confined to workspace root
- Path escape attempts detected and blocked
- ACL checks prevent unauthorized access

### Shell Command Safety

- CommandTool prevents shell injection via argv splitting
- ShellTool only for trusted commands
- Environment variable filtering available

## Performance Characteristics

| Operation | Typical | P99 |
|-----------|---------|-----|
| Tool invocation overhead | 1-5ms | 10ms |
| Input validation | 0.5-1ms | 2ms |
| Simple tool (json parse) | 1-2ms | 5ms |
| Network tool (HTTP) | 50-500ms | 5000ms |
| Timeout check | <1ms | <1ms |

## Metrics Collection

Every tool execution produces detailed metrics:

```python
response.metrics = {
    "duration_seconds": 0.123456,
    "started_at": "2024-06-12T10:30:45.123456Z",
    "completed_at": "2024-06-12T10:30:45.246912Z",
    "tool_name": "git",
    "correlation_id": "corr-123",
    "error_type": None,  # Only on errors
}
```

## Adding Custom Tools

```python
from salesforce_ai_engineer.tools.base import BaseTool, ToolRuntimeConfig
from pydantic import BaseModel

class MyToolInput(BaseModel):
    action: str
    param: str

class MyTool(BaseTool):
    name = "my_tool"
    description = "Description of my tool"
    input_model = MyToolInput
    
    async def _run(self, payload: MyToolInput, request: ToolRequest):
        # Implement tool logic
        return {"result": "value"}

# Register in factory
registry.register(MyTool(), "my", "custom")
```

## Troubleshooting

### Tool Not Found

```
ToolNotFoundError: No tool registered for 'typo'
```

Solution: Check `registry.names()` for correct spelling and aliases.

### Validation Error

```
Tool request validation must be a non-negative integer
```

Solution: Ensure input matches Pydantic model. Check `registry.schema_for(tool_name)`.

### Timeout

```
Tool 'git' timed out after 30 seconds
```

Solution: Increase `timeout_seconds` in ToolRequest or adjust default in ToolRuntimeConfig.

### Response Too Large

```
Tool output 15000000 bytes exceeds limit (10485760 bytes)
```

Solution: Increase `max_response_size_bytes` or use pagination/streaming.

## See Also

- [Tool Layer Design](./TOOLS_ARCHITECTURE_ANALYSIS.md)
- [Test Suite](./tests/tools/test_tool_layer.py)
- [Error Handling Reference](./src/salesforce_ai_engineer/tools/errors.py)
