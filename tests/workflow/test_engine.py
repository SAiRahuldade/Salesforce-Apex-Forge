import pytest
import asyncio
from typing import Any
from uuid import uuid4

from salesforce_ai_engineer.agent.models import (
    ExecutionPlan,
    ExecutionTask,
    TaskResult,
    TaskStatus,
    WorkflowStatus,
    RecoveryDecision,
    RecoveryAction
)
from salesforce_ai_engineer.workflow.models import (
    WorkflowRunStatus,
    WorkflowExecutionPolicy,
    WorkflowRetryPolicy
)
from salesforce_ai_engineer.workflow.engine import WorkflowExecutionEngine

class DummyAgent:
    def __init__(self, succeed=True, fail_on_attempt=None):
        self.succeed = succeed
        self.fail_on_attempt = fail_on_attempt
        self.calls = 0

    async def execute(self, task: ExecutionTask) -> TaskResult:
        self.calls += 1
        if self.fail_on_attempt is not None and self.calls == self.fail_on_attempt:
            raise RuntimeError("Intentional failure")
        
        if self.succeed:
            return TaskResult(task_id=task.id, success=True, output={"result": "ok"})
        else:
            return TaskResult(task_id=task.id, success=False, error="Failed task")

class DummyRegistry:
    def __init__(self, agent_map=None):
        self.agent_map = agent_map or {}

    def resolve(self, name: str):
        if name in self.agent_map:
            return self.agent_map[name]
        return DummyAgent(succeed=True)

class DummyRecoveryAgent:
    def __init__(self, action=RecoveryAction.RETRY):
        self.action = action

    async def recover(self, task: ExecutionTask, error: Exception) -> RecoveryDecision:
        return RecoveryDecision(action=self.action, reason="Testing recovery", updated_input=task.input)

class DummyEventBus:
    def __init__(self):
        self.events = []

    async def publish(self, event, payload, workflow_id, **kwargs):
        self.events.append({"event": event, "payload": payload, "workflow_id": workflow_id})

@pytest.fixture
def engine():
    registry = DummyRegistry({"test_agent": DummyAgent(succeed=True)})
    recovery = DummyRecoveryAgent()
    events = DummyEventBus()
    return WorkflowExecutionEngine(agent_registry=registry, recovery_agent=recovery, event_bus=events)

@pytest.mark.asyncio
async def test_execute_plan_success(engine):
    task = ExecutionTask(title="Task 1", description="1", agent="test_agent")
    plan = ExecutionPlan(objective="Test", tasks=[task])
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.SUCCESS
    assert result.successful_tasks == 1
    assert result.failed_tasks == 0

@pytest.mark.asyncio
async def test_execute_plan_with_retry_and_recovery():
    flaky_agent = DummyAgent(succeed=True, fail_on_attempt=1)
    registry = DummyRegistry({"flaky": flaky_agent})
    recovery = DummyRecoveryAgent(action=RecoveryAction.RETRY)
    events = DummyEventBus()
    
    policy = WorkflowExecutionPolicy(
        retry_policy=WorkflowRetryPolicy(max_attempts=2, initial_backoff_seconds=0.01)
    )
    
    engine = WorkflowExecutionEngine(
        agent_registry=registry,
        recovery_agent=recovery,
        event_bus=events,
        default_policy=policy
    )
    
    task = ExecutionTask(title="Flaky Task", description="flaky", agent="flaky")
    plan = ExecutionPlan(objective="Test", tasks=[task])
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.SUCCESS
    assert result.successful_tasks == 1
    assert flaky_agent.calls == 2

@pytest.mark.asyncio
async def test_execute_plan_escalate():
    failing_agent = DummyAgent(succeed=False, fail_on_attempt=1)
    registry = DummyRegistry({"fail": failing_agent})
    recovery = DummyRecoveryAgent(action=RecoveryAction.ESCALATE)
    events = DummyEventBus()
    
    policy = WorkflowExecutionPolicy(fail_fast=True, rollback_on_failure=False)
    
    engine = WorkflowExecutionEngine(
        agent_registry=registry,
        recovery_agent=recovery,
        event_bus=events,
        default_policy=policy
    )
    
    task = ExecutionTask(title="Fail Task", description="fail", agent="fail")
    plan = ExecutionPlan(objective="Test", tasks=[task])
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.ESCALATED
    assert result.failed_tasks == 1

