# Tools Layer Quick Reference

## Tool Registry & Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent/Orchestrator                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────────────────┐
│                    ToolExecutor                              │
│  - Emits TOOL_REQUESTED event                               │
│  - Resolves tool from registry                              │
│  - Delegates to BaseTool.execute()                          │
│  - Emits TOOL_RESPONDED event                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────────────────┐
│                    ToolRegistry                              │
│  Maps: tool_name → BaseTool instance                        │
│  - register(tool, *aliases)                                 │
│  - resolve(name) → BaseTool                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────────────────┐
│                    BaseTool.execute()                        │
│  1. Validate input (Pydantic model)                         │
│  2. Retry loop (with exponential backoff attempt):          │
│     - Call _run() with asyncio.wait_for(timeout)           │
│     - Catch asyncio.TimeoutError → retry or TIMEOUT status │
│     - Catch other errors → classify & retry if retryable   │
│  3. Build ToolResponse with metrics                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────────────────┐
│              Tool-Specific _run() Implementation             │
│  - HttpTool: async HTTP client call                         │
│  - SQLiteTool: async SQL execution                          │
│  - FilesystemTool: file I/O with path validation            │
│  - ShellCommandTool: async subprocess execution             │
│  - OllamaTool: LLM chat API call                            │
│  - StructuredDataTools: JSON/YAML/XML parsing               │
└─────────────────────────────────────────────────────────────┘
```

---

## Tool List & Configuration

| Tool Name | Aliases | Input Model | Notes |
|-----------|---------|-------------|-------|
| **http** | rest | `HttpInput` | GET/POST/PUT/PATCH/DELETE/HEAD via httpx |
| **sqlite** | — | `SQLiteInput` | Async SQL queries/execute via aiosqlite |
| **filesystem** | fs | `FilesystemInput` | read/write/list/mkdir with path sandboxing |
| **json** | — | `StructuredDataInput` | Parse/format JSON |
| **yaml** | yml | `StructuredDataInput` | Parse/format YAML |
| **xml** | — | `StructuredDataInput` | Parse/format XML (dict ↔ tree) |
| **shell** | — | `ShellCommandInput` | Execute command argv (no shell expansion) |
| **git** | — | `CommandInput` | Execute git commands |
| **salesforce_cli** | sf, sfdx | `CommandInput` | Execute Salesforce CLI |
| **ollama** | llm | `OllamaInput` | Local LLM chat completions |

---

## ToolRequest & ToolResponse Anatomy

### ToolRequest (Immutable)
```python
{
    "id": "uuid",                           # Auto-generated
    "workflow_id": "uuid",                  # From workflow
    "task_id": "uuid",                      # Optional, from task
    "tool_name": "http",                    # Required
    "input": {                              # Tool-specific dict
        "method": "GET",
        "url": "https://..."
    },
    "timeout_seconds": 30.0,                # Optional override
    "correlation_id": "uuid",               # Auto-generated
    "created_at": "2026-06-12T12:00:00Z"   # Auto-generated
}
```

### ToolResponse (Immutable)
```python
{
    "id": "uuid",                               # Auto-generated
    "request_id": "uuid",                       # From request
    "workflow_id": "uuid",                      # From request
    "tool_name": "http",                        # From request
    "status": "success" | "failed" | "timeout", # Execution status
    "output": {                                 # Tool-specific dict
        "status_code": 200,
        "headers": {...},
        "text": "...",
        "json": {...}
    },
    "error": "Error message (if failed)",       # Optional
    "error_type": "network" | "validation" | ..., # Optional
    "metrics": {
        "duration_seconds": 0.234,
        "started_at": "2026-06-12T12:00:00Z",
        "completed_at": "2026-06-12T12:00:00.234Z"
    },
    "attempts": 1,                              # Retry attempt count
    "started_at": "2026-06-12T12:00:00Z",
    "completed_at": "2026-06-12T12:00:00.234Z"
}
```

---

## Error Classification

```
ToolError Taxonomy:

├─ VALIDATION (400-like)
│  └─ Raised by: ToolValidationError
│  └─ Retryable: NO
│  └─ Cause: Invalid input

├─ TIMEOUT (408-like)
│  └─ Raised by: ToolTimeoutError
│  └─ Retryable: YES
│  └─ Cause: Exceeded deadline

