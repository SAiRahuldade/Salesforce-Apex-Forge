# Tool Layer Architecture Diagrams

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AGENTS LAYER                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │   Orchestrator   │  │    Planner       │  │  Recovery Agent  │  │
│  │      Agent       │  │      Agent       │  │      Agent       │  │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  │
│           │                     │                     │             │
│           └─────────────────────┼─────────────────────┘             │
│                                 │                                   │
│                        ToolRequest (JSON)                           │
│                                 │                                   │
│                                 ▼                                   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                      TOOL LAYER (This Implementation)               │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  ToolExecutor                               │   │
│  │  ┌────────────────────────────────────────────────────────┐ │   │
│  │  │ - Dispatches ToolRequest to registry                  │ │   │
│  │  │ - Emits lifecycle events (TOOL_REQUESTED, RESPONDED)  │ │   │
│  │  │ - Propagates correlation IDs                          │ │   │
│  │  │ - Standardizes error responses                        │ │   │
│  │  └────────────────────────────────────────────────────────┘ │   │
│  └────────────────────┬─────────────────────────────────────────┘   │
│                       │                                             │
│                       ▼                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  ToolRegistry                               │   │
│  │  ┌────────────────────────────────────────────────────────┐ │   │
│  │  │ Tool Name Resolution (case-insensitive)               │ │   │
│  │  │ - Resolve: tool_name → BaseTool instance             │ │   │
│  │  │ - Aliases: sf, sfdx, salesforce → SalesforceCliTool │ │   │
│  │  │ - Discovery: names(), all_schemas(), schema_for()   │ │   │
│  │  │ - Schema generation for agent introspection          │ │   │
│  │  └────────────────────────────────────────────────────────┘ │   │
│  └────────────────────┬─────────────────────────────────────────┘   │
│                       │                                             │
│     ┌─────────────────┼─────────────────┬────────────┐             │
│     │                 │                 │            │             │
│     ▼                 ▼                 ▼            ▼             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                BaseTool (Abstract Base Class)                │  │
│  │                                                              │  │
│  │  async execute(ToolRequest) → ToolResponse                  │  │
│  │  ├─ validate_input()         [Pydantic validation]          │  │
│  │  ├─ _run()                   [Tool-specific logic]          │  │
│  │  ├─ timeout_protection()     [asyncio.wait_for]            │  │
│  │  ├─ retry_with_backoff()     [Exponential backoff]         │  │
│  │  ├─ error_classification()   [9 error types]               │  │
│  │  └─ _response()              [Metrics collection]           │  │
│  │                                                              │  │
│  │  Configuration:                                              │  │
│  │  - default_timeout_seconds: 30.0                            │  │
│  │  - default_retries: 0                                       │  │
│  │  - base_retry_delay_seconds: 0.25                           │  │
│  │  - max_retry_delay_seconds: 10.0                            │  │
│  │  - backoff_multiplier: 2.0                                  │  │
│  │  - max_response_size_bytes: 10MB                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│     │                                                               │
│     └─────────────────────────────────────────────────┐            │
│                                                       │            │
└───────────────────────────────────────────────────────┼────────────┘
                                                        │
                                 ┌──────────────────────┼──────────────────────┐
                                 │                      │                      │
                                 ▼                      ▼                      ▼
                          ┌────────────────┐    ┌────────────────┐    ┌───────────────┐
                          │ Execution Tool │    │ Data Tools     │    │ External API  │
                          │                │    │                │    │ Integration   │
                          │ • Salesforce   │    │ • JSON         │    │               │
                          │ • Shell        │    │ • YAML         │    │ • HTTP/REST   │
                          │ • Command      │    │ • XML          │    │ • Ollama LLM  │
                          │ • Git          │    │                │    │               │
                          │ • Filesystem   │    │                │    │               │
                          │ • SQLite       │    │                │    │               │
                          │                │    │                │    │               │
                          └────────────────┘    └────────────────┘    └───────────────┘
                                 │                      │                      │
                                 ▼                      ▼                      ▼
                          ┌────────────────┐    ┌────────────────┐    ┌───────────────┐
                          │ External       │    │ Data Format    │    │ Network/APIs  │
                          │ Services       │    │ Processing     │    │               │
                          │                │    │                │    │               │
                          │ SF Org         │    │ JSON parsing   │    │ REST endpoints│
                          │ Git servers    │    │ YAML parsing   │    │ HTTP requests │
                          │ OS processes   │    │ XML conversion │    │ LLM services  │
                          │ Databases      │    │                │    │               │
                          └────────────────┘    └────────────────┘    └───────────────┘