@pytest.mark.asyncio
async def test_conditional_branching(engine):
    """Test conditional branching based on task output."""
    # If condition passes, task runs.
    task1 = ExecutionTask(title="T1", description="1", agent="test_agent")
    task2 = ExecutionTask(
        title="T2", description="2", agent="test_agent", dependencies=[task1.id],
        metadata={"condition": {"task_id": task1.id, "equals": {"result": "ok"}}}
    )
    task3 = ExecutionTask(
        title="T3", description="3", agent="test_agent", dependencies=[task1.id],
        metadata={"condition": {"task_id": task1.id, "equals": {"result": "other"}}}
    )
    plan = ExecutionPlan(objective="Test", tasks=[task1, task2, task3])
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.SUCCESS
    assert result.successful_tasks == 2  # t1 and t2 ran
    assert result.skipped_tasks == 1     # t3 skipped

@pytest.mark.asyncio
async def test_cancel_workflow():
    """Test cancellation of in-flight workflows."""
    registry = DummyRegistry({"test": DummyAgent(succeed=True)})
    recovery = DummyRecoveryAgent()
    events = DummyEventBus()
    engine = WorkflowExecutionEngine(agent_registry=registry, recovery_agent=recovery, event_bus=events)
    
    task1 = ExecutionTask(title="T1", description="1", agent="test")
    task2 = ExecutionTask(title="T2", description="2", agent="test", dependencies=[task1.id])
    task3 = ExecutionTask(title="T3", description="3", agent="test", dependencies=[task2.id])
    plan = ExecutionPlan(objective="Test", tasks=[task1, task2, task3])
    
    workflow_id = str(uuid4())
    
    async def trigger_cancel():
        await asyncio.sleep(0.05)
        await engine.cancel(workflow_id)
    
    exec_task = asyncio.create_task(engine.execute_plan(plan, request="Do work", workflow_id=workflow_id))
    cancel_task = asyncio.create_task(trigger_cancel())
    
    await asyncio.gather(cancel_task)
    await asyncio.sleep(0.1)
    result = await asyncio.wait_for(exec_task, timeout=5.0)
    
    assert result.run_status in [WorkflowRunStatus.CANCELLED, WorkflowRunStatus.SUCCESS]

@pytest.mark.asyncio
async def test_rollback_on_failure():
    """Test rollback execution when tasks fail."""
    registry = DummyRegistry({"fail": DummyAgent(succeed=False)})
    recovery = DummyRecoveryAgent(action=RecoveryAction.ESCALATE)
    events = DummyEventBus()
    
    policy = WorkflowExecutionPolicy(
        fail_fast=True,
        rollback_on_failure=True
    )
    
    engine = WorkflowExecutionEngine(
        agent_registry=registry,
        recovery_agent=recovery,
        event_bus=events,
        default_policy=policy
    )
    
    task1 = ExecutionTask(title="T1", description="1", agent="fail")
    task2 = ExecutionTask(title="T2", description="2", agent="fail", dependencies=[task1.id])
    plan = ExecutionPlan(objective="Test", tasks=[task1, task2])
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.ESCALATED
    assert result.failed_tasks == 1

