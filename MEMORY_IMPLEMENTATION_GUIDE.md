# Memory Agent - Implementation Guide

Step-by-step guide for implementing memory usage in agents.

## 📋 Quick Reference

| Task | Method | Example |
|------|--------|---------|
| Store task result | `store_completed_task()` | Record successful execution |
| Store error | `store_known_error()` | Catalog error for future ref |
| Find similar tasks | `find_similar_tasks()` | Reuse previous solutions |
| Find past fixes | `find_fixes_for_error()` | Apply known fixes |
| Store decision | `store_architecture_decision()` | ADR for future |
| Search memory | `search_memory()` | Query historical knowledge |
| Get agent stats | `get_agent_stats()` | Performance metrics |

## 🚀 Getting Started

### Step 1: Initialize Memory Manager

```python
from pathlib import Path
from salesforce_ai_engineer.memory import SQLiteMemoryStore, MemoryManager
from salesforce_ai_engineer.core.bootstrap import container

# Option A: Direct initialization
async def init_memory():
    store = SQLiteMemoryStore(Path("./memory/system.db"))
    await store.open()
    return MemoryManager(store)

# Option B: Via DI container (recommended)
memory_manager = container.resolve("memory_manager")
```

### Step 2: Inject into Agent

```python
class MyAgent:
    def __init__(self, memory: MemoryManager):
        self.memory = memory
    
    async def execute(self):
        # Use memory in your agent code
        pass
```

### Step 3: Register in DI Container

```python
# In bootstrap.py or configuration
container.register_factory(
    "memory_manager",
    lambda services: MemoryManager(
        store=services.resolve("memory_store")
    ),
    singleton=True
)
```

## 💾 Storing Information

### Pattern 1: Record Task Completion

```python
async def execute_task(self, task):
    start_time = time.time()
    
    try:
        result = await self.process_task(task)
        duration = time.time() - start_time
        
        # Store success
        record_id = await self.memory.store_completed_task(
            task_type=task.task_type,
            task_id=task.task_id,
            agent_responsible=self.name,
            approach_used=self.algorithm_name,
            result_summary=f"Processed {len(result)} items",
            success=True,
            duration_seconds=duration,
            created_by=self.name,
            lessons_learned=[
                "Parallelization helped",
                "Memory usage was high"
            ]
        )
        
        logger.info(f"Stored task record: {record_id}")
        return result
        
    except Exception as e:
        duration = time.time() - start_time
        
        # Store failure
        record_id = await self.memory.store_completed_task(
            task_type=task.task_type,
            task_id=task.task_id,
            agent_responsible=self.name,
            approach_used="unknown",
            result_summary=str(e),
            success=False,
            duration_seconds=duration,
            created_by=self.name
        )
        
        raise
```

### Pattern 2: Record Agent Execution

```python
async def run(self):
    execution_id = str(uuid4())
    
    await self.memory.store_execution_history(
        agent_name=self.name,
        task_description=f"Running {self.name}",
        success=True,
        duration_seconds=elapsed,
        created_by=self.name,
        execution_id=execution_id,
        input_data=self.config.to_dict(),
        output_data=results,
        resource_usage={
            "cpu_percent": cpu_usage,
            "memory_mb": memory_usage
        }
    )
```

### Pattern 3: Record Error

```python
async def handle_error(self, error: Exception):
    # Check if we know about this error
    past_errors = await self.memory.find_past_errors(type(error).__name__)
    
    # Store this error
    record_id = await self.memory.store_known_error(
        error_type=type(error).__name__,
        error_message=str(error),
        severity="high" if critical else "medium",
        created_by=self.name,
        reproduction_steps=self.get_error_context(),
        affected_components=["MyAgent", "DataProcessor"],
        workaround="Retry with exponential backoff"
    )
    
    logger.error(f"Stored error record: {record_id}")
```

### Pattern 4: Record Fix