├─ NOT_FOUND (404-like)
│  └─ Raised by: ToolNotFoundError
│  └─ Retryable: NO
│  └─ Cause: Tool/resource missing

├─ PERMISSION (403-like)
│  └─ Raised by: ToolPermissionError
│  └─ Retryable: NO
│  └─ Cause: Access denied

├─ EXTERNAL_PROCESS (5xx-like from subprocess)
│  └─ Raised by: ExternalProcessError
│  └─ Retryable: YES
│  └─ Cause: Command failed

├─ NETWORK (5xx-like from HTTP)
│  └─ Raised by: ToolNetworkError
│  └─ Retryable: YES
│  └─ Cause: HTTP/API failure

├─ SERIALIZATION (400-like data format)
│  └─ Raised by: ToolSerializationError
│  └─ Retryable: NO
│  └─ Cause: JSON/YAML/XML parse error

├─ DATABASE (5xx-like from DB)
│  └─ Raised by: ToolDatabaseError
│  └─ Retryable: YES
│  └─ Cause: SQLite failure

└─ UNKNOWN (catch-all)
   └─ Raised by: Unmapped exceptions
   └─ Retryable: YES
   └─ Cause: Not classified
```

---

## Timeout & Retry Configuration

### At Tool Level (ToolRuntimeConfig)
```python
default_timeout_seconds: float = 30.0   # Used if request doesn't specify
default_retries: int = 0                # Initial attempt count
retry_delay_seconds: float = 0.25       # Sleep between retries (LINEAR, not exponential)
```

### At Request Level (ToolRequest)
```python
timeout_seconds: float | None = None    # Overrides default_timeout_seconds
input.retries: int = 0                  # Parsed from request input
```

### Retry Calculation
```
attempts = input.get("retries", config.default_retries) + 1
# Example: retries=2 → 3 total attempts
```

### Timeout Application
```
for attempt in range(1, attempts + 1):
    try:
        output = await asyncio.wait_for(
            self._run(...),
            timeout=timeout_seconds
        )
