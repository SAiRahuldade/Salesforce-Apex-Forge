from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from salesforce_ai_engineer.agent import (
    AgentRegistry,
    ExecutionPlan,
    ExecutionTask,
    OrchestratorAgent,
    RecoveryAction,
    RecoveryDecision,
    ExecutionReport,
    TaskResult,
    TaskStatus,
    WorkflowStatus,
)
from salesforce_ai_engineer.core import EventBus, StateManager
from salesforce_ai_engineer.memory import MemoryManager, SQLiteMemoryStore
from salesforce_ai_engineer.models.domain.memory import MemoryCategory
from salesforce_ai_engineer.reward_learning import (
    RewardLearningEngine,
    StrategyPerformance,
    StrategyType,
)


class FakePlanner:
    def __init__(self, plan: ExecutionPlan) -> None:
        self.plan = plan

    async def create_plan(self, request: str) -> ExecutionPlan:
        self.plan.objective = request
        return self.plan


class FakeRecovery:
    async def recover(self, task: ExecutionTask, error: Exception | str) -> RecoveryDecision:
        return RecoveryDecision(action=RecoveryAction.RETRY, reason="retry")


class MetricAgent:
    async def execute(self, task: ExecutionTask) -> TaskResult:
        return TaskResult(
            task_id=task.id,
            success=True,
            output={
                "code_quality_score": 92,
                "verification_score": 96,
                "test_coverage": 88,
                "resource_usage": 35,
            },
        )


@pytest.fixture
async def memory_manager(tmp_path: Path) -> MemoryManager:
    store = SQLiteMemoryStore(tmp_path / "learning.db")
    await store.open()
    manager = MemoryManager(store)
    yield manager
    await store.close()


async def test_engine_scores_persists_and_publishes_learning(memory_manager: MemoryManager) -> None:
    event_bus = EventBus()
    events = []
    await event_bus.subscribe("*", lambda event: events.append(event))
    engine = RewardLearningEngine(memory_manager=memory_manager, event_bus=event_bus)
    started_at = datetime.now(UTC)
    task = ExecutionTask(
        id="build",
        title="Build Apex",
        description="Build Apex",
        agent="salesforce_engineer",
        acceptance_criteria=["tests pass"],
        deliverables=["metadata"],
        attempts=1,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        output={
            "code_quality_score": 94,
            "verification_score": 97,
            "test_coverage": 91,
            "resource_usage": 30,
        },
    )
    task.status = TaskStatus.SUCCESS
    report = ExecutionReport(
        workflow_id="wf-learning",
        request="Build",
        status=WorkflowStatus.SUCCESS,
        plan_id="plan-1",
        total_tasks=1,
        successful_tasks=1,
        failed_tasks=0,
        tasks=[task],
        started_at=started_at,
        completed_at=datetime.now(UTC),
        summary="done",
    )

    result = await engine.evaluate_execution_report(report)

    assert result.workflow_score.score > 80
    assert result.agent_scores[0].entity_id == "salesforce_engineer"
    assert result.trace["persisted_record_ids"]
    reward_records, reward_total = await memory_manager.store.list_by_category(
        MemoryCategory.REWARD_RECORD
    )
    metric_records, metric_total = await memory_manager.store.list_by_category(
        MemoryCategory.EXECUTION_METRIC
    )
    assert reward_total >= 2
    assert metric_total > 0
    assert reward_records[0].metadata.custom["reward_score"]["entity_type"] in {
        "agent",
        "workflow",
    }
    assert "reward.updated" in [event.name for event in events]
    assert "reward_learning.evaluation.completed" in [event.name for event in events]


async def test_engine_recommends_better_historical_strategy(memory_manager: MemoryManager) -> None:
    engine = RewardLearningEngine(memory_manager=memory_manager, event_bus=EventBus())
    baseline = StrategyPerformance(
        strategy_type=StrategyType.STANDARD,
        agent_name="worker",
        total_uses=5,
        successful_uses=3,
        average_execution_time_seconds=300,
        average_retry_count=2,
        average_quality_score=70,
        success_rate=0.6,
        confidence=0.7,
    )
    candidate = StrategyPerformance(
        strategy_type=StrategyType.CONSERVATIVE,
        agent_name="worker",
        total_uses=5,
        successful_uses=5,
        average_execution_time_seconds=150,
        average_retry_count=0,
        average_quality_score=90,
        success_rate=1.0,
        confidence=0.9,
    )

    comparison = engine.compare_strategies(baseline, candidate)

    assert comparison.recommendation == "adopt_candidate"
    assert comparison.score_delta > 0


async def test_orchestrator_invokes_reward_learning_engine(tmp_path: Path) -> None:
    store = SQLiteMemoryStore(tmp_path / "orchestrator-learning.db")
    await store.open()
    memory_manager = MemoryManager(store)
    event_bus = EventBus()
    events = []
    await event_bus.subscribe("*", lambda event: events.append(event))
    engine = RewardLearningEngine(memory_manager=memory_manager, event_bus=event_bus)
    plan = ExecutionPlan(
        objective="Build",
        tasks=[
            ExecutionTask(
                id="task",
                title="Task",
                description="Task",
                agent="worker",
                acceptance_criteria=["verified"],
                deliverables=["code"],
            )
        ],
    )
    registry = AgentRegistry()
    registry.register("worker", MetricAgent())
    orchestrator = OrchestratorAgent(
        planner=FakePlanner(plan),
        recovery_agent=FakeRecovery(),
        agent_registry=registry,
        state_manager=StateManager(tmp_path / "state.json"),
        event_bus=event_bus,
        reward_learning_engine=engine,
    )

    report = await orchestrator.run("Build", workflow_id="wf-auto")

    assert report.status == WorkflowStatus.SUCCESS
    event_names = [event.name for event in events]
    assert "orchestrator.workflow.learned" in event_names
    assert "reward.updated" in event_names
    _, reward_total = await memory_manager.store.list_by_category(MemoryCategory.REWARD_RECORD)
    assert reward_total >= 2
    await store.close()
