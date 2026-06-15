# Memory Agent - Architecture & Design

Comprehensive architecture documentation for the Memory Agent system.

## 🏗️ System Architecture

### Layered Design

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Layer                          │
│   Orchestrator | Planner | Recovery | Data Processing  │
└─────────────────────┬───────────────────────────────────┘
                      │ Uses
                      ▼
┌─────────────────────────────────────────────────────────┐
│               Memory Manager API                        │
│  (High-Level Interface - No Database Access)           │
│                                                         │
│  • store_*() methods for different record types        │
│  • find_*() methods for common search patterns         │
│  • get_*_stats() methods for analytics                │
│  • search_memory() for general search                  │
│  • relate_records() for relationships                 │
│  • tag_record() for tagging                           │
└─────────────────────┬───────────────────────────────────┘
                      │ Delegates to
                      ▼
┌─────────────────────────────────────────────────────────┐
│           Abstract MemoryStore Interface                │
│                (BaseMemoryStore)                        │
│                                                         │
│  • CRUD operations (create, read, update, delete)     │
│  • Search and filtering                               │
│  • Tagging operations                                 │
│  • Versioning operations                              │
│  • Relationship operations                            │
│  • Analytics operations                               │
│  • Transaction support                                │
└─────────────────────┬───────────────────────────────────┘
                      │ Implements
        ┌─────────────┼──────────────┐
        │             │              │
        ▼             ▼              ▼
    ┌─────────┐  ┌──────────┐  ┌──────────┐
    │ SQLite  │  │ Future:  │  │ Future:  │
    │ Store   │  │ Vector   │  │ Graph DB │
    │ (Now)   │  │ Store    │  │          │
    └─────────┘  └──────────┘  └──────────┘
        │             │              │
        └─────────────┼──────────────┘
                      │
                      ▼
        ┌──────────────────────────┐
        │  Persistent Storage      │
        │  (Files / Databases)     │
        └──────────────────────────┘
```

## 📊 Data Model

### Core Entities

```
MemoryRecord (Abstract Base)
├── id: str (UUID)
├── category: MemoryCategory
├── title: str
├── description: str
├── content: Dict[str, Any]
├── tags: List[MemoryTag]
├── metadata: MemoryMetadata
├── status: MemoryStatus (active/archived/deprecated/deleted)
├── created_at: datetime
├── updated_at: datetime
├── created_by: str

Specialized Types:
├── ProjectMemory
├── WorkflowHistory
├── ExecutionHistory
├── AgentInteraction
├── CompletedTask
├── RecoveryHistory
├── DeploymentHistory
├── ArchitectureDecision
├── KnownError
├── SuccessfulFix
├── UserPreference
├── CodingPattern
├── RewardRecord
└── ExecutionMetric
```

### Relationships

```
MemoryRelationship
├── id: str
├── source_id: str (MemoryRecord.id)
├── target_id: str (MemoryRecord.id)
├── relationship_type: str
├── bidirectional: bool
├── metadata: Dict[str, Any]
└── created_at: datetime
```

### Versioning

```
MemoryVersion
├── id: str
├── record_id: str (MemoryRecord.id)
├── version_number: int
├── created_at: datetime
├── created_by: str
├── content_before: Dict[str, Any]
├── content_after: Dict[str, Any]
├── change_description: str
└── change_type: str (create/update/delete)
```

## 🗄️ Storage Strategy

### SQLite Schema

#### memory_records table
```sql
CREATE TABLE memory_records (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    content TEXT NOT NULL (JSON),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    metadata_source TEXT NOT NULL,
    metadata_confidence REAL,
    metadata_relevance REAL,
    metadata_priority INTEGER,
    metadata_ttl_seconds INTEGER,
    metadata_custom TEXT (JSON)
)

Indexes:
- idx_category (for filtering by category)
- idx_status (for status queries)
- idx_created_by (for creator filtering)
- idx_created_at (for date range queries)
- idx_updated_at (for recent queries)
```

#### memory_tags table
```sql
CREATE TABLE memory_tags (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    tag_name TEXT NOT NULL,
    tag_value TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(record_id) REFERENCES memory_records(id)
)

Indexes:
- idx_tag_name (for tag searches)
- idx_tag_record (for tag-to-record mapping)
```

#### memory_versions table
```sql
CREATE TABLE memory_versions (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    content_before TEXT NOT NULL (JSON),
    content_after TEXT NOT NULL (JSON),
    change_description TEXT,
    change_type TEXT NOT NULL,
    FOREIGN KEY(record_id) REFERENCES memory_records(id),
    UNIQUE(record_id, version_number)
)