```

---

## Validation & Input Models

All tools validate input using Pydantic. Validation errors raise `ToolValidationError` (not retryable).

### Example: HTTP Tool
```python
class HttpInput(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
    url: HttpUrl                    # Validates URL format
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    json_body: Any | None = None
    text_body: str | None = None
```

### Example: SQLite Tool
```python
class SQLiteInput(BaseModel):
    database_path: str
    statement: str
    parameters: list[Any] | dict[str, Any] = Field(default_factory=list)
    operation: Literal["query", "execute"] = "query"
    
    # Additional validation in _run():
    if not statement.strip():
        raise ToolValidationError("SQLite statement must not be empty")
```

### Example: Filesystem Tool
```python
class FilesystemInput(BaseModel):
    operation: Literal["read_text", "write_text", "exists", "list", "mkdir"]
    path: str
    content: str | None = None
    pattern: str = "*"
    
    # Security validation in _resolve():
    resolved = (self.root / path).resolve()
    if self.root not in (resolved, *resolved.parents):
        raise ToolPermissionError(f"Path escapes filesystem tool root: {path}")
```

---

## Metrics Captured

Every ToolResponse includes:
```python
metrics: dict[str, Any] = {
    "duration_seconds": 0.234,      # Execution time (perf_counter accuracy)
    "started_at": "2026-06-12T...", # ISO timestamp
    "completed_at": "2026-06-12...", # ISO timestamp
}
```

### Tool-Specific Outputs (also tracked)
- **HttpTool**: status_code, headers, response size (implicitly)
- **SQLiteTool**: row_count, lastrowid
- **FilesystemTool**: bytes_written, files count
- **OllamaTool**: response object (tokens, generation time)
- **ProcessTools**: return_code, stdout/stderr size (implicitly)

---

## Missing/TODO

### Integration
- [ ] Register tool_registry and tool_executor in bootstrap.py container
- [ ] Add orchestrator dependency on tool_executor

### Testing
- [ ] Unit tests for BaseTool (retry, timeout, error classification)
- [ ] Unit tests for each tool implementation
- [ ] Integration tests with mock services

### Tooling
- [ ] Tool discovery API endpoint (`GET /tools`)
- [ ] Tool introspection (list available, describe signature)
- [ ] OpenAPI schema generation for tools

### Optimization
- [ ] Upgrade retry delay to exponential backoff (use core/retry.py)
- [ ] Add tool-specific metrics collection
- [ ] Implement structured logging with correlation IDs
- [ ] Add response size limits and validation
- [ ] Implement circuit breaker pattern for failing tools

### Completeness
- [ ] Implement salesforce/ tools
- [ ] Implement shell/ tools
- [ ] Add LangChain tool adapter
- [ ] Add OpenAI function calling adapter

---

## Code Walkthrough: HTTP Tool Request → Response

```python
# 1. Agent creates ToolRequest
request = ToolRequest(
    workflow_id="wf-123",
    tool_name="http",
    input={
        "method": "GET",
        "url": "https://api.example.com/data",
        "headers": {"Authorization": "Bearer token"},
    },
    timeout_seconds=10.0,
)

# 2. ToolExecutor.execute() is called
executor = ToolExecutor(registry, event_bus, logger)
response = await executor.execute(request)

# Flow:
# 2a. Emit TOOL_REQUESTED lifecycle event
# 2b. Call registry.resolve("http") → HttpTool instance
# 2c. Call tool.execute(request):
#     - Validate input using HttpInput Pydantic model
#     - For attempt in range(1, 1+1):  # retries=0 by default
#       - Call asyncio.wait_for(tool._run(...), timeout=10.0)
#       - HttpTool._run():
#         - Create httpx.AsyncClient(timeout=10.0)
#         - Execute client.request("GET", "...", ...)
#         - Call response.raise_for_status()
#         - Return {status_code, headers, text, json}
#       - Return ToolResponse(status=SUCCESS, output=...)
# 2d. Emit TOOL_RESPONDED lifecycle event

# 3. Result
{
    "status": "success",
    "output": {
        "status_code": 200,
        "headers": {...},
        "text": "...",
        "json": {...}
    },
    "metrics": {
        "duration_seconds": 0.512,
        "started_at": "2026-06-12T12:00:00Z",
        "completed_at": "2026-06-12T12:00:00.512Z"
    },
    "attempts": 1
}
```

---

## Container Integration (NEEDED)

Currently missing from `bootstrap.py`:

```python
def build_container(config_manager: ConfigurationManager | None = None) -> Container:
    # ... existing code ...
    
    # ADD THIS:
    container.register_factory(
        "tool_registry",
        lambda services: build_tool_registry(
            services.resolve("settings"),
            Path.cwd()
        ),
        singleton=True,
    )
    
    container.register_factory(
        "tool_executor",
        lambda services: ToolExecutor(
            registry=services.resolve("tool_registry"),
            event_bus=services.resolve("event_bus"),
            logger=services.resolve("logger"),
        ),
        singleton=True,
    )
    
    return container
```

Then agents can resolve: `container.resolve("tool_executor", ToolExecutor)`

---

## Testing Template

```python
import pytest
from unittest.mock import AsyncMock, patch
from salesforce_ai_engineer.tools.http import HttpTool
from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus

@pytest.mark.asyncio
async def test_http_tool_success():
    tool = HttpTool()
    request = ToolRequest(
        workflow_id="test-wf",
        tool_name="http",
        input={
            "method": "GET",
            "url": "https://api.example.com/data",
        },
        timeout_seconds=5.0,
    )
    
    with patch("httpx.AsyncClient.request") as mock_request:
        mock_request.return_value.status_code = 200
        mock_request.return_value.text = "success"
        mock_request.return_value.json.return_value = {"key": "value"}
        
        response = await tool.execute(request)
    
    assert response.status == ToolStatus.SUCCESS
    assert response.output["status_code"] == 200
    assert response.attempts == 1

@pytest.mark.asyncio
async def test_http_tool_timeout():
    tool = HttpTool()
    request = ToolRequest(
        workflow_id="test-wf",
        tool_name="http",
        input={"method": "GET", "url": "https://api.example.com/slow"},
        timeout_seconds=0.001,  # Very short timeout
    )
    
    with patch("httpx.AsyncClient.request") as mock_request:
        mock_request.side_effect = asyncio.TimeoutError()
        
        response = await tool.execute(request)
    
    assert response.status == ToolStatus.TIMEOUT
    assert "timed out" in response.error
```
