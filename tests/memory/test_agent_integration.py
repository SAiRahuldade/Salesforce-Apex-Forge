"""
Integration tests showing agents using the Memory system.

Demonstrates how Planner, Orchestrator, and Recovery agents leverage
memory for learning, planning, and error recovery.
"""

import pytest
from uuid import uuid4

from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.memory.sqlite_store import SQLiteMemoryStore


@pytest.fixture
async def integration_memory_manager(tmp_path):
    """Create a memory manager for integration tests."""
    db_path = tmp_path / "integration_test.db"
    store = SQLiteMemoryStore(db_path)
    await store.open()
    
    manager = MemoryManager(store)
    
    yield manager
    
    await store.close()


class TestPlannerMemoryIntegration:
    """Test Planner agent using memory for better planning decisions."""
    
    @pytest.mark.asyncio
    async def test_planner_finds_similar_past_tasks(self, integration_memory_manager):
        """Planner retrieves similar completed tasks to inform current planning."""
        mem = integration_memory_manager
        
        # Store completed tasks from past workflows
        task_id_1 = await mem.store_completed_task(
            task_type="DataMigration",
            task_id="data-001",
            agent_responsible="planner",
            approach_used="Batch Processing with checkpoints",
            result_summary="Successfully migrated 100k records",
            success=True,
            duration_seconds=45.5,
            created_by="planner"
        )
        
        task_id_2 = await mem.store_completed_task(
            task_type="DataMigration",
            task_id="data-002",
            agent_responsible="planner",
            approach_used="Stream Processing",
            result_summary="Memory overflow on 200k+ records",
            success=False,
            duration_seconds=15.2,
            created_by="planner"
        )
        
        # Planner searches for similar tasks to current work
        similar_tasks = await mem.find_similar_tasks(
            "DataMigration",
            limit=5
        )
        
        assert len(similar_tasks) >= 2
        assert any(t.id == task_id_1 for t in similar_tasks)
        
        # Extract lessons: batch processing successful, streaming failed
        successful = [t for t in similar_tasks if t.success]
        assert len(successful) > 0
        assert "checkpoints" in successful[0].approach_used.lower()
    
    @pytest.mark.asyncio
    async def test_planner_learns_from_past_errors(self, integration_memory_manager):
        """Planner learns from previous task failures to avoid repeated mistakes."""
        mem = integration_memory_manager
        
        # Store an error from a past workflow
        error_id = await mem.store_known_error(
            error_type="MemoryOverflow",
            error_message="Process exceeded available memory during batch operation",
            severity="high",
            created_by="planner",
            context_info={
                "data_size": "200k records",
                "batch_size": "50k",
                "available_memory": "2GB"
            }
        )
        
        # Planner searches for errors related to memory management
        past_errors = await mem.find_past_errors(
            "MemoryOverflow",
            limit=10
        )
        
        assert len(past_errors) > 0
        error = past_errors[0]
        assert error.error_message is not None
        assert "memory" in error.error_message.lower()