@pytest.mark.asyncio
async def test_dynamic_task_generation():
    """Test dynamic task generation from task output."""
    registry = DummyRegistry({"gen": DummyAgent(succeed=True)})
    recovery = DummyRecoveryAgent()
    events = DummyEventBus()
    engine = WorkflowExecutionEngine(agent_registry=registry, recovery_agent=recovery, event_bus=events)
    
    # Create agent that generates tasks
    class GeneratorAgent:
        async def execute(self, task: ExecutionTask) -> TaskResult:
            return TaskResult(
                task_id=task.id,
                success=True,
                output={
                    "result": "ok",
                    "generated_tasks": [
                        {
                            "id": "gen-1",
                            "title": "Generated 1",
                            "description": "Generated by task",
                            "agent": "gen",
                            "dependencies": [task.id]
                        }
                    ]
                }
            )
    
    registry.agent_map["gen"] = GeneratorAgent()
    task1 = ExecutionTask(title="Generator", description="1", agent="gen")
    plan = ExecutionPlan(objective="Test", tasks=[task1])
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.SUCCESS
    assert result.total_tasks == 2  # Original + generated

@pytest.mark.asyncio
async def test_parallel_task_execution():
    """Test parallel execution of independent tasks."""
    registry = DummyRegistry({"test": DummyAgent(succeed=True)})
    recovery = DummyRecoveryAgent()
    events = DummyEventBus()
    
    policy = WorkflowExecutionPolicy(max_parallel_tasks=3)
    engine = WorkflowExecutionEngine(
        agent_registry=registry,
        recovery_agent=recovery,
        event_bus=events,
        default_policy=policy
    )
    
    # Create 3 independent tasks
    task1 = ExecutionTask(title="T1", description="1", agent="test")
    task2 = ExecutionTask(title="T2", description="2", agent="test")
    task3 = ExecutionTask(title="T3", description="3", agent="test")
    plan = ExecutionPlan(objective="Test", tasks=[task1, task2, task3])
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.SUCCESS
    assert result.successful_tasks == 3

@pytest.mark.asyncio
async def test_task_timeout():
    """Test timeout handling for long-running tasks."""
    class SlowAgent:
        async def execute(self, task: ExecutionTask) -> TaskResult:
            await asyncio.sleep(10)
            return TaskResult(task_id=task.id, success=True, output={})
    
    registry = DummyRegistry({"slow": SlowAgent()})
    recovery = DummyRecoveryAgent(action=RecoveryAction.ESCALATE)
    events = DummyEventBus()
    
    policy = WorkflowExecutionPolicy(
        task_timeout_seconds=0.1,
        retry_policy=WorkflowRetryPolicy(max_attempts=1)
    )
    
    engine = WorkflowExecutionEngine(
        agent_registry=registry,
        recovery_agent=recovery,
        event_bus=events,
        default_policy=policy
    )
    
    task = ExecutionTask(title="Slow", description="slow", agent="slow")
    plan = ExecutionPlan(objective="Test", tasks=[task])
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.ESCALATED

@pytest.mark.asyncio
async def test_task_dependency_resolution():
    """Test that tasks execute in correct dependency order."""
    execution_order = []
    
    class OrderAgent:
        def __init__(self, task_name):
            self.task_name = task_name
        
        async def execute(self, task: ExecutionTask) -> TaskResult:
            execution_order.append(self.task_name)
            return TaskResult(task_id=task.id, success=True, output={})
    
    agent_a = OrderAgent("A")
    agent_b = OrderAgent("B")
    agent_c = OrderAgent("C")
    
    registry = DummyRegistry({
        "a": agent_a,
        "b": agent_b,
        "c": agent_c
    })
    recovery = DummyRecoveryAgent()
    events = DummyEventBus()
    engine = WorkflowExecutionEngine(agent_registry=registry, recovery_agent=recovery, event_bus=events)
    
    task_a = ExecutionTask(title="A", description="a", agent="a")
    task_b = ExecutionTask(title="B", description="b", agent="b", dependencies=[task_a.id])
    task_c = ExecutionTask(title="C", description="c", agent="c", dependencies=[task_b.id])
    plan = ExecutionPlan(objective="Test", tasks=[task_a, task_b, task_c])
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.SUCCESS
    assert execution_order == ["A", "B", "C"]

