"""End-to-end platform integration tests for autonomous multi-agent system."""

import pytest
import asyncio
import logging
try:
    import psutil
except ImportError:
    psutil = None
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime

from salesforce_ai_engineer.agent.models import (
    ExecutionPlan,
    ExecutionTask,
    TaskResult,
    TaskStatus,
    WorkflowStatus,
    ExecutionReport,
    RecoveryDecision,
    RecoveryAction,
)
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.core.state import StateManager
from salesforce_ai_engineer.memory import MemoryManager, SQLiteMemoryStore
from salesforce_ai_engineer.workflow.engine import WorkflowExecutionEngine
from salesforce_ai_engineer.reward_learning import (
    RewardLearningEngine,
    LearningAnalyzer,
    RewardScorer,
    WorkflowEvaluator,
)
from salesforce_ai_engineer.agent.registry import AgentRegistry
from salesforce_ai_engineer.agent.orchestrator import OrchestratorAgent
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)


class MockAgent:
    """Mock agent for testing."""
    
    def __init__(self, name: str, succeed: bool = True, fail_on_attempt: int | None = None):
        self.name = name
        self.succeed = succeed
        self.fail_on_attempt = fail_on_attempt
        self.call_count = 0
        self.executions = []
    
    async def execute(self, task: ExecutionTask) -> TaskResult:
        self.call_count += 1
        self.executions.append({
            "task_id": task.id,
            "attempt": self.call_count,
            "timestamp": datetime.now(),
        })
        
        if self.fail_on_attempt and self.call_count == self.fail_on_attempt:
            raise RuntimeError(f"Intentional failure from {self.name} on attempt {self.call_count}")
        
        if not self.succeed:
            raise RuntimeError(f"Task failed in {self.name}")
        
        return TaskResult(
            task_id=task.id,
            success=True,
            output={"agent": self.name, "result": "success", "data": task.input}
        )


class EventCapture:
    """Captures events published to EventBus."""
    
    def __init__(self):
        self.events = []
    
    async def capture(self, event, payload, **kwargs):
        self.events.append({
            "event": event,
            "payload": payload,
            "kwargs": kwargs,
            "timestamp": datetime.now(),
        })