```

## Execution Flow

```
Agent Request
    │
    ▼
┌─────────────────────────────────┐
│ Create ToolRequest              │
│ - workflow_id                   │
│ - tool_name                     │
│ - input (dict)                  │
│ - correlation_id (auto-gen)     │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│ ToolExecutor.execute()          │
│ - Emit TOOL_REQUESTED event     │
│ - Resolve tool from registry    │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│ BaseTool.execute()              │
│ ┌─────────────────────────────┐ │
│ │ 1. Validate Input           │ │
│ │    (Pydantic model)         │ │
│ │                             │ │
│ │    ✗ Invalid → Error        │ │
│ │    ✓ Valid → Continue       │ │
│ └──────────┬──────────────────┘ │
│            ▼                    │
│ ┌─────────────────────────────┐ │
│ │ 2. Execute with Timeout     │ │
│ │    (asyncio.wait_for)       │ │
│ │    Attempt 1:               │ │
│ │    await _run()             │ │
│ │                             │ │
│ │    ✗ Timeout → Check retry  │ │
│ │    ✓ Success → Build resp   │ │
│ │    ✗ Error → Check retry    │ │
│ └──────────┬──────────────────┘ │
│            ▼                    │
│ ┌─────────────────────────────┐ │
│ │ 3. Classify Error & Retry?  │ │
│ │                             │ │
│ │ Error Type:                 │ │
│ │ ├─ TIMEOUT (retryable)      │ │
│ │ ├─ NETWORK (retryable)      │ │
│ │ ├─ VALIDATION (non-retry)   │ │
│ │ ├─ NOT_FOUND (non-retry)    │ │
│ │ └─ ... (7 types total)      │ │
│ │                             │ │
│ │ If retryable & attempts < max│ │
│ │ → Backoff & Retry           │ │
│ │ Else → Fail                 │ │
│ └──────────┬──────────────────┘ │
│            ▼                    │
│ ┌─────────────────────────────┐ │
│ │ 4. Exponential Backoff      │ │
│ │    (if retrying)            │ │
│ │                             │ │
│ │ Delay = min(                │ │
│ │   base * (mult ^ attempt)   │ │
│ │   * (0.5-1.0 jitter),       │ │
│ │   max_delay                 │ │
│ │ )                           │ │
│ │                             │ │
│ │ Attempt 1: 0.13-0.25s       │ │
│ │ Attempt 2: 0.25-0.5s        │ │
│ │ Attempt 3: 0.5-1.0s         │ │
│ │ Attempt N: capped at 10s    │ │
│ │                             │ │
│ │ → Loop back to Attempt      │ │
│ └──────────┬──────────────────┘ │
│            ▼                    │
│ ┌─────────────────────────────┐ │
│ │ 5. Validate Response        │ │
│ │    - Check size (<10MB)      │ │
│ │    - Validate JSON-able      │ │
│ │                             │ │
│ │    ✗ Invalid → Error        │ │
│ │    ✓ Valid → Continue       │ │
│ └──────────┬──────────────────┘ │
│            ▼                    │
│ ┌─────────────────────────────┐ │
│ │ 6. Build ToolResponse       │ │
│ │    - status (SUCCESS/FAILED)│ │
│ │    - output (if success)    │ │
│ │    - error (if failed)      │ │
│ │    - error_type             │ │
│ │    - metrics:               │ │
│ │      * duration_seconds     │ │
│ │      * started_at           │ │
│ │      * completed_at         │ │
│ │      * tool_name            │ │
│ │      * correlation_id       │ │
│ │    - attempts               │ │
│ └──────────┬──────────────────┘ │
└───────────┼────────────────────┘
            │
            ▼