```python
async def implement_fix_for_error(self, error_type: str, fix_description: str):
    # Find past errors of this type
    past_errors = await self.memory.find_past_errors(error_type)
    
    # Record the fix
    fix_id = await self.memory.store_successful_fix(
        error_type=error_type,
        error_description=f"{error_type} encountered during processing",
        fix_description=fix_description,
        fix_steps=[
            "Add exponential backoff",
            "Increase timeout",
            "Add retry logic"
        ],
        time_to_fix_minutes=30.0,
        who_fixed=self.name,
        created_by=self.name,
        prevention_strategy="Use circuit breaker pattern"
    )
    
    logger.info(f"Recorded fix: {fix_id}")
```

### Pattern 5: Record Workflow

```python
async def orchestrate_workflow(self):
    workflow_id = str(uuid4())
    start_time = datetime.utcnow()
    steps_executed = []
    
    try:
        # Step 1
        steps_executed.append("validate_input")
        await self.validate_input()
        
        # Step 2
        steps_executed.append("process_data")
        await self.process_data()
        
        # Step 3
        steps_executed.append("store_results")
        await self.store_results()
        
        # Record success
        await self.memory.store_workflow_history(
            workflow_id=workflow_id,
            workflow_type="DataPipeline",
            status="completed",
            duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
            steps_executed=steps_executed,
            created_by=self.name,
            outcomes={"records_processed": 1000, "errors": 0}
        )
        
    except Exception as e:
        # Record failure
        await self.memory.store_workflow_history(
            workflow_id=workflow_id,
            workflow_type="DataPipeline",
            status="failed",
            duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
            steps_executed=steps_executed,
            created_by=self.name,
            issues_encountered=[str(e)]
        )
        raise
```

## 🔍 Searching & Retrieving

### Pattern 1: Find Similar Past Tasks

```python
async def execute_task_with_past_knowledge(self, task):
    # Find similar tasks
    similar_tasks = await self.memory.find_similar_tasks(
        task_type=task.task_type,
        limit=5
    )
    
    # Learn from successes
    successful = [t for t in similar_tasks if t.success]
    
    if successful:
        logger.info(f"Found {len(successful)} successful similar tasks")
        
        # Use the best approach
        best_task = max(successful, key=lambda t: t.metadata.confidence)
        logger.info(f"Using approach: {best_task.approach_used}")
        
        return await self.apply_approach(best_task.approach_used, task)
    
    # Fall back to default approach
    return await self.execute_task(task)
```

### Pattern 2: Learn from Error History

```python
async def handle_error_with_memory(self, error: Exception):
    error_type = type(error).__name__
    
    # Check if we've seen this before
    past_errors = await self.memory.find_past_errors(error_type, limit=5)
    
    if past_errors:
        logger.info(f"Found {len(past_errors)} past occurrences of {error_type}")
        
        # Find fixes
        fixes = await self.memory.find_fixes_for_error(error_type)
        
        if fixes:
            # Apply the fastest fix
            fastest_fix = min(fixes, key=lambda f: f.time_to_fix_minutes)
            logger.info(f"Applying fix (took {fastest_fix.time_to_fix_minutes}min): {fastest_fix.fix_description}")
            
            return await self.apply_fix(fastest_fix)
    
    # No past knowledge, handle as new
    return await self.handle_new_error(error)
```

### Pattern 3: Search Memory

```python
async def search_knowledge_base(self, query: str):
    results = await self.memory.search_memory(
        keywords=query.split(),
        limit=10
    )
    
    for record in results:
        logger.info(f"Found: {record.title}")
        logger.info(f"  Category: {record.category}")
        logger.info(f"  Confidence: {record.metadata.confidence}")
        logger.info(f"  Description: {record.description}")
    
    return results
```

### Pattern 4: Get Agent Statistics

```python
async def report_performance(self):
    stats = await self.memory.get_agent_stats(self.name)
    
    logger.info(f"Agent: {stats['agent_name']}")
    logger.info(f"  Total records: {stats['total_records']}")
    logger.info(f"  Success rate: {stats['success_rate'] * 100:.1f}%")
    logger.info(f"  Total duration: {stats['total_duration_seconds']:.1f}s")
    logger.info(f"  Categories:")
    for category, count in stats['records_by_category'].items():
        logger.info(f"    - {category}: {count}")
```

## 🔗 Managing Relationships

### Pattern 1: Link Related Records

