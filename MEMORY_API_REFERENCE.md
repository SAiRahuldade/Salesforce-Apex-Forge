# Memory Agent - Complete API Reference

Complete reference for all Memory Agent APIs.

## 📦 Module Structure

```
salesforce_ai_engineer.memory/
├── __init__.py
├── store.py          # BaseMemoryStore (abstract interface)
├── sqlite_store.py   # SQLiteMemoryStore (implementation)
└── manager.py        # MemoryManager (high-level API)

salesforce_ai_engineer.models.domain/
└── memory.py         # All memory record models
```

## 🏗️ BaseMemoryStore (Abstract Interface)

Abstract base class that all storage implementations must follow.

### CRUD Operations

#### `async create(record: MemoryRecord) -> str`
Create a new memory record.

```python
record_id = await store.create(project_memory)
```

**Parameters:**
- `record` (MemoryRecord): Record to create

**Returns:**
- `str`: ID of created record

**Raises:**
- `RecordAlreadyExistsError`: If record with same ID exists
- `MemoryStoreOperationError`: If creation fails

---

#### `async read(record_id: str) -> Optional[MemoryRecord]`
Read a memory record by ID.

```python
record = await store.read("record-id-123")
```

**Parameters:**
- `record_id` (str): ID of record to read

**Returns:**
- `Optional[MemoryRecord]`: Record if found, None otherwise

---

#### `async read_many(record_ids: List[str]) -> List[MemoryRecord]`
Read multiple memory records.

```python
records = await store.read_many(["id1", "id2", "id3"])
```

**Parameters:**
- `record_ids` (List[str]): List of record IDs

**Returns:**
- `List[MemoryRecord]`: Found records (preserves order)

---

#### `async update(record_id: str, updates: Dict[str, Any], change_description: str = "", created_by: str = "system") -> MemoryRecord`
Update an existing memory record.

```python
updated = await store.update(
    "record-id",
    {"title": "New Title", "status": "archived"},
    change_description="Updated title and status",
    created_by="AgentName"
)
```

**Parameters:**
- `record_id` (str): ID of record to update
- `updates` (Dict[str, Any]): Fields to update
- `change_description` (str): Description of change (for audit trail)
- `created_by` (str): Who is making this update

**Returns:**
- `MemoryRecord`: Updated record

**Raises:**
- `RecordNotFoundError`: If record doesn't exist

---

#### `async delete(record_id: str, soft: bool = True) -> None`
Delete a memory record.

```python
await store.delete("record-id", soft=True)  # Mark as deleted
await store.delete("record-id", soft=False) # Permanently remove
```

**Parameters:**
- `record_id` (str): ID of record to delete
- `soft` (bool): If True, mark as deleted; if False, hard delete

**Raises:**
- `RecordNotFoundError`: If record doesn't exist

---

#### `async exists(record_id: str) -> bool`
Check if a record exists.

```python
exists = await store.exists("record-id")
```

**Parameters:**
- `record_id` (str): ID to check

**Returns:**
- `bool`: True if exists, False otherwise

---

### Search & Filter

#### `async search(query: MemorySearchQuery) -> List[MemoryRecord]`
Search memory records by keywords and metadata.

```python
results = await store.search(MemorySearchQuery(
    keywords=["optimization", "performance"],
    category=MemoryCategory.EXECUTION_HISTORY,
    min_confidence=0.8,
    limit=50,
    offset=0
))
```

**Parameters:**
- `query` (MemorySearchQuery): Search query object

**Returns:**
- `List[MemoryRecord]`: Matching records (ordered by relevance)

---

#### `async filter(filters: List[MemoryFilter], operator: str = "and") -> List[MemoryRecord]`
Filter records by complex criteria.

```python
records = await store.filter([
    MemoryFilter(field="status", operator="eq", value="active"),
    MemoryFilter(field="metadata_priority", operator="gte", value=7),
    MemoryFilter(field="created_at", operator="gte", value=datetime.utcnow() - timedelta(days=7))
], operator="and")
```

**Parameters:**
- `filters` (List[MemoryFilter]): List of filter criteria
- `operator` (str): "and" or "or" to combine filters

**Returns:**
- `List[MemoryRecord]`: Matching records

**Supported operators:**
- `eq` - Equal
- `ne` - Not equal
- `gt` - Greater than
- `lt` - Less than
- `gte` - Greater than or equal
- `lte` - Less than or equal
- `in` - In list
- `contains` - String contains
- `regex` - Regex match

---

#### `async list_by_category(category: MemoryCategory, status: Optional[MemoryStatus] = None, limit: int = 100, offset: int = 0) -> Tuple[List[MemoryRecord], int]`
List records by category.