Indexes:
- idx_version_record (for history lookups)
```

#### memory_relationships table
```sql
CREATE TABLE memory_relationships (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    bidirectional BOOLEAN,
    metadata TEXT (JSON),
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_id) REFERENCES memory_records(id),
    FOREIGN KEY(target_id) REFERENCES memory_records(id)
)

Indexes:
- idx_rel_source (for outgoing relationships)
- idx_rel_target (for incoming relationships)
- idx_rel_type (for relationship type searches)
```

#### memory_fts table (Full-Text Search)
```sql
CREATE VIRTUAL TABLE memory_fts USING fts5(
    id,
    title,
    description,
    content_text,
    content=memory_records,
    content_rowid=rowid
)

Triggers:
- memory_fts_ai (auto-update on insert)
- memory_fts_au (auto-update on update)
- memory_fts_ad (auto-update on delete)
```

## 🔄 Operational Flows

### Create Record Flow

```
Agent
  │
  └─→ MemoryManager.store_*()
        │
        └─→ create_memory_record() [factory]
              │
              └─→ MemoryRecord subclass
                   │
                   └─→ BaseMemoryStore.create()
                        │
                        ├─→ Validate input (Pydantic)
                        ├─→ Check for duplicates
                        ├─→ Insert into memory_records
                        ├─→ Insert tags into memory_tags
                        ├─→ Insert into memory_fts
                        ├─→ Emit memory.record_created event
                        │
                        └─→ Return record_id
```

### Search Flow

```
Agent
  │
  └─→ MemoryManager.search_memory()
        │
        └─→ BaseMemoryStore.search()
              │
              ├─→ Build SQL query from MemorySearchQuery
              ├─→ Apply keyword filter (FTS5 search)
              ├─→ Apply category filter
              ├─→ Apply date range filter
              ├─→ Apply tag filter
              ├─→ Sort by relevance DESC, updated_at DESC
              ├─→ Apply pagination (LIMIT/OFFSET)
              │
              └─→ Fetch results and convert to MemoryRecords
```

### Update Record Flow

```
Agent
  │
  └─→ MemoryManager.* [implicit update]
        │
        └─→ BaseMemoryStore.update()
              │
              ├─→ Read existing record
              ├─→ Store old_content for versioning
              ├─→ Apply updates to record
              ├─→ Update memory_records row
              ├─→ Increment version_number
              ├─→ Insert into memory_versions
              │
              └─→ Return updated record
```

### Relationship Query Flow

```
Agent
  │
  └─→ MemoryManager.get_related_records(record_id, depth=N)
        │
        └─→ BaseMemoryStore.find_related_records()
              │
              ├─→ Initialize current_level = {record_id}
              │
              └─→ For each depth level:
                    │
                    ├─→ Get all relationships for current level
                    ├─→ Extract connected record IDs
                    ├─→ Add to next level for next iteration
                    │
                    └─→ Return all related IDs
                        │
                        └─→ Fetch MemoryRecords for related IDs
```

## 🔌 Extensibility Points

### Adding a New Storage Backend

```
1. Create new class inheriting from BaseMemoryStore:
   
   class YourStorageBackend(BaseMemoryStore):
       async def open(self): ...
       async def close(self): ...
       async def create(self, record): ...
       # ... implement all abstract methods

2. Register with MemoryManager:
   
   store = YourStorageBackend(config)
   await store.open()
   manager = MemoryManager(store)

3. No agent code changes needed!
```

### Adding a New Record Type

```
1. Create Pydantic model in models/domain/memory.py:
   
   class MyCustomMemory(BaseMemoryRecord):
       category: Literal[MemoryCategory.CUSTOM] = MemoryCategory.CUSTOM
       # ... add your fields

2. Add category to MemoryCategory enum

3. Update create_memory_record() factory function

4. Use from agents:
   
   record_id = await memory.store.create(MyCustomMemory(...))