```python
async def relate_project_to_execution(self, project_id, execution_id):
    # Create bidirectional relationship
    rel_id = await self.memory.relate_records(
        source_id=project_id,
        target_id=execution_id,
        relationship_type="implemented_in",
        bidirectional=True,
        metadata={"implementation_date": datetime.utcnow().isoformat()}
    )
    
    logger.info(f"Created relationship: {rel_id}")
```

### Pattern 2: Find Related Knowledge

```python
async def get_related_knowledge(self, record_id):
    # Find directly related records
    direct_relations = await self.memory.get_related_records(
        record_id,
        depth=1
    )
    
    logger.info(f"Found {len(direct_relations)} directly related records")
    
    # Find transitively related records
    transitive_relations = await self.memory.get_related_records(
        record_id,
        depth=2
    )
    
    logger.info(f"Found {len(transitive_relations)} transitively related records")
    
    return {"direct": direct_relations, "transitive": transitive_relations}
```

## 🏷️ Using Tags

### Pattern 1: Tag Important Records

```python
async def tag_important_records(self):
    # Find critical errors
    critical_errors = await self.memory.search_memory(
        keywords=["critical", "system"],
        limit=100
    )
    
    for record in critical_errors:
        await self.memory.tag_record(record.id, ["critical", "reviewed"])
```

### Pattern 2: Find Tagged Records

```python
async def find_urgent_tasks(self):
    # Find all records tagged as urgent
    urgent = await self.memory.find_by_tags(
        ["urgent"],
        operator="or"
    )
    
    logger.info(f"Found {len(urgent)} urgent items")
    return urgent
```

## 📊 Analytics

### Pattern 1: System Health Check

```python
async def check_system_health(self):
    # Get system stats
    stats = await self.memory.get_system_stats()
    
    logger.info("System Memory Status:")
    logger.info(f"  Total records: {stats['total_records']}")
    logger.info(f"  Storage size: {stats.get('file_size_bytes', 0) / 1024 / 1024:.1f} MB")
    
    # Get category breakdown
    logger.info("  By category:")
    for category, count in stats['by_category'].items():
        logger.info(f"    - {category}: {count}")
    
    # Health check
    if await self.memory.health_check():
        logger.info("✓ Memory system healthy")
    else:
        logger.error("✗ Memory system unhealthy!")
```

### Pattern 2: Task Success Analysis

```python
async def analyze_task_performance(self, task_type: str):
    success_rate = await self.memory.get_task_success_rate(task_type)
    
    if success_rate > 0.95:
        logger.info(f"✓ {task_type}: Excellent ({success_rate * 100:.1f}%)")
    elif success_rate > 0.8:
        logger.warning(f"⚠ {task_type}: Good ({success_rate * 100:.1f}%)")
    else:
        logger.error(f"✗ {task_type}: Poor ({success_rate * 100:.1f}%)")
    
    return success_rate
```

## 🔐 Best Practices

### 1. Always Use Created_by

```python
# ✓ Good
await memory.store_completed_task(
    task_type="ProcessData",
    task_id="task-001",
    agent_responsible="DataAgent",
    approach_used="MapReduce",
    result_summary="Success",
    success=True,
    duration_seconds=10.0,
    created_by="DataAgent"  # Clear who created this
)

# ✗ Avoid
await memory.store_completed_task(
    ...,
    created_by="unknown"  # Unclear who created this
)
```

### 2. Include Descriptive Titles

```python
# ✓ Good
title="Task: DataProcessing - Customer Records - 2024-06-12"

# ✗ Avoid
title="Task"
```

### 3. Store Lessons Learned

```python
# ✓ Good
await memory.store_completed_task(
    ...,
    lessons_learned=[
        "Parallelization reduced time by 40%",
        "Memory usage was higher than expected"
    ]
)

# ✗ Avoid - empty lessons
lessons_learned=[]
```

### 4. Use Meaningful Metadata

```python
# ✓ Good
metadata=MemoryMetadata(
    source="DataAgent",
    confidence=0.95,  # This fix works 95% of the time
    relevance=0.8,    # Relevant to many scenarios
    priority=8        # Important
)

# ✗ Avoid - default metadata
metadata=MemoryMetadata(source="agent")
```

### 5. Tag for Organization