```python
records, total = await store.list_by_category(
    category=MemoryCategory.COMPLETED_TASK,
    status=MemoryStatus.ACTIVE,
    limit=20,
    offset=0
)
```

**Parameters:**
- `category` (MemoryCategory): Category to filter by
- `status` (Optional[MemoryStatus]): Optional status filter
- `limit` (int): Max records to return
- `offset` (int): Offset for pagination

**Returns:**
- `Tuple[List[MemoryRecord], int]`: (records, total_count)

---

#### `async list_by_creator(created_by: str, limit: int = 100, offset: int = 0) -> Tuple[List[MemoryRecord], int]`
List records created by specific agent.

```python
records, total = await store.list_by_creator("DataAgent", limit=50, offset=100)
```

**Parameters:**
- `created_by` (str): Creator name/ID
- `limit` (int): Max records to return
- `offset` (int): Offset for pagination

**Returns:**
- `Tuple[List[MemoryRecord], int]`: (records, total_count)

---

### Tagging

#### `async add_tags(record_id: str, tags: List[str]) -> None`
Add tags to a record.

```python
await store.add_tags("record-id", ["important", "urgent", "production"])
```

**Parameters:**
- `record_id` (str): Record ID
- `tags` (List[str]): Tags to add

**Raises:**
- `RecordNotFoundError`: If record doesn't exist

---

#### `async remove_tags(record_id: str, tags: List[str]) -> None`
Remove tags from a record.

```python
await store.remove_tags("record-id", ["deprecated"])
```

**Parameters:**
- `record_id` (str): Record ID
- `tags` (List[str]): Tags to remove

---

#### `async find_by_tags(tags: List[str], operator: str = "and") -> List[MemoryRecord]`
Find records with specific tags.

```python
# Records with ALL tags
records = await store.find_by_tags(["critical", "system"], operator="and")

# Records with ANY tag
records = await store.find_by_tags(["urgent", "important"], operator="or")
```

**Parameters:**
- `tags` (List[str]): Tags to search for
- `operator` (str): "and" or "or" to combine

**Returns:**
- `List[MemoryRecord]`: Matching records

---

#### `async list_all_tags() -> List[str]`
List all tags in use.

```python
all_tags = await store.list_all_tags()
```

**Returns:**
- `List[str]`: All tags in system

---

### Versioning

#### `async get_history(record_id: str, limit: int = 100) -> List[MemoryVersion]`
Get version history for a record.

```python
versions = await store.get_history("record-id", limit=50)

for version in versions:
    print(f"Version {version.version_number}: {version.change_description}")
```

**Parameters:**
- `record_id` (str): Record ID
- `limit` (int): Max versions to return

**Returns:**
- `List[MemoryVersion]`: Version history (newest first)

---

#### `async restore_version(record_id: str, version_number: int) -> MemoryRecord`
Restore a record to a previous version.

```python
restored = await store.restore_version("record-id", version_number=3)
```

**Parameters:**
- `record_id` (str): Record ID
- `version_number` (int): Version to restore to

**Returns:**
- `MemoryRecord`: Restored record

**Raises:**
- `RecordNotFoundError`: If record or version doesn't exist

---

### Relationships

#### `async create_relationship(relationship: MemoryRelationship) -> str`
Create a relationship between two records.

```python
rel_id = await store.create_relationship(MemoryRelationship(
    source_id="record-1",
    target_id="record-2",
    relationship_type="depends_on",
    bidirectional=False,
    metadata={"strength": "high"}
))
```

**Parameters:**
- `relationship` (MemoryRelationship): Relationship to create

**Returns:**
- `str`: ID of created relationship

---

#### `async get_relationships(record_id: str, direction: str = "outgoing") -> List[MemoryRelationship]`
Get relationships for a record.

```python
# Outgoing relationships (record_id is source)
outgoing = await store.get_relationships("record-id", direction="outgoing")

# Incoming relationships (record_id is target)
incoming = await store.get_relationships("record-id", direction="incoming")

# Both
all_rels = await store.get_relationships("record-id", direction="both")
```

**Parameters:**
- `record_id` (str): Record ID
- `direction` (str): "outgoing", "incoming", or "both"

**Returns:**
- `List[MemoryRelationship]`: Relationships

---

#### `async delete_relationship(relationship_id: str) -> None`
Delete a relationship.

```python
await store.delete_relationship("rel-id-123")
```

**Parameters:**
- `relationship_id` (str): Relationship ID to delete

---

#### `async find_related_records(record_id: str, relationship_type: Optional[str] = None, depth: int = 1) -> List[MemoryRecord]`
Find records related to a given record.