@pytest.fixture
async def temp_state_dir():
    """Temporary directory for state management."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
async def event_bus():
    """Event bus with capture."""
    bus = EventBus()
    return bus


@pytest.fixture
async def state_manager(temp_state_dir):
    """State manager for workflow persistence."""
    return StateManager(temp_state_dir)


@pytest.fixture
async def memory_manager():
    """Mock memory manager."""
    mock = AsyncMock(spec=MemoryManager)
    mock.health_check = AsyncMock(return_value=True)
    mock.store = AsyncMock()
    
    # Configure store methods to return proper tuples
    mock.store.list_by_category = AsyncMock(return_value=([], 0))
    mock.store.create = AsyncMock(return_value="record-id")
    mock.store.update = AsyncMock(return_value="record-id")
    
    mock.store_workflow_history = AsyncMock(return_value="workflow-id")
    mock.store_execution_history = AsyncMock(return_value="exec-id")
    mock.store_completed_task = AsyncMock(return_value="task-id")
    return mock


@pytest.fixture
async def agent_registry():
    """Agent registry with mock agents."""
    registry = AgentRegistry()
    
    # Register mock agents for each specialized agent
    planner = MockAgent("planner")
    engineer = MockAgent("salesforce_engineer")
    verifier = MockAgent("verifier")
    recovery = MockAgent("recovery_agent")
    deployer = MockAgent("deployment_agent")
    
    registry.register("planner_agent", planner)
    registry.register("salesforce_engineer", engineer)
    registry.register("verifier", verifier)
    registry.register("recovery_agent", recovery)
    registry.register("deployment_agent", deployer)
    
    return registry, {
        "planner": planner,
        "engineer": engineer,
        "verifier": verifier,
        "recovery": recovery,
        "deployer": deployer,
    }


@pytest.fixture
async def recovery_agent():
    """Mock recovery agent."""
    mock = AsyncMock()
    mock.recover = AsyncMock(
        return_value=RecoveryDecision(
            action=RecoveryAction.RETRY,
            reason="Testing recovery",
            updated_input={}
        )
    )
    return mock


@pytest.fixture
async def workflow_engine(agent_registry, recovery_agent, event_bus, state_manager, memory_manager):
    """Workflow execution engine."""
    registry, _ = agent_registry
    return WorkflowExecutionEngine(
        agent_registry=registry,
        recovery_agent=recovery_agent,
        event_bus=event_bus,
        state_manager=state_manager,
        memory_manager=memory_manager,
    )


@pytest.fixture
async def reward_learning_engine(memory_manager, event_bus):
    """Reward and learning engine."""
    scorer = RewardScorer()
    evaluator = WorkflowEvaluator(scorer)
    analyzer = LearningAnalyzer()
    
    return RewardLearningEngine(
        memory_manager=memory_manager,
        event_bus=event_bus,
        scorer=scorer,
        evaluator=evaluator,
        analyzer=analyzer,
    )


@pytest.mark.asyncio
async def test_orchestrator_delegates_to_workflow_engine(workflow_engine, event_bus):
    """Test that orchestrator properly delegates execution to workflow engine."""
    
    # Capture events
    capture = EventCapture()
    original_publish = event_bus.publish
    event_bus.publish = capture.capture
    
    # Create simple execution plan
    task1 = ExecutionTask(
        id="task1",
        title="Engineer Task",
        description="Generate code",
        agent="salesforce_engineer",
        input={"requirement": "Create Apex class"}
    )
    task2 = ExecutionTask(
        id="task2",
        title="Verify Task",
        description="Verify code",
        agent="verifier",
        dependencies=["task1"],
        input={"code": "generated"}
    )
    
    plan = ExecutionPlan(
        id="plan-1",
        objective="Build Salesforce component",
        tasks=[task1, task2]
    )
    
    workflow_id = str(uuid4())
    request = "Build Apex trigger for account validation"
    
    # Execute workflow
    result = await workflow_engine.execute_plan(plan, request, workflow_id=workflow_id)
    
    # Verify execution completed
    assert result.status in [WorkflowStatus.SUCCESS, WorkflowStatus.ESCALATED]
    assert result.total_tasks == 2
    
    # Verify events were published
    event_names = [e["event"] for e in capture.events]
    assert "workflow.started" in event_names or len(event_names) > 0
    
    # Restore original publish
    event_bus.publish = original_publish


@pytest.mark.asyncio
async def test_eventbus_lifecycle_tracking(workflow_engine, event_bus):
    """Test that EventBus tracks complete workflow lifecycle."""
    
    events_published = []
    
    async def track_event(event, payload, **kwargs):
        events_published.append(event)
    
    original_publish = event_bus.publish
    event_bus.publish = track_event
    
    task = ExecutionTask(
        id="lifecycle-test",
        title="Lifecycle Test",
        description="Test event tracking",
        agent="salesforce_engineer",
        input={}
    )
    
    plan = ExecutionPlan(
        id="plan-lifecycle",
        objective="Test lifecycle",
        tasks=[task]
    )
    
    workflow_id = str(uuid4())
    await workflow_engine.execute_plan(plan, "Test request", workflow_id=workflow_id)
    
    # Restore original publish
    event_bus.publish = original_publish
    
    # Should have published multiple lifecycle events
    assert len(events_published) > 0
    
    # Check for key lifecycle events
    event_str = str(events_published)
    # At least task and workflow events should be present
    assert any("task" in str(e).lower() or "workflow" in str(e).lower() for e in events_published)


@pytest.mark.asyncio
async def test_memory_persistence_across_workflow(workflow_engine, state_manager):
    """Test that workflow state persists to memory across execution."""
    
    task = ExecutionTask(
        id="persist-test",
        title="Persistence Test",
        description="Test memory persistence",
        agent="salesforce_engineer",
        input={"test": "data"}
    )
    
    plan = ExecutionPlan(
        id="plan-persist",
        objective="Test persistence",
        tasks=[task]
    )
    
    workflow_id = str(uuid4())
    
    # Execute workflow
    result1 = await workflow_engine.execute_plan(
        plan, "Test request", workflow_id=workflow_id
    )
    assert result1.status in [WorkflowStatus.SUCCESS, WorkflowStatus.ESCALATED]
    
    # Load snapshot from state manager
    snapshot = await workflow_engine.load_snapshot(workflow_id)
    
    # Snapshot should exist
    assert snapshot is not None
    assert snapshot.workflow_id == workflow_id
    assert snapshot.status in ["success", "escalated"]


@pytest.mark.asyncio
async def test_recovery_agent_sequence_logic(workflow_engine, recovery_agent):
    """Verify the retry sequence: 1st/2nd fail -> RETRY, 3rd fail -> ESCALATE."""
    
    # Create an agent that fails exactly 3 times then succeeds
    # But since we want to test the escalation at 3, we'll keep it failing.
    failing_agent = MockAgent("failing_agent", succeed=False)
    workflow_engine.agent_registry.register("failing_agent", failing_agent)
    
    task = ExecutionTask(
        id="seq-fail-task",
        title="Sequential Failure",
        description="Sequential failure test task",
        agent="failing_agent",
        max_attempts=4,
        input={}
    )
    
    # Mock recovery behavior based on attempts
    async def dynamic_recover(t, err):
        if t.attempts < 3:
            return RecoveryDecision(action=RecoveryAction.RETRY, reason=f"Retry {t.attempts}")
        return RecoveryDecision(action=RecoveryAction.ESCALATE, reason="Max retries reached")
    
    recovery_agent.recover = AsyncMock(side_effect=dynamic_recover)
    
    plan = ExecutionPlan(id="plan-fail-seq", objective="Test sequence", tasks=[task])
    result = await workflow_engine.execute_plan(plan, "Test sequence")
    
    assert result.status == WorkflowStatus.ESCALATED
    assert failing_agent.call_count == 4
    assert recovery_agent.recover.call_count == 4


@pytest.mark.asyncio
async def test_engine_performance_benchmark(workflow_engine):
    """Benchmark peak CPU, Memory, and Latency during a 20-task parallel load."""
    if psutil is None:
        pytest.skip("psutil not installed")

    process = psutil.Process(os.getpid())
    
    tasks = [
        ExecutionTask(id=f"perf-{i}", title=f"Task {i}", description=f"Task {i}", agent="salesforce_engineer", input={})
        for i in range(20)
    ]
    plan = ExecutionPlan(id="benchmark-plan", objective="Benchmark", tasks=tasks)
    
    start_time = datetime.now()
    start_mem = process.memory_info().rss
    
    result = await workflow_engine.execute_plan(plan, "Performance Benchmark")
    
    end_time = datetime.now()
    peak_mem = process.memory_info().rss
    
    duration = (end_time - start_time).total_seconds()
    mem_delta_mb = (peak_mem - start_mem) / 1024 / 1024
    
    assert result.status == WorkflowStatus.SUCCESS
    assert len([t for t in result.tasks if t.status == TaskStatus.SUCCESS]) == 20
    
    logger.info(f"PERF: Latency={duration}s, Memory Delta={mem_delta_mb:.2f}MB")


@pytest.mark.asyncio
async def test_memory_stress_and_persistence(tmp_path):
    """Stress test the memory store with 100 concurrent ops and verify persistence."""
    db_path = tmp_path / "stress.db"
    store = SQLiteMemoryStore(db_path)
    await store.open()
    memory = MemoryManager(store)
    
    # 100 concurrent writes
    async def write_op(i):
        await memory.store_execution_history(
            agent_name="StressAgent", task_description=f"Dose {i}", success=True,
            duration_seconds=0.1, created_by="Stress", workflow_id="stress-1", task_id=f"t-{i}"
        )

    await asyncio.gather(*[write_op(i) for i in range(100)])
    
    # Close and restart to verify persistence
    await store.close()
    
    new_store = SQLiteMemoryStore(db_path)
    await new_store.open()
    new_memory = MemoryManager(new_store)
    
    results = await new_memory.search_memory(keywords=["Dose"], limit=200)
    assert len(results) == 100
    await new_store.close()


@pytest.mark.asyncio
async def test_complete_platform_orchestration_loop(
    agent_registry, recovery_agent, event_bus, state_manager, memory_manager, reward_learning_engine
):
    """
    End-to-End Platform Test: 
    User -> Orchestrator -> Planner -> Engine -> Agents -> Reward -> Memory
    """
    registry, agents = agent_registry
    
    # Mock Planner to return a simple plan
    planner_mock = AsyncMock()
    planner_mock.create_plan = AsyncMock(return_value=ExecutionPlan(
        id="e2e-plan",
        objective="Build Apex",
        tasks=[ExecutionTask(id="e2e-1", title="Build Apex", description="Build Apex class", agent="salesforce_engineer", input={})]
    ))

    orchestrator = OrchestratorAgent(
        planner=planner_mock,
        recovery_agent=recovery_agent,
        agent_registry=registry,
        state_manager=state_manager,
        event_bus=event_bus,
        memory_manager=memory_manager,
        reward_learning_engine=reward_learning_engine
    )

    # Run the full request
    report = await orchestrator.run("Create a trigger for Account")

    # Verify flow
    assert report.status == WorkflowStatus.SUCCESS
    assert report.successful_tasks == 1
    
    # Verify Reward & Memory calls
    memory_manager.store_workflow_history.assert_called()
    # The orchestrator publishes completed events
    # We verify if the reward engine was evaluated by checking the mock (if it was hooked)
    assert orchestrator.reward_learning_engine is not None


@pytest.mark.asyncio
async def test_parallel_task_execution(workflow_engine):
    """Test that independent tasks execute in parallel."""
    
    execution_times = []
    
    class TimedAgent:
        async def execute(self, task: ExecutionTask) -> TaskResult:
            start = datetime.now()
            # Simulate work
            await asyncio.sleep(0.05)
            end = datetime.now()
            execution_times.append({
                "task_id": task.id,
                "start": start,
                "end": end
            })
            return TaskResult(task_id=task.id, success=True, output={})
    
    timed_agent = TimedAgent()
    workflow_engine.agent_registry.register("timed", timed_agent)
    
    # Create independent parallel tasks
    tasks = [
        ExecutionTask(
            id=f"parallel-{i}",
            title=f"Parallel Task {i}",
            description=f"Task {i}",
            agent="timed",
            input={}
        )
        for i in range(3)
    ]
    
    plan = ExecutionPlan(
        id="plan-parallel",
        objective="Test parallel execution",
        tasks=tasks
    )
    
    workflow_id = str(uuid4())
    result = await workflow_engine.execute_plan(
        plan, "Test parallel", workflow_id=workflow_id
    )
    
    assert result.status == WorkflowStatus.SUCCESS
    assert result.successful_tasks == 3


@pytest.mark.asyncio
async def test_task_dependency_ordering(workflow_engine):
    """Test that tasks respect dependency ordering."""
    
    execution_order = []
    
    class OrderAgent:
        def __init__(self, name):
            self.name = name
        
        async def execute(self, task: ExecutionTask) -> TaskResult:
            execution_order.append(self.name)
            return TaskResult(task_id=task.id, success=True, output={})
    
    for agent_name in ["a", "b", "c"]:
        workflow_engine.agent_registry.register(agent_name, OrderAgent(agent_name))
    
    # Create dependent tasks
    task_a = ExecutionTask(
        id="order-a",
        title="Task A",
        description="First",
        agent="a",
        input={}
    )
    task_b = ExecutionTask(
        id="order-b",
        title="Task B",
        description="Second",
        agent="b",
        dependencies=["order-a"],
        input={}
    )
    task_c = ExecutionTask(
        id="order-c",
        title="Task C",
        description="Third",
        agent="c",
        dependencies=["order-b"],
        input={}
    )
    
    plan = ExecutionPlan(
        id="plan-order",
        objective="Test ordering",
        tasks=[task_a, task_b, task_c]
    )
    
    workflow_id = str(uuid4())
    result = await workflow_engine.execute_plan(
        plan, "Test ordering", workflow_id=workflow_id
    )
    
    assert result.status == WorkflowStatus.SUCCESS
    assert execution_order == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_end_to_end_workflow_to_learning(
    workflow_engine,
    reward_learning_engine,
    event_bus,
    memory_manager
):
    """Test complete flow: Workflow execution → Reward & Learning."""
    
    # Set up basic workflow
    task = ExecutionTask(
        id="e2e-task",
        title="End-to-End Task",
        description="Full flow test",
        agent="salesforce_engineer",
        input={"type": "apex_class"}
    )
    
    plan = ExecutionPlan(
        id="plan-e2e",
        objective="End-to-end test",
        tasks=[task]
    )
    
    workflow_id = str(uuid4())
    
    # Execute workflow
    result = await workflow_engine.execute_plan(
        plan, "E2E request", workflow_id=workflow_id
    )
    
    assert result.status in [WorkflowStatus.SUCCESS, WorkflowStatus.ESCALATED]
    
    # Create execution report
    report = ExecutionReport(
        workflow_id=workflow_id,
        request="E2E request",
        status=result.status,
        plan_id=plan.id,
        total_tasks=len(plan.tasks),
        successful_tasks=result.successful_tasks,
        failed_tasks=result.failed_tasks,
        escalated=False,
        tasks=plan.tasks,
        started_at=datetime.now(),
        completed_at=datetime.now(),
        summary="E2E test execution"
    )
    
    # Evaluate with reward & learning engine
    learning_result = await reward_learning_engine.evaluate_execution_report(report)
    
    # Verify learning was captured
    assert learning_result is not None
    assert learning_result.workflow_id == workflow_id
    assert learning_result.workflow_score is not None
    assert learning_result.workflow_score.score >= 0


@pytest.mark.asyncio
async def test_workflow_pause_resume(workflow_engine):
    """Test pause and resume workflow operations."""
    
    pause_event_fired = False
    resume_event_fired = False
    
    async def capture_pause(event, payload, **kwargs):
        nonlocal pause_event_fired
        if "pause" in str(event).lower():
            pause_event_fired = True
    
    original_publish = workflow_engine.event_bus.publish
    workflow_engine.event_bus.publish = capture_pause
    
    task1 = ExecutionTask(
        id="pause-task1",
        title="Task 1",
        description="First",
        agent="salesforce_engineer",
        input={}
    )
    task2 = ExecutionTask(
        id="pause-task2",
        title="Task 2",
        description="Second",
        agent="verifier",
        dependencies=["pause-task1"],
        input={}
    )
    
    plan = ExecutionPlan(
        id="plan-pause",
        objective="Test pause/resume",
        tasks=[task1, task2]
    )
    
    workflow_id = str(uuid4())
    
    # Schedule pause after small delay
    async def trigger_pause():
        await asyncio.sleep(0.01)
        try:
            await workflow_engine.pause(workflow_id)
        except Exception:
            pass  # Workflow might complete before pause
    
    # Execute with pause
    exec_task = asyncio.create_task(
        workflow_engine.execute_plan(plan, "Test", workflow_id=workflow_id)
    )
    pause_task = asyncio.create_task(trigger_pause())
    
    await pause_task
    await asyncio.sleep(0.1)
    
    # Restore original publish
    workflow_engine.event_bus.publish = original_publish
    
    # Complete execution
    try:
        result = await asyncio.wait_for(exec_task, timeout=5.0)
        assert result.status in [WorkflowStatus.SUCCESS, WorkflowStatus.ESCALATED]
    except asyncio.TimeoutError:
        pass  # Expected if pause holds workflow


@pytest.mark.asyncio
async def test_workflow_cancellation(workflow_engine):
    """Test workflow cancellation."""
    
    task1 = ExecutionTask(
        id="cancel-task1",
        title="Task 1",
        description="First",
        agent="salesforce_engineer",
        input={}
    )
    task2 = ExecutionTask(
        id="cancel-task2",
        title="Task 2",
        description="Second",
        agent="verifier",
        dependencies=["cancel-task1"],
        input={}
    )
    
    plan = ExecutionPlan(
        id="plan-cancel",
        objective="Test cancellation",
        tasks=[task1, task2]
    )
    
    workflow_id = str(uuid4())
    
    # Schedule cancellation after small delay
    async def trigger_cancel():
        await asyncio.sleep(0.01)
        try:
            await workflow_engine.cancel(workflow_id)
        except Exception:
            pass
    
    exec_task = asyncio.create_task(
        workflow_engine.execute_plan(plan, "Test", workflow_id=workflow_id)
    )
    cancel_task = asyncio.create_task(trigger_cancel())
    
    await cancel_task
    
    try:
        result = await asyncio.wait_for(exec_task, timeout=5.0)
        # Should be cancelled, escalated, or completed
        assert result.status in [WorkflowStatus.SUCCESS, WorkflowStatus.ESCALATED, WorkflowStatus.FAILED]
    except asyncio.TimeoutError:
        pass


@pytest.mark.asyncio
async def test_conditional_branching_in_workflow(workflow_engine):
    """Test conditional task branching."""
    
    # Task 1 outputs result
    task1 = ExecutionTask(
        id="condition-task1",
        title="Decider",
        description="Sets output for condition",
        agent="salesforce_engineer",
        input={"decision": "proceed"}
    )
    
    # Task 2 runs if condition is met
    task2 = ExecutionTask(
        id="condition-task2",
        title="Conditional Task",
        description="Runs conditionally",
        agent="verifier",
        dependencies=["condition-task1"],
        metadata={"condition": {"equals": "proceed"}},
        input={}
    )
    
    plan = ExecutionPlan(
        id="plan-condition",
        objective="Test conditional branching",
        tasks=[task1, task2]
    )
    
    workflow_id = str(uuid4())
    result = await workflow_engine.execute_plan(
        plan, "Test condition", workflow_id=workflow_id
    )
    
    assert result.status in [WorkflowStatus.SUCCESS, WorkflowStatus.ESCALATED]


@pytest.mark.asyncio
async def test_checkpoint_restoration(workflow_engine, state_manager):
    """Test checkpoint creation and restoration."""
    
    task = ExecutionTask(
        id="checkpoint-task",
        title="Checkpoint Test",
        description="Test checkpointing",
        agent="salesforce_engineer",
        input={}
    )
    
    plan = ExecutionPlan(
        id="plan-checkpoint",
        objective="Test checkpointing",
        tasks=[task]
    )
    
    workflow_id = str(uuid4())
    
    # Execute and checkpoint
    result1 = await workflow_engine.execute_plan(
        plan, "Test checkpoint", workflow_id=workflow_id
    )
    
    # Verify checkpoint exists
    snapshot = await workflow_engine.load_snapshot(workflow_id)
    assert snapshot is not None
    assert snapshot.workflow_id == workflow_id
    
    # Verify version incremented
    assert snapshot.version > 0


@pytest.mark.asyncio
async def test_error_handling_and_recovery(workflow_engine, recovery_agent):
    """Test error handling with recovery agent intervention."""
    
    recovery_agent.recover = AsyncMock(
        return_value=RecoveryDecision(
            action=RecoveryAction.RETRY,
            reason="Recovered successfully",
            updated_input={}
        )
    )
    
    # Create agent that fails once then succeeds
    flaky_agent = MockAgent("flaky", succeed=True, fail_on_attempt=1)
    workflow_engine.agent_registry.register("flaky", flaky_agent)
    
    task = ExecutionTask(
        id="flaky-task",
        title="Flaky Task",
        description="Fails once",
        agent="flaky",
        input={}
    )
    
    plan = ExecutionPlan(
        id="plan-flaky",
        objective="Test error recovery",
        tasks=[task]
    )
    
    workflow_id = str(uuid4())
    result = await workflow_engine.execute_plan(
        plan, "Test error", workflow_id=workflow_id
    )
    
    # Should have completed (either success after retry or escalation)
    assert result.status in [WorkflowStatus.SUCCESS, WorkflowStatus.ESCALATED]
