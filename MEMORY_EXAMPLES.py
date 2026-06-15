"""
Memory Agent - Practical Code Examples

10 complete, runnable examples demonstrating the Memory Agent system.
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from salesforce_ai_engineer.memory import SQLiteMemoryStore, MemoryManager
from salesforce_ai_engineer.models.domain.memory import (
    MemoryCategory,
    MemoryMetadata,
)


# ===== Example 1: Basic CRUD Operations =====

async def example_1_basic_crud():
    """
    Example 1: Basic Create, Read, Update, Delete operations.
    
    This example shows the fundamental operations for managing memory records.
    """
    print("\n" + "="*60)
    print("Example 1: Basic CRUD Operations")
    print("="*60)
    
    # Initialize memory store
    db_path = Path("./memory/example_1.db")
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    
    try:
        # Create
        print("\n1. Creating project memory record...")
        record_id = await manager.store_project_memory(
            title="AI Agent System Architecture",
            key_insights=[
                "Modular design enables easy extension",
                "Event-driven architecture for loose coupling"
            ],
            technical_stack=["Python", "SQLite", "asyncio"],
            created_by="ArchitectureTeam"
        )
        print(f"   ✓ Created record: {record_id}")
        
        # Read
        print("\n2. Reading record...")
        record = await manager.get_record(record_id)
        print(f"   ✓ Title: {record.title}")
        print(f"   ✓ Category: {record.category}")
        print(f"   ✓ Key insights: {record.key_insights}")
        
        # Update
        print("\n3. Updating record...")
        updated = await store.update(
            record_id,
            {"title": "AI Agent System - v2.0 Architecture"},
            change_description="Updated version number",
            created_by="ArchitectureTeam"
        )
        print(f"   ✓ Updated title: {updated.title}")
        
        # Delete (soft)
        print("\n4. Deleting record (soft delete)...")
        await store.delete(record_id, soft=True)
        print(f"   ✓ Record marked as deleted")
        
    finally:
        await store.close()


# ===== Example 2: Task Storage and Retrieval =====

async def example_2_task_storage():
    """
    Example 2: Store and retrieve task execution information.
    
    Shows how agents record their work and retrieve similar past tasks.
    """
    print("\n" + "="*60)
    print("Example 2: Task Storage and Retrieval")
    print("="*60)
    
    db_path = Path("./memory/example_2.db")
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    
    try:
        # Store several completed tasks
        print("\n1. Storing completed tasks...")
        task_ids = []
        
        tasks = [
            {
                "task_type": "DataProcessing",
                "task_id": "task-001",
                "approach": "MapReduce",
                "success": True,
                "duration": 120.0,
                "result": "Processed 1M records"
            },
            {
                "task_type": "DataProcessing",
                "task_id": "task-002",
                "approach": "Streaming",
                "success": True,
                "duration": 45.0,
                "result": "Processed 500K records"
            },
            {
                "task_type": "DataCleaning",
                "task_id": "task-003",
                "approach": "Regex matching",
                "success": True,
                "duration": 30.0,
                "result": "Cleaned 100K records"
            },
        ]
        
        for task in tasks:
            task_id = await manager.store_completed_task(
                task_type=task["task_type"],
                task_id=task["task_id"],
                agent_responsible="DataAgent",
                approach_used=task["approach"],
                result_summary=task["result"],
                success=task["success"],
                duration_seconds=task["duration"],
                created_by="DataAgent",
                lessons_learned=[
                    "Streaming is faster than MapReduce for small datasets",
                    "Regex was 2x faster than traditional parsing"
                ]
            )
            task_ids.append(task_id)
            print(f"   ✓ Stored {task['task_type']}: {task_id}")
        
        # Find similar tasks
        print("\n2. Finding similar tasks (DataProcessing)...")
        similar = await manager.find_similar_tasks("DataProcessing", limit=10)
        print(f"   ✓ Found {len(similar)} similar tasks")
        for task in similar:
            if task.success:
                print(f"      - Success: {task.approach_used} ({task.duration_seconds:.1f}s)")
        
        # Get success rate
        print("\n3. Calculating success rate...")
        success_rate = await manager.get_task_success_rate("DataProcessing")
        print(f"   ✓ DataProcessing success rate: {success_rate * 100:.1f}%")
        
    finally:
        await store.close()


# ===== Example 3: Error Management =====

async def example_3_error_management():
    """
    Example 3: Store errors and track successful fixes.
    
    Shows how to learn from failure and reuse fixes.
    """
    print("\n" + "="*60)
    print("Example 3: Error Management")
    print("="*60)
    
    db_path = Path("./memory/example_3.db")
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    
    try:
        # Store known errors
        print("\n1. Recording known errors...")
        error_ids = []
        
        errors = [
            {
                "type": "TimeoutError",
                "message": "API request exceeded 30 second timeout",
                "severity": "high"
            },
            {
                "type": "ConnectionRefused",
                "message": "Unable to connect to database",
                "severity": "critical"
            },
            {
                "type": "MemoryError",
                "message": "Out of memory processing large dataset",
                "severity": "high"
            },
        ]
        
        for error in errors:
            error_id = await manager.store_known_error(
                error_type=error["type"],
                error_message=error["message"],
                severity=error["severity"],
                created_by="ErrorMonitor",
                reproduction_steps=["Try to run", "Wait", "See error"],
                affected_components=["APIClient", "DataProcessor"]
            )
            error_ids.append(error_id)
            print(f"   ✓ Recorded {error['type']}: {error_id}")
        
        # Store successful fixes
        print("\n2. Recording successful fixes...")
        fix_ids = []
        
        fixes = [
            {
                "error_type": "TimeoutError",
                "description": "Increased timeout to 60 seconds + exponential backoff",
                "time_to_fix": 30.0
            },
            {
                "error_type": "ConnectionRefused",
                "description": "Added connection retry logic with circuit breaker",
                "time_to_fix": 120.0
            },
        ]
        
        for fix in fixes:
            fix_id = await manager.store_successful_fix(
                error_type=fix["error_type"],
                error_description=f"Handling {fix['error_type']}",
                fix_description=fix["description"],
                fix_steps=["Update config", "Add retry logic", "Test"],
                time_to_fix_minutes=fix["time_to_fix"],
                who_fixed="EngineerA",
                created_by="EngineerA"
            )
            fix_ids.append(fix_id)
            print(f"   ✓ Recorded fix for {fix['error_type']}: {fix_id}")
        
        # Find fixes for error
        print("\n3. Finding fixes for TimeoutError...")
        fixes = await manager.find_fixes_for_error("TimeoutError")
        if fixes:
            print(f"   ✓ Found {len(fixes)} fixes")
            for fix in fixes:
                print(f"      - {fix.fix_description}")
                print(f"      - Time to fix: {fix.time_to_fix_minutes} minutes")
        
    finally:
        await store.close()


# ===== Example 4: Search and Filtering =====

async def example_4_search_and_filtering():
    """
    Example 4: Search memory records with keywords and filters.
    
    Shows advanced search capabilities.
    """
    print("\n" + "="*60)
    print("Example 4: Search and Filtering")
    print("="*60)
    
    db_path = Path("./memory/example_4.db")
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    
    try:
        # Create records with diverse content
        print("\n1. Creating test records...")
        
        await manager.store_completed_task(
            task_type="DataProcessing",
            task_id="task-001",
            agent_responsible="Agent1",
            approach_used="Parallel processing",
            result_summary="Optimized performance using parallelization",
            success=True,
            duration_seconds=50.0,
            created_by="Agent1"
        )
        
        await manager.store_completed_task(
            task_type="DataAnalysis",
            task_id="task-002",
            agent_responsible="Agent2",
            approach_used="Statistical analysis",
            result_summary="Performance metrics collected successfully",
            success=True,
            duration_seconds=30.0,
            created_by="Agent2"
        )
        
        print("   ✓ Created test records")
        
        # Search by keywords
        print("\n2. Searching by keywords...")
        results = await manager.search_memory(
            keywords=["performance"],
            limit=10
        )
        print(f"   ✓ Found {len(results)} records with 'performance'")
        for r in results:
            print(f"      - {r.title}")
        
        # Search by category
        print("\n3. Searching by category...")
        results = await manager.search_memory(
            category=MemoryCategory.COMPLETED_TASK,
            limit=10
        )
        print(f"   ✓ Found {len(results)} completed tasks")
        
        # Search by creator
        print("\n4. Searching by creator...")
        results = await manager.search_memory(
            created_by="Agent1",
            limit=10
        )
        print(f"   ✓ Found {len(results)} records by Agent1")
        
    finally:
        await store.close()


# ===== Example 5: Versioning and History =====

async def example_5_versioning():
    """
    Example 5: Track versions and restore previous states.
    
    Shows the audit trail and recovery capabilities.
    """
    print("\n" + "="*60)
    print("Example 5: Versioning and History")
    print("="*60)
    
    db_path = Path("./memory/example_5.db")
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    
    try:
        # Create initial record
        print("\n1. Creating initial record...")
        record_id = await manager.store_project_memory(
            title="Project v1.0",
            key_insights=["Insight 1"],
            technical_stack=["Python"],
            created_by="Team"
        )
        print(f"   ✓ Created: {record_id}")
        
        # Make updates
        print("\n2. Making updates...")
        for i in range(2, 5):
            await store.update(
                record_id,
                {"title": f"Project v{i}.0"},
                change_description=f"Updated to version {i}.0",
                created_by="Team"
            )
            print(f"   ✓ Updated to v{i}.0")
        
        # Get history
        print("\n3. Viewing version history...")
        versions = await manager.get_record_history(record_id)
        print(f"   ✓ Total versions: {len(versions)}")
        for version in versions[:3]:
            print(f"      - Version {version.version_number}: {version.change_description}")
        
        # Restore to previous version
        print("\n4. Restoring to version 2...")
        restored = await manager.restore_record(record_id, version_number=2)
        print(f"   ✓ Restored to: {restored.title}")
        
    finally:
        await store.close()


# ===== Example 6: Tagging and Organization =====

async def example_6_tagging():
    """
    Example 6: Tag records for organization and discovery.
    
    Shows tag-based organization.
    """
    print("\n" + "="*60)
    print("Example 6: Tagging and Organization")
    print("="*60)
    
    db_path = Path("./memory/example_6.db")
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    
    try:
        # Create records
        print("\n1. Creating records...")
        id1 = await manager.store_known_error(
            error_type="CriticalError",
            error_message="System crash",
            severity="critical",
            created_by="Monitor"
        )
        
        id2 = await manager.store_known_error(
            error_type="WarningError",
            error_message="Non-critical issue",
            severity="low",
            created_by="Monitor"
        )
        print("   ✓ Created 2 error records")
        
        # Add tags
        print("\n2. Adding tags...")
        await manager.tag_record(id1, ["critical", "system", "urgent"])
        await manager.tag_record(id2, ["warning", "monitoring"])
        print("   ✓ Tagged records")
        
        # Find by tags
        print("\n3. Finding critical records...")
        critical = await manager.find_by_tags(["critical"])
        print(f"   ✓ Found {len(critical)} critical records")
        
        # List all tags
        print("\n4. Listing all tags...")
        all_tags = await store.list_all_tags()
        print(f"   ✓ All tags: {', '.join(all_tags)}")
        
    finally:
        await store.close()


# ===== Example 7: Relationships =====

async def example_7_relationships():
    """
    Example 7: Create relationships between records.
    
    Shows how to link related records.
    """
    print("\n" + "="*60)
    print("Example 7: Record Relationships")
    print("="*60)
    
    db_path = Path("./memory/example_7.db")
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    
    try:
        # Create records
        print("\n1. Creating related records...")
        project_id = await manager.store_project_memory(
            title="AI System",
            key_insights=[],
            technical_stack=[],
            created_by="Team"
        )
        
        execution_id = await manager.store_execution_history(
            agent_name="Agent1",
            task_description="Implement system",
            success=True,
            duration_seconds=10.0,
            created_by="Agent1"
        )
        print("   ✓ Created project and execution records")
        
        # Create relationship
        print("\n2. Creating relationship...")
        rel_id = await manager.relate_records(
            source_id=project_id,
            target_id=execution_id,
            relationship_type="implemented_in",
            bidirectional=True
        )
        print(f"   ✓ Created relationship: {rel_id}")
        
        # Find related
        print("\n3. Finding related records...")
        related = await manager.get_related_records(project_id, depth=1)
        print(f"   ✓ Found {len(related)} related records")
        for r in related:
            print(f"      - {r.title}")
        
    finally:
        await store.close()


# ===== Example 8: Analytics =====

async def example_8_analytics():
    """
    Example 8: Get statistics and analytics about memory.
    
    Shows analytics capabilities.
    """
    print("\n" + "="*60)
    print("Example 8: Analytics and Statistics")
    print("="*60)
    
    db_path = Path("./memory/example_8.db")
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    
    try:
        # Create varied records
        print("\n1. Creating test data...")
        for i in range(5):
            await manager.store_execution_history(
                agent_name="Agent1",
                task_description=f"Task {i}",
                success=i % 2 == 0,
                duration_seconds=float(i * 10),
                created_by="Agent1"
            )
        
        print("   ✓ Created test records")
        
        # Get agent stats
        print("\n2. Agent statistics...")
        stats = await manager.get_agent_stats("Agent1")
        print(f"   ✓ Agent: {stats['agent_name']}")
        print(f"   ✓ Total records: {stats['total_records']}")
        print(f"   ✓ Success rate: {stats['success_rate'] * 100:.1f}%")
        print(f"   ✓ Total duration: {stats['total_duration_seconds']:.1f}s")
        
        # Get system stats
        print("\n3. System statistics...")
        sys_stats = await manager.get_system_stats()
        print(f"   ✓ Total records: {sys_stats['total_records']}")
        print(f"   ✓ Storage size: {sys_stats.get('file_size_bytes', 0) / 1024:.1f} KB")
        
    finally:
        await store.close()


# ===== Example 9: Workflow Execution =====

async def example_9_workflow():
    """
    Example 9: Record complete workflow execution.
    
    Shows how to track multi-step workflows.
    """
    print("\n" + "="*60)
    print("Example 9: Workflow Execution")
    print("="*60)
    
    db_path = Path("./memory/example_9.db")
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    
    try:
        print("\n1. Recording workflow execution...")
        workflow_id = "wf-001"
        steps = []
        outcomes = {}
        
        # Simulate workflow steps
        print("   - Step 1: Validating input...")
        steps.append("validate_input")
        outcomes["validation"] = "passed"
        await asyncio.sleep(0.1)
        
        print("   - Step 2: Processing data...")
        steps.append("process_data")
        outcomes["records_processed"] = 1000
        await asyncio.sleep(0.1)
        
        print("   - Step 3: Storing results...")
        steps.append("store_results")
        outcomes["records_stored"] = 1000
        await asyncio.sleep(0.1)
        
        # Record workflow
        print("\n2. Storing workflow history...")
        wf_id = await manager.store_workflow_history(
            workflow_id=workflow_id,
            workflow_type="DataPipeline",
            status="completed",
            duration_seconds=0.3,
            steps_executed=steps,
            created_by="Orchestrator",
            outcomes=outcomes
        )
        print(f"   ✓ Recorded workflow: {wf_id}")
        
        # Retrieve it
        print("\n3. Retrieving workflow record...")
        record = await manager.get_record(wf_id)
        print(f"   ✓ Workflow: {record.title}")
        print(f"   ✓ Status: {record.status}")
        print(f"   ✓ Steps: {record.steps_executed}")
        print(f"   ✓ Outcomes: {record.outcomes}")
        
    finally:
        await store.close()


# ===== Example 10: Decision Recording (ADRs) =====

async def example_10_decisions():
    """
    Example 10: Record architecture decisions (ADRs).
    
    Shows how to document important decisions.
    """
    print("\n" + "="*60)
    print("Example 10: Architecture Decision Records (ADRs)")
    print("="*60)
    
    db_path = Path("./memory/example_10.db")
    store = SQLiteMemoryStore(db_path)
    await store.open()
    manager = MemoryManager(store)
    
    try:
        # Record decisions
        print("\n1. Recording architecture decisions...")
        
        decisions = [
            {
                "id": "ADR-001",
                "context": "Need persistent knowledge storage",
                "decision": "Use SQLite with versioning",
                "rationale": "No external dependencies, ACID compliance"
            },
            {
                "id": "ADR-002",
                "context": "Need async I/O for scalability",
                "decision": "Use asyncio throughout",
                "rationale": "Non-blocking I/O, better resource utilization"
            },
        ]
        
        for decision in decisions:
            adr_id = await manager.store_architecture_decision(
                decision_id=decision["id"],
                status="accepted",
                context=decision["context"],
                decision=decision["decision"],
                rationale=decision["rationale"],
                created_by="ArchitectureTeam",
                consequences=[
                    "Single-node coupling",
                    "Easier initial deployment"
                ],
                alternatives_considered=["PostgreSQL", "Redis"]
            )
            print(f"   ✓ Recorded {decision['id']}")
        
        print("\n2. Retrieving decisions...")
        decisions_records = await manager.search_memory(
            category=MemoryCategory.ARCHITECTURE_DECISION,
            limit=10
        )
        print(f"   ✓ Found {len(decisions_records)} decisions")
        for decision in decisions_records:
            print(f"      - {decision.title}")
            print(f"        Decision: {decision.decision}")
            print(f"        Rationale: {decision.rationale}")
        
    finally:
        await store.close()


# ===== Main =====

async def main():
    """Run all examples."""
    examples = [
        ("Basic CRUD", example_1_basic_crud),
        ("Task Storage", example_2_task_storage),
        ("Error Management", example_3_error_management),
        ("Search & Filtering", example_4_search_and_filtering),
        ("Versioning", example_5_versioning),
        ("Tagging", example_6_tagging),
        ("Relationships", example_7_relationships),
        ("Analytics", example_8_analytics),
        ("Workflows", example_9_workflow),
        ("Decisions", example_10_decisions),
    ]
    
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "Memory Agent - 10 Practical Examples".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    
    for i, (name, example_func) in enumerate(examples, 1):
        print(f"\n[{i}/10] Running: {name}")
        try:
            await example_func()
            print(f"✓ {name} completed successfully")
        except Exception as e:
            print(f"✗ {name} failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("All examples completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