```python
# 1 hop away
directly_related = await store.find_related_records("record-id", depth=1)

# 2 hops away
transitively_related = await store.find_related_records("record-id", depth=2)

# Only "implements" relationships
implementations = await store.find_related_records(
    "record-id",
    relationship_type="implements",
    depth=1
)
```

**Parameters:**
- `record_id` (str): Record ID
- `relationship_type` (Optional[str]): Optional filter by type
- `depth` (int): How many hops to search

**Returns:**
- `List[MemoryRecord]`: Related records

---

### Statistics & Analytics

#### `async count_by_category() -> Dict[str, int]`
Count records by category.

```python
counts = await store.count_by_category()
# {"execution_history": 1523, "completed_task": 450, ...}
```

**Returns:**
- `Dict[str, int]`: Category → count mapping

---

#### `async count_by_status() -> Dict[str, int]`
Count records by status.

```python
counts = await store.count_by_status()
# {"active": 1800, "archived": 200, "deleted": 50}
```

**Returns:**
- `Dict[str, int]`: Status → count mapping

---

#### `async count_by_creator() -> Dict[str, int]`
Count records by creator.

```python
counts = await store.count_by_creator()
# {"Orchestrator": 500, "Planner": 400, "DataAgent": 900}
```

**Returns:**
- `Dict[str, int]`: Creator → count mapping

---

#### `async get_total_records() -> int`
Get total count of all records.

```python
total = await store.get_total_records()
```

**Returns:**
- `int`: Total record count

---

#### `async get_storage_stats() -> Dict[str, Any]`
Get storage statistics.

```python
stats = await store.get_storage_stats()
# {
#   "total_records": 2000,
#   "by_category": {...},
#   "by_status": {...},
#   "by_creator": {...},
#   "file_size_bytes": 5242880
# }
```

**Returns:**
- `Dict[str, Any]`: Storage statistics

---

### Lifecycle & Maintenance

#### `async health_check() -> bool`
Check if storage is healthy and accessible.

```python
if await store.health_check():
    print("Memory store is healthy")
```

**Returns:**
- `bool`: True if healthy

---

#### `async clear_expired() -> int`
Clear records with expired TTL.

```python
cleared = await store.clear_expired()
print(f"Cleared {cleared} expired records")
```

**Returns:**
- `int`: Number of records cleared

---

#### `async close() -> None`
Close storage connection.

```python
await store.close()
```

---

#### `async open() -> None`
Open storage connection.

```python
await store.open()
```

**Raises:**
- `MemoryStoreConnectionError`: If unable to connect

---

### Transactions

#### `async begin_transaction() -> None`
Begin a transaction.

```python
await store.begin_transaction()
try:
    await store.create(record1)
    await store.create(record2)
    await store.commit_transaction()
except Exception:
    await store.rollback_transaction()
```

---

#### `async commit_transaction() -> None`
Commit current transaction.

---

#### `async rollback_transaction() -> None`
Rollback current transaction.

---

## 🎯 MemoryManager (High-Level API)

Convenient high-level interface for agents.

### Constructor

```python
manager = MemoryManager(
    store: BaseMemoryStore,
    event_bus: Optional[EventBus] = None,
    logger_instance: Optional[logging.Logger] = None
)
```

---

### Record Storage Methods

#### `async store_project_memory(...) -> str`
Store project-level knowledge.

```python
record_id = await manager.store_project_memory(
    title="AI Agent System Architecture",
    key_insights=["Modular design", "Event-driven"],
    technical_stack=["Python", "SQLite", "asyncio"],
    created_by="SystemAdmin",
    architecture_components=["Agent", "Memory", "Tools"],
    constraints=["Thread-safe", "Production-ready"],
    goals=["Scalable", "Extensible"]
)
```

---

#### `async store_workflow_history(...) -> str`
Store completed workflow information.

```python
record_id = await manager.store_workflow_history(
    workflow_id="wf-data-processing-001",
    workflow_type="DataProcessing",
    status="completed",
    duration_seconds=120.5,
    steps_executed=["validate", "process", "store"],
    created_by="Orchestrator"
)
```

---

#### `async store_execution_history(...) -> str`
Store agent execution information.

```python
record_id = await manager.store_execution_history(
    agent_name="DataAgent",
    task_description="Process customer records",
    success=True,
    duration_seconds=45.2,
    created_by="DataAgent",
    execution_id="exec-001",
    input_data={"count": 1000},
    output_data={"processed": 1000}
)
```

---

#### `async store_completed_task(...) -> str`
Store completed task information.

