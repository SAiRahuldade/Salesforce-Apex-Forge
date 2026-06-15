"""Performance and load testing for the Salesforce AI Engineer platform.

This test suite validates system performance under various load conditions,
including concurrent workflows, memory usage, and response times.
"""

import pytest
import asyncio
import time
import statistics
from uuid import uuid4
from datetime import UTC, datetime
from pytest_asyncio import fixture

from salesforce_ai_engineer.agent.models import (
    ExecutionPlan,
    ExecutionTask,
    TaskStatus,
    WorkflowStatus,
    SalesforceWorkType,
)
from salesforce_ai_engineer.workflow import WorkflowExecutionEngine
from salesforce_ai_engineer.agent.registry import AgentRegistry
from salesforce_ai_engineer.agent.recovery import RuleBasedRecoveryAgent
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.core.state import StateManager
from salesforce_ai_engineer.memory import MemoryManager, SQLiteMemoryStore
from pathlib import Path
import tempfile


class FastMockAgent:
    """Fast mock agent for performance testing."""

    async def execute(self, task):
        from salesforce_ai_engineer.agent.models import TaskResult
        # Simulate minimal work
        await asyncio.sleep(0.001)
        return TaskResult(task_id=task.id, success=True, output={"result": "ok"})


@fixture
async def performance_container():
    """Create a minimal container for performance testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Memory
        db_path = Path(tmpdir) / "perf_memory.db"
        memory_store = SQLiteMemoryStore(db_path)
        await memory_store.open()
        memory_manager = MemoryManager(
            store=memory_store,
            event_bus=EventBus(),
        )

        # State
        state_path = Path(tmpdir) / "perf_state.json"
        state_manager = StateManager(state_path)

        # Agent Registry
        agent_registry = AgentRegistry()
        agent_registry.register("fast", FastMockAgent())

        # Recovery
        recovery_agent = RuleBasedRecoveryAgent()

        # Event Bus
        event_bus = EventBus()

        # Workflow Engine
        workflow_engine = WorkflowExecutionEngine(
            agent_registry=agent_registry,
            recovery_agent=recovery_agent,
            event_bus=event_bus,
            memory_manager=memory_manager,
            state_manager=state_manager,
        )

        yield {
            "workflow_engine": workflow_engine,
            "memory_manager": memory_manager,
            "state_manager": state_manager,
        }

        # Cleanup
        await memory_store.close()


@pytest.mark.asyncio
async def test_single_workflow_performance(performance_container):
    """Test baseline performance of a single workflow."""
    workflow_engine = performance_container["workflow_engine"]

    plan = ExecutionPlan(
        objective="Performance test",
        tasks=[
            ExecutionTask(
                title=f"Task {i}",
                description=f"Task {i}",
                agent="fast",
                input={},
            )
            for i in range(5)
        ],
    )

    start_time = time.time()
    result = await workflow_engine.execute_plan(plan, request="Performance test")
    duration = time.time() - start_time

    assert result.status == WorkflowStatus.SUCCESS
    assert duration < 3.0  # Should complete in reasonable time


@pytest.mark.asyncio
async def test_concurrent_workflows(performance_container):
    """Test performance with multiple concurrent workflows."""
    workflow_engine = performance_container["workflow_engine"]

    async def execute_workflow(workflow_id):
        plan = ExecutionPlan(
            objective=f"Concurrent test {workflow_id}",
            tasks=[
                ExecutionTask(
                    title=f"Task {workflow_id}-{i}",
                    description=f"Task {i}",
                    agent="fast",
                    input={},
                )
                for i in range(3)
            ],
        )
        return await workflow_engine.execute_plan(plan, request=f"Test {workflow_id}")

    # Execute 10 workflows concurrently
    num_workflows = 10
    start_time = time.time()

    results = await asyncio.gather(
        *[execute_workflow(str(i)) for i in range(num_workflows)]
    )

    duration = time.time() - start_time

    # Verify all succeeded
    assert all(r.status == WorkflowStatus.SUCCESS for r in results)
    assert len(results) == num_workflows

    # Should complete in reasonable time (concurrent execution)
    assert duration < 15.0


@pytest.mark.asyncio
async def test_high_volume_task_execution(performance_container):
    """Test performance with a workflow containing many tasks."""
    workflow_engine = performance_container["workflow_engine"]

    # Create workflow with 50 tasks
    plan = ExecutionPlan(
        objective="High volume test",
        tasks=[
            ExecutionTask(
                title=f"Task {i}",
                description=f"Task {i}",
                agent="fast",
                input={},
            )
            for i in range(50)
        ],
    )

    start_time = time.time()
    result = await workflow_engine.execute_plan(plan, request="High volume test")
    duration = time.time() - start_time

    assert result.status == WorkflowStatus.SUCCESS
    assert result.successful_tasks == 50
    assert duration < 30.0  # Should handle 50 tasks efficiently


@pytest.mark.asyncio
async def test_memory_usage_under_load(performance_container):
    """Test memory usage during high load."""
    import psutil
    import os

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    workflow_engine = performance_container["workflow_engine"]
    memory_manager = performance_container["memory_manager"]

    # Execute multiple workflows
    for i in range(20):
        plan = ExecutionPlan(
            objective=f"Memory test {i}",
            tasks=[
                ExecutionTask(
                    title=f"Task {i}",
                    description=f"Task {i}",
                    agent="fast",
                    input={"data": "x" * 1000},  # 1KB per task
                )
            ],
        )
        await workflow_engine.execute_plan(plan, request=f"Memory test {i}")

    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_increase = final_memory - initial_memory

    # Memory increase should be reasonable (< 100MB for 20 workflows)
    assert memory_increase < 100

    # Verify memory manager stats
    stats = await memory_manager.get_system_stats()
    assert stats["total_records"] >= 20


@pytest.mark.asyncio
async def test_response_time_distribution(performance_container):
    """Test distribution of response times across multiple executions."""
    workflow_engine = performance_container["workflow_engine"]

    response_times = []

    for i in range(30):
        plan = ExecutionPlan(
            objective=f"Response time test {i}",
            tasks=[
                ExecutionTask(
                    title=f"Task {i}",
                    description=f"Task {i}",
                    agent="fast",
                    input={},
                )
            ],
        )

        start_time = time.time()
        result = await workflow_engine.execute_plan(plan, request=f"Test {i}")
        duration = time.time() - start_time

        assert result.status == WorkflowStatus.SUCCESS
        response_times.append(duration)

    # Analyze response times
    avg_time = statistics.mean(response_times)
    median_time = statistics.median(response_times)
    p95_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
    max_time = max(response_times)

    # Performance assertions
    assert avg_time < 0.5  # Average should be fast
    assert median_time < 0.5
    assert p95_time < 1.0  # 95th percentile should be under 1 second
    assert max_time < 2.0  # No execution should take more than 2 seconds


@pytest.mark.asyncio
async def test_parallel_task_scaling(performance_container):
    """Test how performance scales with parallel task count."""
    workflow_engine = performance_container["workflow_engine"]

    results = {}

    for parallel_count in [1, 2, 4, 8]:
        from salesforce_ai_engineer.workflow.models import WorkflowExecutionPolicy

        policy = WorkflowExecutionPolicy(max_parallel_tasks=parallel_count)
        workflow_engine.default_policy = policy

        plan = ExecutionPlan(
            objective=f"Parallel scaling test {parallel_count}",
            tasks=[
                ExecutionTask(
                    title=f"Task {i}",
                    description=f"Task {i}",
                    agent="fast",
                    input={},
                )
                for i in range(16)  # 16 tasks total
            ],
        )

        start_time = time.time()
        result = await workflow_engine.execute_plan(plan, request=f"Parallel {parallel_count}")
        duration = time.time() - start_time

        assert result.status == WorkflowStatus.SUCCESS
        results[parallel_count] = duration

    # Verify that increasing parallelism improves performance
    # (with diminishing returns)
    assert results[8] < results[4] < results[2] < results[1]


@pytest.mark.asyncio
async def test_checkpoint_performance(performance_container):
    """Test performance impact of workflow checkpointing."""
    workflow_engine = performance_container["workflow_engine"]

    plan = ExecutionPlan(
        objective="Checkpoint performance test",
        tasks=[
            ExecutionTask(
                title=f"Task {i}",
                description=f"Task {i}",
                agent="fast",
                input={"data": "x" * 500},
            )
            for i in range(20)
        ],
    )

    workflow_id = str(uuid4())

    # Execute with checkpointing
    start_time = time.time()
    result1 = await workflow_engine.execute_plan(
        plan, request="Checkpoint test", workflow_id=workflow_id
    )
    duration_with_checkpoint = time.time() - start_time

    # Resume from checkpoint
    start_time = time.time()
    result2 = await workflow_engine.resume(workflow_id)
    duration_resume = time.time() - start_time

    assert result1.status == WorkflowStatus.SUCCESS
    assert result2.status == WorkflowStatus.SUCCESS

    # Checkpointing overhead should be minimal
    assert duration_with_checkpoint < 5.0
    # Resume should be fast
    assert duration_resume < 1.0


@pytest.mark.asyncio
async def test_event_bus_performance(performance_container):
    """Test event bus performance under high event load."""
    event_bus = EventBus()
    event_count = 0

    async def event_handler(event):
        nonlocal event_count
        event_count += 1

    # Subscribe to multiple event types
    await event_bus.subscribe("workflow.*", event_handler)
    await event_bus.subscribe("task.*", event_handler)
    await event_bus.subscribe("agent.*", event_handler)

    # Publish many events
    start_time = time.time()
    for i in range(1000):
        await event_bus.publish(f"workflow.event_{i}", {"index": i}, workflow_id=str(i))

    duration = time.time() - start_time

    # Should handle 1000 events quickly
    assert duration < 3.0
    assert event_count == 1000


@pytest.mark.asyncio
async def test_memory_search_performance(performance_container):
    """Test memory search performance with many records."""
    memory_manager = performance_container["memory_manager"]

    # Insert many records
    for i in range(100):
        await memory_manager.store_project_memory(
            title=f"Project {i}",
            key_insights=[f"Insight {i}"],
            technical_stack=["Python"],
            created_by="test",
        )

    # Test search performance
    start_time = time.time()
    results = await memory_manager.search_memory(keywords=["Project"], limit=100)
    duration = time.time() - start_time

    assert len(results) == 100
    assert duration < 0.5  # Search should be fast


@pytest.mark.asyncio
async def test_tool_executor_performance(performance_container):
    """Test tool executor performance under load."""
    from salesforce_ai_engineer.tools.executor import ToolExecutor
    from salesforce_ai_engineer.tools.registry import ToolRegistry
    from salesforce_ai_engineer.tools.structured_data import JSONTool
    from salesforce_ai_engineer.models.domain import ToolRequest

    tool_registry = ToolRegistry()
    tool_registry.register(JSONTool())
    tool_executor = ToolExecutor(tool_registry, EventBus())

    # Execute many tool calls
    start_time = time.time()
    for i in range(100):
        request = ToolRequest(
            workflow_id=str(i),
            tool_name="json",
            input={"operation": "parse", "content": '{"key": "value"}'},
        )
        response = await tool_executor.execute(request)
        assert response.status.value == "success"

    duration = time.time() - start_time

    # Should handle 100 tool calls quickly
    assert duration < 2.0


@pytest.mark.asyncio
async def test_stress_test(performance_container):
    """Comprehensive stress test combining multiple load factors."""
    workflow_engine = performance_container["workflow_engine"]

    async def stress_workflow(workflow_id):
        plan = ExecutionPlan(
            objective=f"Stress test {workflow_id}",
            tasks=[
                ExecutionTask(
                    title=f"Task {workflow_id}-{i}",
                    description=f"Task {i}",
                    agent="fast",
                    input={"data": "x" * 1000},
                )
                for i in range(10)
            ],
        )
        return await workflow_engine.execute_plan(plan, request=f"Stress {workflow_id}")

    # Run 50 concurrent workflows with 10 tasks each
    start_time = time.time()
    results = await asyncio.gather(
        *[stress_workflow(str(i)) for i in range(50)]
    )
    duration = time.time() - start_time

    # Verify all succeeded
    assert all(r.status == WorkflowStatus.SUCCESS for r in results)
    assert len(results) == 50

    # Should complete in reasonable time
    assert duration < 30.0

    # Verify system is still responsive
    quick_test = ExecutionPlan(
        objective="Quick responsiveness test",
        tasks=[
            ExecutionTask(
                title="Quick Task",
                description="Quick",
                agent="fast",
                input={},
            )
        ],
    )
    quick_start = time.time()
    quick_result = await workflow_engine.execute_plan(quick_test, request="Quick")
    quick_duration = time.time() - quick_start

    assert quick_result.status == WorkflowStatus.SUCCESS
    assert quick_duration < 3.0  # System should still be responsive


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