┌─────────────────────────────────┐
│ ToolExecutor                    │
│ - Emit TOOL_RESPONDED event     │
│ - Return ToolResponse           │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│ Agent Handles Response          │
│ - Check status                  │
│ - Extract output or error       │
│ - Log metrics                   │
│ - Continue or escalate          │
└─────────────────────────────────┘
```

## Tool Resolution & Discovery

```
┌──────────────────────────────────────┐
│ Agent discovers tools at runtime     │
│ registry.schema_for("tool_name")     │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│ ToolRegistry                                 │
│                                              │
│ _tools: dict[str, BaseTool]                 │
│ ├─ "sf" → SalesforceCliTool()               │
│ ├─ "sfdx" → SalesforceCliTool() (alias)     │
│ ├─ "salesforce" → SalesforceCliTool() (alias)
│ ├─ "git" → GitTool()                        │
│ ├─ "fs" → FilesystemTool()                  │
│ ├─ "shell" → ShellTool()                    │
│ ├─ "http" → HttpTool()                      │
│ ├─ "sqlite" → SQLiteTool()                  │
│ ├─ "json" → JSONTool()                      │
│ ├─ "yaml" → YAMLTool()                      │
│ └─ "xml" → XMLTool()                        │
│                                              │
│ Methods:                                     │
│ - resolve("git") → GitTool                  │
│ - names() → ["fs", "git", "http", ...]     │
│ - schema_for("git") → ToolSchema            │
│ - all_schemas() → List[ToolSchema]          │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│ ToolSchema                                   │
│                                              │
│ {                                            │
│   "name": "git",                             │
│   "description": "Execute git commands...",  │
│   "input_schema": {                          │
│     "type": "object",                        │
│     "properties": {                          │
│       "args": {                              │
│         "type": "array",                     │
│         "items": {"type": "string"}          │
│       },                                     │
│       "cwd": {"type": "string"},             │
│       "stdin": {"type": "string"}            │
│     },                                       │
│     "required": ["args"]                     │
│   },                                         │
│   "input_example": {                         │
│     "args": ["clone", "url", "dir"],         │
│     "cwd": "/workspace"                      │
│   }                                          │
│ }                                            │
└──────────────────────────────────────────────┘
```

## Error Classification & Retry Decision Tree

```
┌──────────────────────────────────┐
│ Exception During Tool Execution  │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│ classify_error(exception) → ToolErrorType    │
├──────────────────────────────────────────────┤
│ Match Exception Type:                        │
│                                              │
│ asyncio.TimeoutError                         │
│ ├─→ TIMEOUT ✓ Retryable                      │
│                                              │
│ ConnectionError, ConnectionRefusedError      │
│ ├─→ NETWORK ✓ Retryable                      │
│                                              │
│ ExternalProcessError, subprocess.CalledProcessError
│ ├─→ EXTERNAL_PROCESS ✓ Retryable             │
│                                              │
│ sqlite3.DatabaseError                        │
│ ├─→ DATABASE ✓ Retryable                     │
│                                              │
│ ValueError (validation)                      │
│ ├─→ VALIDATION ✗ Non-retryable               │
│                                              │
│ FileNotFoundError                            │
│ ├─→ NOT_FOUND ✗ Non-retryable                │
│                                              │
│ PermissionError                              │
│ ├─→ PERMISSION ✗ Non-retryable               │
│                                              │
│ JSONDecodeError, ParseError                  │
│ ├─→ SERIALIZATION ✗ Non-retryable            │
│                                              │
│ Other                                        │
│ ├─→ UNKNOWN ✓ Retryable (fallback)          │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│ Decision: Retry or Fail?                     │
├──────────────────────────────────────────────┤
│                                              │
│ IF error_type IS retryable                   │
│   AND attempt < max_attempts                 │
│   AND timeout_not_exceeded                   │
│ THEN:                                        │
│   │                                          │
│   ├─→ Compute backoff delay                  │
│   │   delay = min(base * mult^attempt        │
│   │            * jitter, max)                │
│   │                                          │
│   ├─→ Sleep(delay)                           │
│   │                                          │
│   └─→ Retry loop back                        │
│                                              │
│ ELSE:                                        │
│   │                                          │
│   └─→ Build error response                   │
│       status = FAILED or TIMEOUT             │
│       error_type = classified_type           │
│       error = exception message              │
│       attempts = current_attempt             │
│                                              │
└──────────────────────────────────────────────┘
```

## Response Building Pipeline

```
Successful Execution
         │
         ▼
    output dict
         │
         ├─→ Validate size (<10MB)
         │
         ├─→ Compute metrics
         │   ├─ duration_seconds
         │   ├─ started_at (ISO)
         │   ├─ completed_at (ISO)
         │   ├─ tool_name
         │   └─ correlation_id
         │
         ▼
    ┌─────────────────────────────────┐
    │ ToolResponse (SUCCESS)          │
    ├─────────────────────────────────┤
    │ status: ToolStatus.SUCCESS      │
    │ output: output_dict             │
    │ error: None                     │
    │ error_type: None                │
    │ metrics: {...}                  │
    │ attempts: 1                     │
    │ started_at: datetime            │
    │ completed_at: datetime          │
    └─────────────────────────────────┘