```python
record_id = await manager.store_completed_task(
    task_type="DataProcessing",
    task_id="task-001",
    agent_responsible="DataAgent",
    approach_used="MapReduce",
    result_summary="Successfully processed 1M records",
    success=True,
    duration_seconds=120.0,
    created_by="DataAgent",
    lessons_learned=["Parallelization improved speed"],
    similar_past_tasks=["task-previous-001"]
)
```

---

#### `async store_recovery_history(...) -> str`
Store failure recovery information.

```python
record_id = await manager.store_recovery_history(
    failure_id="fail-001",
    failure_type="NetworkTimeout",
    failure_description="API request timed out",
    recovery_strategy="retry_with_backoff",
    recovery_steps=["increase timeout", "retry"],
    success=True,
    time_to_recovery_seconds=30.0,
    created_by="RecoveryAgent",
    root_cause="Overloaded downstream service",
    preventive_measures=["Add circuit breaker"]
)
```

---

#### `async store_known_error(...) -> str`
Store known error information.

```python
record_id = await manager.store_known_error(
    error_type="TimeoutError",
    error_message="Request exceeded timeout",
    severity="high",
    created_by="SystemAdmin",
    reproduction_steps=["Call slow API", "Wait"],
    affected_components=["APIClient"],
    workaround="Increase timeout to 60s"
)
```

---

#### `async store_successful_fix(...) -> str`
Store successful fix information.

```python
record_id = await manager.store_successful_fix(
    error_type="TimeoutError",
    error_description="API timeouts",
    fix_description="Implemented exponential backoff",
    fix_steps=["Add backoff logic", "Update config", "Test"],
    time_to_fix_minutes=120.0,
    who_fixed="EngineerA",
    created_by="EngineerA",
    prevention_strategy="Use circuit breaker pattern"
)
```

---

#### `async store_architecture_decision(...) -> str`
Store architecture decision (ADR).

```python
record_id = await manager.store_architecture_decision(
    decision_id="ADR-001",
    status="accepted",
    context="Need to store agent execution history",
    decision="Use SQLite with versioning",
    rationale="Simple, no external dependencies",
    created_by="ArchitectureTeam",
    consequences=["Tighter single-node coupling"],
    alternatives_considered=["PostgreSQL", "MongoDB"]
)
```

---

#### `async store_coding_pattern(...) -> str`
Store successful coding pattern.

```python
record_id = await manager.store_coding_pattern(
    pattern_name="AsyncContextManager",
    pattern_description="Safely manage async resources",
    code_example="async with resource: ...",
    use_cases=["Database connections", "File handles"],
    created_by="EngineerB",
    pros=["Safe cleanup", "Exception handling"],
    cons=["Slightly more verbose"],
    best_for_languages=["Python"]
)
```

---

### Retrieval Methods

#### `async get_record(record_id: str) -> Optional[MemoryRecord]`
Get a specific record.

```python
record = await manager.get_record("record-id")
if record:
    print(record.title)
```

---

#### `async find_similar_tasks(task_type: str, limit: int = 5) -> List[MemoryRecord]`
Find similar previously completed tasks.

```python
similar = await manager.find_similar_tasks("DataProcessing", limit=10)
for task in similar:
    if task.success:
        print(f"Successful approach: {task.approach_used}")
```

---

#### `async find_past_errors(error_type: str, limit: int = 10) -> List[MemoryRecord]`
Find past occurrences of specific error type.

```python
past = await manager.find_past_errors("TimeoutError")
```

---

#### `async find_fixes_for_error(error_type: str, limit: int = 5) -> List[MemoryRecord]`
Find successful fixes for specific error type.

```python
fixes = await manager.find_fixes_for_error("TimeoutError")
for fix in fixes:
    print(f"Fastest fix: {fix.time_to_fix_minutes} minutes")
```

---

#### `async search_memory(keywords: Optional[List[str]] = None, category: Optional[MemoryCategory] = None, tags: Optional[List[str]] = None, created_by: Optional[str] = None, limit: int = 50) -> List[MemoryRecord]`
Search memory records.

```python
results = await manager.search_memory(
    keywords=["optimization", "performance"],
    category=MemoryCategory.COMPLETED_TASK,
    limit=20
)
```

---

### Relationship Methods

#### `async relate_records(source_id: str, target_id: str, relationship_type: str, bidirectional: bool = False, metadata: Optional[Dict[str, Any]] = None) -> str`
Create relationship between two records.

```python
rel_id = await manager.relate_records(
    source_id=project_id,
    target_id=execution_id,
    relationship_type="implemented_in",
    bidirectional=False
)
```

---