```

## 🎯 Design Decisions

### 1. SQLite as Primary Backend

**Decision**: Use SQLite as the initial implementation.

**Rationale**:
- No external dependencies (embedded)
- ACID transaction support
- Full-text search (FTS5)
- Excellent for single-node deployments
- Easy to backup and migrate
- Good performance for up to millions of records

**Trade-offs**:
- Single-threaded writes (mitigated by async)
- Not ideal for distributed systems (can be solved with replicas)
- Limited to device storage capacity

### 2. Abstract Store Interface

**Decision**: Define BaseMemoryStore as abstract interface.

**Rationale**:
- Enables pluggable backends without code changes
- Future support for Vector DBs, Graph DBs, etc.
- Testable with mock implementations
- Clear contract for implementations

### 3. Pydantic Models for Validation

**Decision**: Use Pydantic for all model validation.

**Rationale**:
- Strong typing with runtime validation
- Automatic JSON serialization
- IDE autocompletion and type checking
- Clear data contracts

### 4. Event Emission for Lifecycle

**Decision**: Emit events for important operations.

**Rationale**:
- Loose coupling between components
- Enables observability and monitoring
- Other agents can react to memory changes
- Audit trail for compliance

### 5. Versioning for Accountability

**Decision**: Create version entries for all updates.

**Rationale**:
- Complete audit trail of changes
- Ability to restore previous states
- Track who made changes and when
- Understand evolution of records

### 6. FTS5 for Semantic Search

**Decision**: Use SQLite's FTS5 for full-text search.

**Rationale**:
- No external search service needed
- Good enough for most use cases
- Integrated with SQLite
- Can migrate to Elasticsearch later if needed

### 7. Relationship Tracking

**Decision**: Explicit relationship table for connecting records.

**Rationale**:
- Enables graph-like queries
- Find related records efficiently
- Support for different relationship types
- Optional bidirectional relationships

### 8. Async/Await Throughout

**Decision**: All operations are async.

**Rationale**:
- Non-blocking I/O for better scalability
- Consistent with asyncio-based system
- Better resource utilization
- Natural fit for SQLite's row_factory

## 📈 Scalability Considerations

### Current (Single Node)
- SQLite database on single machine
- Suitable for: Development, small deployments
- Limits: Device storage capacity

### Near-term (Replicated)
- Master-slave SQLite replication
- Suitable for: High availability needs
- Limits: Write bottleneck on master

### Future (Distributed)
- Partition by MemoryCategory or created_by
- Multiple SQLite nodes or distributed DB
- Suitable for: Very large-scale systems

## 🔐 Security Considerations

1. **Access Control** - Implement ACL layer above MemoryManager
2. **Encryption** - Add transparent encryption for sensitive records
3. **Audit Logging** - All operations logged for compliance
4. **Data Validation** - Pydantic models prevent injection attacks
5. **TTL Support** - Automatic cleanup of expired records

## 📊 Performance Optimization Strategies

### Indexing
- Strategic indexes on frequently queried fields
- Separate index for FTS searches
- Composite indexes for common filter combinations

### Query Optimization
- Paginated queries with LIMIT/OFFSET
- Lazy loading of relationships
- Query result caching for repeated searches

### Resource Management
- Connection pooling (via SQLite check_same_thread=False)
- Batch operations for bulk inserts
- Cleanup of expired records

### Monitoring
- Query performance metrics
- Index usage analysis
- Storage utilization tracking

## 🧪 Testing Strategy

### Unit Tests
- Individual CRUD operations
- Search and filter logic
- Relationship queries
- Version management

### Integration Tests
- Multi-step workflows
- Concurrent access patterns
- Cross-component interactions

### Performance Tests
- Benchmark common operations
- Load testing with many records
- Concurrent user simulation

## 📚 Related Components

### Integration with Tool Layer
- MemoryManager accessible via DI container
- Tools can store execution results in memory
- Enables tool result caching and pattern matching

### Integration with Event System
- Memory lifecycle events
- Coordination with other agents
- Observability and monitoring

### Integration with Logging
- Structured logging of all operations
- Correlation IDs for tracing
- Debug information for troubleshooting

## 🎓 Best Practices for Usage

1. **Use MemoryManager, not BaseMemoryStore** - Higher-level API is more convenient
2. **Tag important records** - Makes finding later easier
3. **Create relationships** - Connect related records for context
4. **Store lessons learned** - Include in completed task records
5. **Use descriptive titles** - Improves search effectiveness
6. **Set appropriate priority** - Helps with query ordering
7. **Clean up expired records** - Prevents unbounded growth
8. **Monitor statistics** - Track what memory system contains

## 🔮 Future Enhancements

### Phase 2: Semantic Memory
- Vector embeddings for similarity search
- LLM-powered summarization
- Automatic pattern extraction

### Phase 3: Distributed Memory
- Partition across multiple nodes
- Distributed consensus for consistency
- Cross-node replication

### Phase 4: Advanced Analytics
- Machine learning on execution history
- Anomaly detection
- Predictive performance modeling

### Phase 5: Memory Compression
- Automatic archival of old records
- Compression of large content fields
- Smart cleanup strategies

---

**Architecture Version**: 1.0
**Last Updated**: 2026-06-12
**Status**: ✅ Production Ready