```python
# ✓ Good
await memory.tag_record(record_id, [
    "error",
    "timeout",
    "api",
    "external_service"
])

# ✗ Avoid - no tags
# No organization information
```

### 6. Clean Up Expired Records

```python
# Run periodically (e.g., daily)
async def maintenance_task():
    while True:
        cleared = await memory.cleanup_expired()
        logger.info(f"Cleaned {cleared} expired records")
        await asyncio.sleep(86400)  # Run daily
```

### 7. Create Relationships for Context

```python
# ✓ Good - Link related records
await memory.relate_records(
    source_id=project_id,
    target_id=execution_id,
    relationship_type="implemented_in"
)

# This enables future queries like:
# "What executions implemented this project?"
```

## 🧪 Testing Memory Usage

```python
@pytest.mark.asyncio
async def test_task_storage_and_retrieval():
    # Create memory manager
    memory = MemoryManager(store)
    
    # Store a task
    task_id = await memory.store_completed_task(
        task_type="TestTask",
        task_id="test-001",
        agent_responsible="TestAgent",
        approach_used="TestApproach",
        result_summary="Success",
        success=True,
        duration_seconds=1.0,
        created_by="TestAgent"
    )
    
    # Retrieve it
    record = await memory.get_record(task_id)
    assert record is not None
    assert record.title == "Task: TestTask"
    
    # Find similar
    similar = await memory.find_similar_tasks("TestTask")
    assert len(similar) > 0
    assert any(t.id == task_id for t in similar)
```

## 🔧 Common Troubleshooting

### Issue: "Record not found"

```python
# Check if record exists first
if await memory.store.exists(record_id):
    record = await memory.get_record(record_id)
else:
    logger.warning(f"Record {record_id} not found")
```

### Issue: Memory store not responding

```python
# Check health
if not await memory.health_check():
    logger.error("Memory store unhealthy!")
    # Attempt recovery
    await memory.store.close()
    await memory.store.open()
```

### Issue: Duplicate records

```python
# Generate unique IDs
from uuid import uuid4

record_id = f"task-{uuid4()}"  # Unique ID
```

### Issue: Search returning no results

```python
# Debug search
results = await memory.search_memory(
    keywords=["debug", "test"],
    limit=1000  # Get more results
)

logger.debug(f"Found {len(results)} results")
for r in results:
    logger.debug(f"  - {r.title} (confidence: {r.metadata.confidence})")
```

## 📚 Complete Agent Example

```python
class ExampleAgent:
    def __init__(self, memory: MemoryManager):
        self.memory = memory
        self.name = "ExampleAgent"
    
    async def execute(self, task):
        try:
            # Check past knowledge
            similar = await self.memory.find_similar_tasks(task.type)
            approach = self._choose_approach(similar)
            
            # Execute task
            start = time.time()
            result = await self._execute_with_approach(task, approach)
            duration = time.time() - start
            
            # Store success
            await self.memory.store_completed_task(
                task_type=task.type,
                task_id=task.id,
                agent_responsible=self.name,
                approach_used=approach,
                result_summary=f"Processed {len(result)} items",
                success=True,
                duration_seconds=duration,
                created_by=self.name,
                lessons_learned=self._extract_lessons(result)
            )
            
            return result
            
        except Exception as e:
            # Check error history
            fixes = await self.memory.find_fixes_for_error(type(e).__name__)
            
            if fixes:
                # Apply fix
                fix = fixes[0]
                await self._apply_fix(fix)
            
            # Store error
            await self.memory.store_known_error(
                error_type=type(e).__name__,
                error_message=str(e),
                severity="high",
                created_by=self.name
            )
            
            raise
    
    def _choose_approach(self, similar):
        # Use best successful approach
        successful = [t for t in similar if t.success]
        if successful:
            return max(
                successful,
                key=lambda t: t.metadata.confidence
            ).approach_used
        return "default"
    
    async def _execute_with_approach(self, task, approach):
        # Your implementation
        pass
    
    def _extract_lessons(self, result):
        # Extract learnings from result
        return []
    
    async def _apply_fix(self, fix):
        # Your implementation
        pass
```

---

**Implementation Guide Version**: 1.0
**Last Updated**: 2026-06-12
**Status**: ✅ Complete