#### `async get_related_records(record_id: str, relationship_type: Optional[str] = None, depth: int = 1) -> List[MemoryRecord]`
Get records related to a specific record.

```python
related = await manager.get_related_records(
    record_id=project_id,
    relationship_type="implemented_in",
    depth=2
)
```

---

### Tagging Methods

#### `async tag_record(record_id: str, tags: List[str]) -> None`
Add tags to a record.

```python
await manager.tag_record("record-id", ["critical", "urgent"])
```

---

#### `async find_by_tags(tags: List[str], operator: str = "and") -> List[MemoryRecord]`
Find records with specific tags.

```python
critical = await manager.find_by_tags(["critical"], operator="or")
```

---

### Analytics Methods

#### `async get_agent_stats(agent_name: str) -> Dict[str, Any]`
Get statistics for a specific agent.

```python
stats = await manager.get_agent_stats("DataAgent")
# {
#   "agent_name": "DataAgent",
#   "total_records": 250,
#   "records_by_category": {...},
#   "success_rate": 0.95,
#   "total_duration_seconds": 5000.0
# }
```

---

#### `async get_system_stats() -> Dict[str, Any]`
Get overall system statistics.

```python
stats = await manager.get_system_stats()
```

---

#### `async get_task_success_rate(task_type: Optional[str] = None) -> float`
Get success rate for tasks.

```python
rate = await manager.get_task_success_rate("DataProcessing")
print(f"Success rate: {rate * 100}%")
```

---

### Version Methods

#### `async get_record_history(record_id: str, limit: int = 10) -> List[MemoryVersion]`
Get version history for a record.

```python
versions = await manager.get_record_history("record-id")
```

---

#### `async restore_record(record_id: str, version_number: int) -> Optional[MemoryRecord]`
Restore record to previous version.

```python
restored = await manager.restore_record("record-id", version_number=5)
```

---

### Lifecycle Methods

#### `async health_check() -> bool`
Check if memory store is healthy.

```python
if await manager.health_check():
    print("Memory system OK")
```

---

#### `async cleanup_expired() -> int`
Clean up expired records.

```python
cleared = await manager.cleanup_expired()
print(f"Cleaned {cleared} records")
```

---

## 📝 Models

### MemorySearchQuery

```python
class MemorySearchQuery(BaseModel):
    keywords: Optional[List[str]] = None
    category: Optional[MemoryCategory] = None
    status: Optional[MemoryStatus] = None
    tags: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    created_by: Optional[str] = None
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=100, ge=1, le=10000)
    offset: int = Field(default=0, ge=0)
```

---

### MemoryFilter

```python
class MemoryFilter(BaseModel):
    field: str
    operator: Literal["eq", "ne", "gt", "lt", "gte", "lte", "in", "contains", "regex"]
    value: Any
```

---

### MemoryRelationship

```python
class MemoryRelationship(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str
    target_id: str
    relationship_type: str
    bidirectional: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

---

### MemoryVersion

```python
class MemoryVersion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    record_id: str
    version_number: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    content_before: Dict[str, Any]
    content_after: Dict[str, Any]
    change_description: str
    change_type: str
```

---

## 🚨 Exceptions

```python
class MemoryStoreError(Exception):
    """Base exception for memory store errors."""

class RecordNotFoundError(MemoryStoreError):
    """Raised when a record is not found."""

class RecordAlreadyExistsError(MemoryStoreError):
    """Raised when trying to create duplicate record."""

class MemoryStoreConnectionError(MemoryStoreError):
    """Raised when unable to connect to storage backend."""

class MemoryStoreOperationError(MemoryStoreError):
    """Raised when an operation fails."""
```

---

## 📚 Enumerations

```python
class MemoryCategory(str, Enum):
    PROJECT_MEMORY = "project_memory"
    WORKFLOW_HISTORY = "workflow_history"
    EXECUTION_HISTORY = "execution_history"
    AGENT_INTERACTION = "agent_interaction"
    COMPLETED_TASK = "completed_task"
    RECOVERY_HISTORY = "recovery_history"
    DEPLOYMENT_HISTORY = "deployment_history"
    ARCHITECTURE_DECISION = "architecture_decision"
    KNOWN_ERROR = "known_error"
    SUCCESSFUL_FIX = "successful_fix"
    USER_PREFERENCE = "user_preference"
    CODING_PATTERN = "coding_pattern"
    REWARD_RECORD = "reward_record"
    EXECUTION_METRIC = "execution_metric"

class MemoryStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"
    DELETED = "deleted"
```

---

**API Version**: 1.0
**Last Updated**: 2026-06-12
**Status**: ✅ Complete
