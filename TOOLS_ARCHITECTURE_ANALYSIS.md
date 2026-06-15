# Tools Directory Architecture Analysis

**Date**: June 12, 2026  
**Scope**: Complete review of `src/salesforce_ai_engineer/tools/` implementation

---

## Table of Contents
1. [Current Architecture](#current-architecture)
2. [Implemented Tools](#implemented-tools)
3. [Implementation Status Matrix](#implementation-status-matrix)
4. [Error Handling](#error-handling)
5. [Async & Timeout Handling](#async--timeout-handling)
6. [Structured Models](#structured-models)
7. [Critical Gaps](#critical-gaps)
8. [Recommendations](#recommendations)

---

## Current Architecture

### Design Patterns

The tools layer follows a **plugin architecture** with three core components:

#### 1. **BaseTool Abstract Class** (`base.py`)
All tools inherit from `BaseTool` and implement the async-first execution model:

```python
class BaseTool(ABC):
    """Common async interface implemented by every external-resource tool."""

    name: str
    description: str
    input_model: type | None = None

    def __init__(self, config: ToolRuntimeConfig | None = None) -> None:
        self.config = config or ToolRuntimeConfig()

    async def execute(self, request: ToolRequest) -> ToolResponse:
        """Validate, run, time, classify, and standardize a tool invocation."""
        # Retry loop with timeout handling
        # Automatic error classification and response formatting
```

**Key responsibilities**:
- Input validation using Pydantic models
- Retry logic with exponential backoff
- Timeout enforcement via `asyncio.wait_for()`
- Error classification and response wrapping
- Metrics collection (duration, timestamps, attempts)

#### 2. **ToolRegistry** (`registry.py`)
Singleton registry for tool name → implementation mapping:

```python
class ToolRegistry:
    """Open-ended registry mapping tool names to implementations."""
    
    def register(self, tool: BaseTool, *aliases: str) -> None:
        # Supports multiple aliases (e.g., "salesforce_cli" → "sf", "sfdx")
    
    def resolve(self, name: str) -> BaseTool:
        # Case-insensitive tool resolution
```

#### 3. **ToolExecutor** (`executor.py`)
Facade that dispatches requests and manages tool lifecycle events:

```python
class ToolExecutor:
    """Dispatches ToolRequest objects while enforcing the tool boundary."""
    
    async def execute(self, request: ToolRequest) -> ToolResponse:
        # Emits TOOL_REQUESTED lifecycle event
        # Resolves tool from registry
        # Delegates execution to BaseTool
        # Emits TOOL_RESPONDED lifecycle event with priority (HIGH for failures)
```

---

## Implemented Tools

### Command-Line Tools (`command.py`)

#### ShellCommandTool
```python
class ShellCommandTool(BaseTool):
    name = "shell"
    input_model = ShellCommandInput  # argv list interface
    
    async def _run(self, payload: ShellCommandInput, request: ToolRequest):
        return await run_process(
            payload.command,
            cwd=Path(payload.cwd).resolve() if payload.cwd else None,
            input_text=payload.stdin,
        )
```
- **Input**: `command: list[str]`, `cwd: str`, `stdin: str`
- **Output**: `{command, cwd, return_code, stdout, stderr}`
- **Error handling**: Raises `ExternalProcessError` on non-zero exit codes

#### GitTool
- Wraps `git` commands via constrained argv interface
- Same input/output as ShellCommandTool
- **Input**: `args: list[str]`, `cwd: str`, `stdin: str`

#### SalesforceCliTool
- Wraps Salesforce CLI (`sf` or `sfdx`) commands
- Validates executable choice in request
- **Input**: `args: list[str]`, `cwd: str`, `stdin: str`, `executable: str`

### HTTP/REST Tool (`http.py`)

```python
class HttpInput(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    json_body: Any | None = None
    text_body: str | None = None

class HttpTool(BaseTool):
    name = "http"
    async def _run(self, payload: HttpInput, request: ToolRequest):
        # Uses httpx.AsyncClient for async HTTP
        # Handles both JSON and text responses
        # Raises ToolNetworkError on HTTP errors
```

- **Features**: Full async HTTP client, timeout support, header/query param management
- **Output**: `{status_code, headers, text, json}`

### Database Tool (`sqlite.py`)

```python
class SQLiteInput(BaseModel):
    database_path: str
    statement: str
    parameters: list[Any] | dict[str, Any] = Field(default_factory=list)
    operation: Literal["query", "execute"] = "query"

class SQLiteTool(BaseTool):
    name = "sqlite"
    async def _run(self, payload: SQLiteInput, request: ToolRequest):
        # Uses aiosqlite for async database access
        # Supports both queries and statements
        # Validates statement is not empty
```

- **Features**: Parameterized queries, row factory for dict conversion
- **Output**: `{rows: [dict], row_count}` for queries; `{row_count, lastrowid}` for execute

### Filesystem Tool (`filesystem/tool.py`)

```python
class FilesystemInput(BaseModel):
    operation: Literal["read_text", "write_text", "exists", "list", "mkdir"]
    path: str
    content: str | None = None
    pattern: str = "*"

class FilesystemTool(BaseTool):
    name = "filesystem"
    
    def __init__(self, root: str | Path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
    
    async def _run(self, payload: FilesystemInput, request: ToolRequest):
        # Path escape detection: raises ToolPermissionError if path escapes root
        # Supports: read_text, write_text, exists, list (with glob patterns), mkdir
```

- **Security**: Enforced root boundary with `_resolve()` method
- **Output**: Varies by operation (content, exists boolean, file list, creation status)

### Structured Data Tools (`structured_data.py`)

#### JSONTool
```python
class JSONTool(BaseTool):
    name = "json"
    
    async def _run(self, payload: StructuredDataInput, request: ToolRequest):
        if payload.operation == "parse":
            return {"data": json.loads(payload.content)}
        return {"content": json.dumps(payload.data, ensure_ascii=False, indent=2, sort_keys=True)}
```

#### YAMLTool
```python
class YAMLTool(BaseTool):
    name = "yaml"
    
    async def _run(self, payload: StructuredDataInput, request: ToolRequest):
        if payload.operation == "parse":
            return {"data": yaml.safe_load(payload.content)}
        return {"content": yaml.safe_dump(payload.data, sort_keys=True, allow_unicode=True)}
```

#### XMLTool
- Bidirectional XML ↔ dict conversion
- Tree-based representation: `{tag, attributes, text, children}`
- Recursive element processing

**Input format** (shared):
```python
class StructuredDataInput(BaseModel):
    operation: Literal["parse", "format"]
    content: str | None = None  # For "parse"
    data: Any | None = None      # For "format"
```

### Ollama Tool (`ollama/tool.py`)

```python
class OllamaInput(BaseModel):
    messages: list[dict[str, str]]
    model: str | None = None
    format: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

class OllamaTool(BaseTool):
    name = "ollama"
    
    def __init__(self, config: OllamaConfig, client: AsyncClient | None = None, ...):
        super().__init__(*args, **kwargs)
        self.config = config
        self.client = client or AsyncClient(host=str(config.base_url))
    
    async def _run(self, payload: OllamaInput, request: ToolRequest):
        response = await self.client.chat(
            model=payload.model or self.config.model,
            messages=payload.messages,
            format=payload.format,
            options=payload.options,
        )
        return {"response": response}
```

- **Configuration**: Reads from `OllamaConfig` (base_url, model)
- **Testability**: Accepts injected client for testing
- **Error handling**: Wraps exceptions as `ToolNetworkError`

### Process Execution (`process.py`)

```python
async def run_process(
    command: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> dict[str, object]:
    """Run a subprocess without invoking a shell."""
    
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd) if cwd is not None else None,
        stdin=asyncio.subprocess.PIPE if input_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate(
        input_text.encode("utf-8") if input_text is not None else None
    )
    
    if process.returncode != 0:
        raise ExternalProcessError(
            f"Command failed with exit code {process.returncode}: {' '.join(command)}"
        )
    return {
        "command": command,
        "cwd": str(cwd),
        "return_code": process.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }
```

**Key points**:
- Fully async using `asyncio.create_subprocess_exec()`
- No shell invocation (safer for untrusted input)
- UTF-8 decoding with error replacement
- Both stdout and stderr captured

---

## Implementation Status Matrix

| Component | Status | Notes |
|-----------|--------|-------|
| **Base Infrastructure** | ✅ Complete | `BaseTool`, `ToolRegistry`, `ToolExecutor` |
| **Error Classification** | ✅ Complete | 9 error types, `classify_error()` function |
| **Retry/Backoff** | ✅ Complete | Built into `BaseTool.execute()` |
| **Timeout Handling** | ✅ Complete | `asyncio.wait_for()` with per-request config |
| **Metrics** | ⚠️ Partial | Duration and timestamps tracked, but no custom metrics |
| **HTTP Tool** | ✅ Complete | Full async HTTP client |
| **Database Tool** | ✅ Complete | Async SQLite with parameterized queries |
| **Filesystem Tool** | ✅ Complete | Safe sandbox with path escape detection |
| **Structured Data** | ✅ Complete | JSON, YAML, XML parse/format |
| **Process Execution** | ✅ Complete | Async subprocess with stdin/stdout/stderr |
| **Command Tools** | ✅ Complete | Shell, Git, Salesforce CLI |
| **Ollama Integration** | ✅ Complete | Local LLM chat interface |
| **Tool Factory** | ✅ Complete | `build_tool_registry()` registers all tools |
| **Registry Integration** | ❌ **MISSING** | Factory not wired into DI container |
| **Tool Discovery API** | ❌ **MISSING** | No OpenAPI/schema endpoint |
| **Lifecycle Events** | ✅ Complete | TOOL_REQUESTED, TOOL_RESPONDED events |
| **Testing** | ❌ **MISSING** | No test files in `tests/tools/` |

---

## Error Handling

### Error Type Classification (`errors.py`)

```python
class ToolErrorType(StrEnum):
    VALIDATION = "validation"        # Invalid input
    TIMEOUT = "timeout"               # Exceeded deadline
    NOT_FOUND = "not_found"          # Tool or resource not found
    PERMISSION = "permission"         # Access denied
    EXTERNAL_PROCESS = "external_process"  # Command failed
    NETWORK = "network"               # HTTP/API failure
    SERIALIZATION = "serialization"   # JSON/YAML/XML parse error
    DATABASE = "database"             # SQLite failure
    UNKNOWN = "unknown"               # Unmapped exception
```

### Error Hierarchy

```
ToolError (base)
├── ToolValidationError
├── ToolTimeoutError
├── ToolNotFoundError
├── ToolPermissionError
├── ExternalProcessError
├── ToolNetworkError
├── ToolSerializationError
└── ToolDatabaseError
```

### Error Classification Logic (`classify_error()`)

```python
def classify_error(error: BaseException) -> ToolErrorType:
    if isinstance(error, ToolError):
        return error.error_type
    if isinstance(error, TimeoutError):
        return ToolErrorType.TIMEOUT
    if isinstance(error, PermissionError):
        return ToolErrorType.PERMISSION
    if isinstance(error, FileNotFoundError):
        return ToolErrorType.NOT_FOUND
    return ToolErrorType.UNKNOWN
```

### Retryable Errors

```python
def is_retryable(self, error: BaseException) -> bool:
    return classify_error(error) in {
        ToolErrorType.TIMEOUT,
        ToolErrorType.NETWORK,
        ToolErrorType.EXTERNAL_PROCESS,
        ToolErrorType.DATABASE,
        ToolErrorType.UNKNOWN,
    }
```

**Non-retryable**: VALIDATION, NOT_FOUND, PERMISSION, SERIALIZATION

---

## Async & Timeout Handling

### Runtime Configuration

```python
@dataclass(frozen=True)
class ToolRuntimeConfig:
    default_timeout_seconds: float = 30.0
    default_retries: int = 0
    retry_delay_seconds: float = 0.25
```

### Timeout Enforcement

```python
async def execute(self, request: ToolRequest) -> ToolResponse:
    timeout = request.timeout_seconds or self.config.default_timeout_seconds
    attempts = self._attempts(request)
    
    for attempt in range(1, attempts + 1):
        try:
            # Enforce timeout with asyncio.wait_for()
            output = await asyncio.wait_for(
                self._run(validated_input, request),
                timeout=timeout,
            )
            return self._response(..., status=ToolStatus.SUCCESS, ...)
        except asyncio.TimeoutError as exc:
            error = ToolTimeoutError(f"Tool {self.name!r} timed out after {timeout} seconds")
            if attempt >= attempts:
                return self._error_response(..., status=ToolStatus.TIMEOUT)
            await asyncio.sleep(self.config.retry_delay_seconds)
```

### Retry Logic

- **Retry count**: Parsed from request input (`request.input.get("retries")`)
- **Delay**: Fixed `retry_delay_seconds` (currently 0.25s)
- **Backoff**: Currently LINEAR (no exponential backoff in BaseTool)
  - *(Note: exponential backoff is available in `core/retry.py` but not used by tools)*

---

## Structured Models

### Request/Response Models

#### ToolRequest (from `models/domain/shared.py`)

```python
class ToolRequest(ImmutableDomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    task_id: str | None = None
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0)
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
```

#### ToolResponse (from `models/domain/shared.py`)

```python
class ToolResponse(ImmutableDomainModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str
    workflow_id: str
    tool_name: str
    status: ToolStatus  # SUCCESS | FAILED | TIMEOUT
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    error_type: ToolErrorType | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)
    started_at: datetime | None = None
    completed_at: datetime = Field(default_factory=utc_now)
```

### Tool-Specific Input Models

All input models use **Pydantic** for validation:

| Tool | Input Model | Key Fields |
|------|-------------|-----------|
| http | `HttpInput` | method, url, headers, query, json_body, text_body |
| sqlite | `SQLiteInput` | database_path, statement, parameters, operation |
| filesystem | `FilesystemInput` | operation, path, content, pattern |
| json/yaml/xml | `StructuredDataInput` | operation, content, data |
| shell | `ShellCommandInput` | command, cwd, stdin |
| git | `CommandInput` | args, cwd, stdin |
| salesforce_cli | `CommandInput` | args, cwd, stdin, executable |
| ollama | `OllamaInput` | messages, model, format, options |

---

## Critical Gaps

### 1. **Container Integration** ❌

The `build_tool_registry()` function exists but is **never called**:

```python
# In factory.py (defined but unused)
def build_tool_registry(settings: Settings, workspace_root: Path) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(SalesforceCliTool(), "sf", "sfdx", "salesforce")
    registry.register(GitTool())
    registry.register(FilesystemTool(workspace_root), "fs")
    # ...
    return registry
```

**Impact**: Agents cannot resolve tools because the registry is not available in the DI container.

**Fix**: Add to `bootstrap.py`:
```python
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
        services.resolve("tool_registry"),
        services.resolve("event_bus"),
        services.resolve("logger"),
    ),
    singleton=True,
)
```

### 2. **No Test Coverage** ❌

- `tests/tools/` directory exists but is empty
- No unit tests for:
  - Tool validation
  - Retry logic
  - Timeout handling
  - Error classification
  - Individual tool implementations

### 3. **Missing Tool Discovery API** ❌

No mechanism for:
- Listing available tools
- Introspecting tool signatures
- Generating OpenAPI/JSON Schema definitions
- Dynamic tool documentation

**Suggestion**: Add endpoint to list tools with metadata:
```python
@router.get("/tools")
async def list_tools(executor: ToolExecutor) -> list[dict]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_model": tool.input_model.model_json_schema() if tool.input_model else None,
        }
        for tool in executor.registry._tools.values()
    ]
```

### 4. **Empty Subdirectories** ⚠️

- `salesforce/` – only `__init__.py`
- `shell/` – only `__init__.py`

These directories suggest planned Salesforce-specific and shell-specific tools but are not implemented.

### 5. **Retry Backoff Not Optimized** ⚠️

`BaseTool` uses linear delays (fixed 0.25s) instead of exponential backoff:

```python
await asyncio.sleep(self.config.retry_delay_seconds)  # Always 0.25s
```

Available in `core/retry.py` but not used:
```python
@dataclass(frozen=True)
class RetryPolicy:
    backoff: float = 2.0  # Exponential multiplier
    max_delay: float = 5.0
    jitter: float = 0.1
```

### 6. **Limited Metrics Collection** ⚠️

Metrics only include:
- Duration (seconds)
- Timestamps (ISO format)
- Attempt count

**Missing**:
- Request payload size
- Response payload size
- Error rates by type
- Tool-specific metrics (e.g., HTTP status codes, DB row counts)

### 7. **No Structured Logging** ⚠️

Tools use minimal logging. Example from `executor.py`:
```python
self.logger.info("Executing tool %s for workflow %s", request.tool_name, request.workflow_id)
```

**Missing**:
- Structured logs with correlation IDs
- Tool-specific context in logs
- Timing breakdowns (validation, execution, error classification)

---

## Recommendations

### Priority 1: Integration (Blocking)

1. **Wire ToolExecutor into DI container** (`bootstrap.py`)
   - Register `ToolRegistry` and `ToolExecutor` as singletons
   - Ensure agents can resolve tool_executor

2. **Create tool integration tests** (`tests/tools/`)
   - Test BaseTool retry and timeout logic
   - Test error classification
   - Test each tool implementation
   - Mock external services (HTTP, Ollama, SQLite)

### Priority 2: Missing Functionality

3. **Tool Discovery API**
   - Add endpoint to list registered tools
   - Include input schemas (JSON Schema format)
   - Generate OpenAPI documentation

4. **Implement missing tools**
   - `salesforce/` directory tools (e.g., metadata operations)
   - `shell/` directory tools (e.g., interactive shell, pipes)

5. **Structured logging**
   - Add structured log context to all tool operations
   - Include correlation IDs and metrics in logs

### Priority 3: Optimization

6. **Upgrade retry strategy**
   - Switch from linear to exponential backoff
   - Make backoff configurable per tool
   - Consider jitter for distributed systems

7. **Enhanced metrics**
   - Per-tool metric collection
   - Payload size tracking
   - Error rate aggregation
   - Performance SLO tracking

8. **Tool resource limits**
   - Memory limits for large responses
   - Response size validation
   - Database query result limits

---

## Summary

The tools architecture is **well-designed** with solid patterns for:
- ✅ Async execution
- ✅ Error handling
- ✅ Retry and timeout logic
- ✅ Structured models
- ✅ Event integration

However, **critical gaps** prevent immediate use:
- ❌ Tools not registered in DI container
- ❌ No test coverage
- ❌ No tool discovery mechanism

**Recommended next steps**: Fix container integration → Add tests → Implement discovery API → Enhance metrics.