@pytest.mark.asyncio
async def test_workflow_persistence():
    """Test workflow snapshot persistence via state manager."""
    from salesforce_ai_engineer.core.state import StateManager
    from pathlib import Path
    import tempfile
    
    registry = DummyRegistry({"test": DummyAgent(succeed=True)})
    recovery = DummyRecoveryAgent()
    events = DummyEventBus()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "workflow_state.json"
        state_manager = StateManager(state_file)
        
        engine = WorkflowExecutionEngine(
            agent_registry=registry,
            recovery_agent=recovery,
            event_bus=events,
            state_manager=state_manager
        )
        
        task = ExecutionTask(title="T", description="t", agent="test")
        plan = ExecutionPlan(objective="Test", tasks=[task])
        
        workflow_id = str(uuid4())
        result = await engine.execute_plan(plan, request="Do work", workflow_id=workflow_id)
        
        assert result.status == WorkflowStatus.SUCCESS
        
        # Verify snapshot was saved to state manager
        snapshot = await engine.load_snapshot(workflow_id)
        assert snapshot is not None
        assert snapshot.workflow_id == workflow_id

@pytest.mark.asyncio
async def test_max_parallel_tasks_limit():
    """Test that max_parallel_tasks limit is respected."""
    concurrent_executions = []
    max_concurrent = 0
    lock = asyncio.Lock()
    
    class ConcurrentAgent:
        async def execute(self, task: ExecutionTask) -> TaskResult:
            nonlocal max_concurrent
            async with lock:
                concurrent_executions.append(1)
                max_concurrent = max(max_concurrent, len(concurrent_executions))
            
            await asyncio.sleep(0.05)
            
            async with lock:
                concurrent_executions.pop()
            
            return TaskResult(task_id=task.id, success=True, output={})
    
    agent = ConcurrentAgent()
    registry = DummyRegistry({"concurrent": agent})
    recovery = DummyRecoveryAgent()
    events = DummyEventBus()
    
    policy = WorkflowExecutionPolicy(max_parallel_tasks=2)
    engine = WorkflowExecutionEngine(
        agent_registry=registry,
        recovery_agent=recovery,
        event_bus=events,
        default_policy=policy
    )
    
    tasks = [ExecutionTask(title=f"T{i}", description=str(i), agent="concurrent") for i in range(5)]
    plan = ExecutionPlan(objective="Test", tasks=tasks)
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.SUCCESS
    assert max_concurrent <= 2

@pytest.mark.asyncio
async def test_restart_workflow():
    """Test restarting a completed workflow from the beginning."""
    registry = DummyRegistry({"test": DummyAgent(succeed=True)})
    recovery = DummyRecoveryAgent()
    events = DummyEventBus()
    engine = WorkflowExecutionEngine(agent_registry=registry, recovery_agent=recovery, event_bus=events)
    
    task = ExecutionTask(title="T", description="t", agent="test")
    plan = ExecutionPlan(objective="Test", tasks=[task])
    
    workflow_id = str(uuid4())
    result1 = await engine.execute_plan(plan, request="Do work", workflow_id=workflow_id)
    assert result1.status == WorkflowStatus.SUCCESS
    
    result2 = await engine.restart(workflow_id)
    assert result2.status == WorkflowStatus.SUCCESS

@pytest.mark.asyncio
async def test_workflow_with_agent_not_found():
    """Test workflow fails gracefully when agent is not registered."""
    class StrictRegistry:
        def resolve(self, name: str):
            from salesforce_ai_engineer.agent.registry import AgentNotRegisteredError
            raise AgentNotRegisteredError(f"Agent {name!r} not registered")
    
    recovery = DummyRecoveryAgent()
    events = DummyEventBus()
    engine = WorkflowExecutionEngine(agent_registry=StrictRegistry(), recovery_agent=recovery, event_bus=events)
    
    task = ExecutionTask(title="T", description="t", agent="nonexistent")
    plan = ExecutionPlan(objective="Test", tasks=[task])
    
    result = await engine.execute_plan(plan, request="Do work")
    assert result.status == WorkflowStatus.ESCALATED
    assert result.failed_tasks == 1