Failed Execution
         │
         ▼
   Exception raised
         │
         ├─→ Classify error type
         │
         ├─→ Compute metrics
         │   ├─ duration_seconds
         │   ├─ started_at (ISO)
         │   ├─ completed_at (ISO)
         │   ├─ tool_name
         │   ├─ correlation_id
         │   └─ error_type
         │
         ▼
    ┌─────────────────────────────────┐
    │ ToolResponse (FAILED/TIMEOUT)   │
    ├─────────────────────────────────┤
    │ status: ToolStatus.FAILED       │
    │ output: {}                      │
    │ error: str(exception)           │
    │ error_type: classified_type     │
    │ metrics: {...}                  │
    │ attempts: N (if retried)        │
    │ started_at: datetime            │
    │ completed_at: datetime          │
    └─────────────────────────────────┘
```

## DI Container Integration

```
┌─────────────────────────────────────────────┐
│ core/bootstrap.py                           │
│                                             │
│ build_container():                          │
│   container = Container()                   │
│                                             │
│   # ... other registrations ...             │
│                                             │
│   container.register_factory(               │
│     "tool_registry",                        │
│     lambda services: build_tool_registry(   │
│       settings, Path.cwd()                  │
│     ),                                      │
│     singleton=True                          │
│   )                                         │
│                                             │
│   container.register_factory(               │
│     "tool_executor",                        │
│     lambda services: build_tool_executor(   │
│       registry=services.resolve(            │
│         "tool_registry"                     │
│       ),                                    │
│       event_bus=services.resolve(           │
│         "event_bus", EventBus               │
│       ),                                    │
│       logger_instance=services.resolve(     │
│         "logger"                            │
│       )                                     │
│     ),                                      │
│     singleton=True                          │
│   )                                         │
│                                             │
│   return container                          │
└─────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ Container Singleton Storage                 │
│                                             │
│ {                                           │
│   "tool_registry": ToolRegistry(...),       │
│   "tool_executor": ToolExecutor(...)        │
│ }                                           │
└─────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│ Agents resolve at runtime:                  │
│                                             │
│ executor = container.resolve("tool_executor")
│ registry = container.resolve("tool_registry")
│                                             │
│ request = ToolRequest(...)                  │
│ response = await executor.execute(request)  │
└─────────────────────────────────────────────┘
```

## Performance Characteristics

```
Tool Execution Timeline (Percentiles)

         P50        P99        P999
         │          │          │
Startup  |0.5ms     1ms        5ms
Validation|0.5ms    2ms        5ms
Tool Op  |100-500ms 5000ms     ~

Total    |101-501ms 5002ms     ~

With Retry (3 attempts on transient error):

         P50              P99              P999
         │                │                │
Attempt1 |100ms           500ms            1000ms
Backoff1 |250ms (jitter)  500ms (jitter)   1000ms
Attempt2 |100ms           500ms            1000ms
Backoff2 |500ms (jitter)  1000ms (jitter)  2000ms
Attempt3 |100ms           500ms            1000ms
Success  |
         │                │                │
Total    |950ms (best)    ~3500ms (worst)  ~5000ms
```