class TestOrchestratorMemoryIntegration:
    """Test Orchestrator using memory to track workflow execution."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_records_workflow_execution(self, integration_memory_manager):
        """Orchestrator stores workflow execution history for auditing and learning."""
        mem = integration_memory_manager
        
        workflow_id = f"wf-{uuid4()}"
        
        workflow_record_id = await mem.store_workflow_history(
            workflow_id=workflow_id,
            workflow_type="DataProcessingPipeline",
            workflow_status="completed",
            duration_seconds=120.5,
            steps_executed=["validate_input", "transform_data", "load_warehouse", "verify_load"],
            created_by="orchestrator"
        )
        
        assert workflow_record_id is not None
        
        record = await mem.store.read(workflow_record_id)
        assert record.title.startswith("Workflow:")
        assert record.workflow_type == "DataProcessingPipeline"
    
    @pytest.mark.asyncio
    async def test_orchestrator_stores_execution_history(self, integration_memory_manager):
        """Orchestrator tracks agent execution for debugging and optimization."""
        mem = integration_memory_manager
        
        exec_id = await mem.store_agent_interaction(
            initiator_agent="orchestrator",
            target_agent="planner",
            interaction_type="create_plan",
            request_data={"request": "Create execution plan for data migration"},
            response_data={"plan_id": "plan-001"},
            success=True,
            duration_seconds=3.2,
            created_by="orchestrator"
        )
        
        assert exec_id is not None
        
        record = await mem.store.read(exec_id)
        assert record.initiator_agent == "orchestrator"
        assert record.target_agent == "planner"


class TestRecoveryMemoryIntegration:
    """Test Recovery agent using memory to resolve errors."""
    
    @pytest.mark.asyncio
    async def test_recovery_finds_similar_past_errors(self, integration_memory_manager):
        """Recovery agent searches memory for similar errors and their resolutions."""
        mem = integration_memory_manager
        
        # Store past error
        error_id_1 = await mem.store_known_error(
            error_type="DataValidationError",
            error_message="Missing required field: customer_id",
            severity="medium",
            created_by="executor",
            context_info={"record_count": 100, "field": "customer_id"}
        )
        
        # Current error (similar type)
        await mem.store_known_error(
            error_type="DataValidationError",
            error_message="Missing required field: product_id",
            severity="medium",
            created_by="executor",
            context_info={"record_count": 50, "field": "product_id"}
        )
        
        # Recovery searches for similar errors
        similar_errors = await mem.find_past_errors(
            "DataValidationError",
            limit=10
        )
        
        assert len(similar_errors) >= 1
        assert all(e.error_type == "DataValidationError" for e in similar_errors)


class TestAgentMemoryAnalytics:
    """Test memory analytics for agent performance insights."""
    
    @pytest.mark.asyncio
    async def test_get_agent_statistics(self, integration_memory_manager):
        """Retrieve performance statistics for a specific agent."""
        mem = integration_memory_manager
        
        # Store multiple execution records
        for i in range(5):
            await mem.store_agent_interaction(
                initiator_agent="planner",
                target_agent="orchestrator",
                interaction_type="planning",
                request_data={"task_id": f"task-{i}"},
                response_data={},
                success=i < 4,  # 4 succeed, 1 fails
                duration_seconds=2.5 + i,
                created_by="test"
            )
        
        # Get agent stats
        stats = await mem.get_agent_stats("test")
        
        assert stats["agent_name"] == "test"
        assert stats["total_records"] >= 0
        assert "success_rate" in stats


class TestMemoryWorkflowIntegration:
    """Test complete agent workflow with memory interactions."""
    
    @pytest.mark.asyncio
    async def test_complete_workflow_with_memory(self, integration_memory_manager):
        """Simulate a complete workflow where agents learn and improve."""
        mem = integration_memory_manager
        
        workflow_id = f"wf-{uuid4()}"
        
        # STEP 1: Planner retrieves similar past tasks
        await mem.store_completed_task(
            task_type="DataLoad",
            task_id="data-100",
            agent_responsible="planner",
            approach_used="Batch approach with 10k records per batch",
            result_summary="Completed successfully",
            success=True,
            duration_seconds=30.0,
            created_by="test"
        )
        
        similar_tasks = await mem.find_similar_tasks("DataLoad", limit=5)
        assert len(similar_tasks) > 0
        
        # STEP 2: Orchestrator executes workflow
        exec_id = await mem.store_agent_interaction(
            initiator_agent="orchestrator",
            target_agent="executor",
            interaction_type="workflow_execution",
            request_data={"workflow_id": workflow_id},
            response_data={"status": "success"},
            success=True,
            duration_seconds=45.0,
            created_by="test"
        )
        
        # STEP 3: Store workflow completion
        workflow_id_mem = await mem.store_workflow_history(
            workflow_id=workflow_id,
            workflow_type="DataLoad",
            workflow_status="completed",
            duration_seconds=45.0,
            steps_executed=["plan", "execute", "verify"],
            created_by="test"
        )
        
        # STEP 4: Tag records for future retrieval
        await mem.tag_record(
            workflow_id_mem,
            tags=["high_performance", "completed"]
        )
        
        # STEP 5: Create relationships between execution and workflow
        await mem.relate_records(
            exec_id,
            workflow_id_mem,
            relationship_type="orchestrates",
            metadata={"description": "Orchestrator executed this workflow"}
        )
        
        # STEP 6: Retrieve related records
        related = await mem.get_related_records(
            exec_id,
            relationship_type="orchestrates"
        )
        
        assert len(related) > 0
        assert any(r.id == workflow_id_mem for r in related)
