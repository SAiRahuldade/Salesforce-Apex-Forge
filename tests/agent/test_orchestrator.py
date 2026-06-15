from __future__ import annotations

from pathlib import Path

from salesforce_ai_engineer.agent import (
    AgentRegistry,
    ExecutionPlan,
    ExecutionTask,
    OrchestratorAgent,
    RecoveryAction,
    RecoveryDecision,
    TaskResult,
    TaskStatus,
    WorkflowStatus,
)
from salesforce_ai_engineer.core import Event, EventBus, StateManager


class FakePlanner:
    def __init__(self, plan: ExecutionPlan) -> None:
        self.plan = plan

    async def create_plan(self, request: str) -> ExecutionPlan:
        self.plan.objective = request
        return self.plan


class RecordingAgent:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, task: ExecutionTask) -> TaskResult:
        self.executed.append(task.id)
        return TaskResult(task_id=task.id, success=True, output={"done": task.id})


class FailingThenSuccessfulAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, task: ExecutionTask) -> TaskResult:
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("temporary connection failure")
        return TaskResult(task_id=task.id, success=True, output={"recovered": True})


class FakeRecovery:
    async def recover(self, task: ExecutionTask, error: Exception | str) -> RecoveryDecision:
        return RecoveryDecision(
            action=RecoveryAction.RETRY,
            reason="retry transient failure",
            updated_input={**task.input, "recovered": True},
        )


def make_orchestrator(
    plan: ExecutionPlan,
    state_path: Path,
    registry: AgentRegistry,
    event_bus: EventBus | None = None,
) -> OrchestratorAgent:
    return OrchestratorAgent(
        planner=FakePlanner(plan),
        recovery_agent=FakeRecovery(),
        agent_registry=registry,
        state_manager=StateManager(state_path),
        event_bus=event_bus or EventBus(),
    )


async def test_orchestrator_executes_tasks_in_dependency_order(tmp_path: Path) -> None:
    plan = ExecutionPlan(
        objective="Build",
        tasks=[
            ExecutionTask(id="plan", title="Plan", description="Plan work", agent="worker"),
            ExecutionTask(
                id="execute",
                title="Execute",
                description="Execute work",
                agent="worker",
                dependencies=["plan"],
            ),
        ],
    )
    worker = RecordingAgent()
    registry = AgentRegistry()
    registry.register("worker", worker)
    orchestrator = make_orchestrator(plan, tmp_path / "state.json", registry)

    report = await orchestrator.run("Build")

    assert report.status == WorkflowStatus.SUCCESS
    assert worker.executed == ["plan", "execute"]
    assert [task.status for task in report.tasks] == [TaskStatus.SUCCESS, TaskStatus.SUCCESS]


async def test_orchestrator_recovers_and_retries_failed_agent(tmp_path: Path) -> None:
    plan = ExecutionPlan(
        objective="Recover",
        tasks=[
            ExecutionTask(
                id="flaky",
                title="Flaky",
                description="Retry this",
                agent="flaky",
                max_attempts=2,
            )
        ],
    )
    flaky = FailingThenSuccessfulAgent()
    registry = AgentRegistry()
    registry.register("flaky", flaky)
    orchestrator = make_orchestrator(plan, tmp_path / "state.json", registry)

    report = await orchestrator.run("Recover")

    assert report.status == WorkflowStatus.SUCCESS
    assert report.tasks[0].attempts == 2
    assert report.tasks[0].input["recovered"] is True


async def test_orchestrator_saves_checkpoint_and_resumes(tmp_path: Path) -> None:
    plan = ExecutionPlan(
        objective="Resume",
        tasks=[
            ExecutionTask(id="first", title="First", description="First", agent="worker"),
            ExecutionTask(
                id="second",
                title="Second",
                description="Second",
                agent="worker",
                dependencies=["first"],
            ),
        ],
    )
    worker = RecordingAgent()
    registry = AgentRegistry()
    registry.register("worker", worker)
    orchestrator = make_orchestrator(plan, tmp_path / "state.json", registry)

    report = await orchestrator.run("Resume", workflow_id="resume-workflow")
    resumed_report = await orchestrator.resume("resume-workflow")

    assert report.status == WorkflowStatus.SUCCESS
    assert resumed_report.status == WorkflowStatus.SUCCESS
    assert worker.executed == ["first", "second"]


async def test_orchestrator_logs_actions_through_event_bus(tmp_path: Path) -> None:
    plan = ExecutionPlan(
        objective="Events",
        tasks=[ExecutionTask(id="task", title="Task", description="Task", agent="worker")],
    )
    events: list[Event] = []
    event_bus = EventBus()
    await event_bus.subscribe("*", lambda event: events.append(event))
    registry = AgentRegistry()
    registry.register("worker", RecordingAgent())
    orchestrator = make_orchestrator(plan, tmp_path / "state.json", registry, event_bus)

    await orchestrator.run("Events")

    event_names = [event.name for event in events]
    assert "orchestrator.plan.requested" in event_names
    # Orchestrator delegates to WorkflowExecutionEngine which publishes workflow.* events
    assert "workflow.started" in event_names or "orchestrator.workflow.started" in event_names
    assert "orchestrator.workflow.completed" in event_names
