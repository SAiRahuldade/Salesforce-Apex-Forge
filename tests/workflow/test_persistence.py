import pytest
import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from salesforce_ai_engineer.agent.models import ExecutionPlan
from salesforce_ai_engineer.workflow.models import WorkflowSnapshot, WorkflowRunStatus
from salesforce_ai_engineer.workflow.persistence import WorkflowPersistence

@pytest.mark.asyncio
async def test_persistence_fallback():
    persistence = WorkflowPersistence(memory_manager=None)
    
    workflow_id = str(uuid4())
    snapshot = WorkflowSnapshot(
        workflow_id=workflow_id,
        request="Test request",
        plan=ExecutionPlan(objective="Test", tasks=[]),
        status=WorkflowRunStatus.INITIALIZED
    )
    
    # Save snapshot
    await persistence.save_snapshot(snapshot)
    
    # Load snapshot
    loaded = await persistence.load_snapshot(workflow_id)
    assert loaded is not None
    assert loaded.workflow_id == workflow_id
    assert loaded.request == "Test request"
    assert loaded.status == WorkflowRunStatus.INITIALIZED
    
    # Load non-existent
    non_existent = await persistence.load_snapshot("does-not-exist")
    assert non_existent is None
    
    # Archive snapshot
    await persistence.archive_snapshot(workflow_id)
    archived_loaded = await persistence.load_snapshot(workflow_id)
    assert archived_loaded is None

@pytest.mark.asyncio
async def test_save_task_history_fallback():
    persistence = WorkflowPersistence(memory_manager=None)
    # Should safely no-op
    await persistence.save_task_history("wf", "req", trace=None, success=True)
