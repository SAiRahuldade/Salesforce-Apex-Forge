"""Reward & Learning Engine orchestration service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from salesforce_ai_engineer.agent.models import ExecutionReport, WorkflowStatus
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.models.domain import EventPriority, LifecycleEvent
from salesforce_ai_engineer.reward_learning.analyzer import LearningAnalyzer
from salesforce_ai_engineer.reward_learning.evaluator import WorkflowEvaluator
from salesforce_ai_engineer.reward_learning.models import (
    AgentPerformanceMetric,
    FailurePattern,
    LearningEvaluationResult,
    MetricType,
    PerformanceDashboard,
    PerformanceTrend,
    RewardScore,
    StrategyComparison,
    StrategyPerformance,
    StrategyRecommendation,
)
from salesforce_ai_engineer.reward_learning.repository import RewardLearningRepository
from salesforce_ai_engineer.reward_learning.scorer import RewardScorer, ScoringPolicy

logger = logging.getLogger(__name__)


class RewardLearningEngine:
    """Evaluates completed workflows and turns execution history into learning signals."""

    def __init__(
        self,
        memory_manager: MemoryManager,
        event_bus: EventBus,
        scorer: RewardScorer | None = None,
        evaluator: WorkflowEvaluator | None = None,
        analyzer: LearningAnalyzer | None = None,
        repository: RewardLearningRepository | None = None,
    ) -> None:
        self.memory_manager = memory_manager
        self.event_bus = event_bus
        self.scorer = scorer or RewardScorer()
        self.evaluator = evaluator or WorkflowEvaluator(self.scorer)
        self.analyzer = analyzer or LearningAnalyzer()
        self.repository = repository or RewardLearningRepository(memory_manager)
        self.logger = logger

    async def evaluate_execution_report(
        self,
        report: ExecutionReport,
        *,
        execution_data: dict[str, Any] | None = None,
    ) -> LearningEvaluationResult:
        """Evaluate a completed workflow report and persist traceable learning records."""

        await self._ensure_memory_open()
        data = execution_data or self.execution_data_from_report(report)
        await self._publish(
            "reward_learning.evaluation.started",
            {"workflow_id": report.workflow_id, "agent_count": len(data.get("agents", {}))},
            workflow_id=report.workflow_id,
        )

        workflow_metrics = await self.evaluator.evaluate_workflow(report.workflow_id, data)
        workflow_score = await self.scorer.score_workflow(report.workflow_id, workflow_metrics)
        agent_metrics = await self._evaluate_agents(data)
        agent_scores = [
            await self.scorer.score_agent(agent_name, metrics, period="all_time")
            for agent_name, metrics in agent_metrics.items()
        ]
        analytics = await self.evaluator.generate_analytics(report.workflow_id, data)
        strategy_performance = self.analyzer.build_strategy_performance(
            workflow_metrics,
            agent_metrics,
            data,
        )
        historical_strategy_performance = await self.repository.historical_strategy_performance()
        failure_patterns = self.analyzer.detect_failure_patterns(report.workflow_id, data)
        recommendations = self.analyzer.recommend_strategies(
            strategy_performance,
            historical_strategy_performance,
        )
        historical_scores = await self.repository.reward_scores()
        trends = self.analyzer.build_trends(
            [*historical_scores, workflow_score, *agent_scores],
            period="all_time",
        )
        persisted_records = await self.repository.persist_workflow_evaluation(
            workflow_metrics,
            workflow_score,
            agent_scores,
            agent_metrics,
            analytics,
            strategy_performance,
            failure_patterns,
            recommendations,
        )
        trace = self._build_trace(
            workflow_score,
            agent_scores,
            persisted_records,
            data,
        )
        result = LearningEvaluationResult(
            workflow_id=report.workflow_id,
            workflow_metrics=workflow_metrics,
            workflow_score=workflow_score,
            agent_scores=agent_scores,
            agent_metrics=agent_metrics,
            analytics=analytics,
            strategy_performance=strategy_performance,
            failure_patterns=failure_patterns,
            recommendations=recommendations,
            trends=trends,
            trace=trace,
        )

        await self._publish(
            LifecycleEvent.REWARD_UPDATED,
            {
                "workflow_id": report.workflow_id,
                "workflow_score": workflow_score.score,
                "confidence": workflow_score.confidence,
                "agent_scores": {score.entity_id: score.score for score in agent_scores},
                "recommendation_count": len(recommendations),
                "failure_pattern_count": len(failure_patterns),
                "trace": trace,
            },
            workflow_id=report.workflow_id,
            priority=EventPriority.HIGH,
        )
        await self._publish(
            "reward_learning.evaluation.completed",
            result.model_dump(mode="json"),
            workflow_id=report.workflow_id,
        )
        return result

    async def recommended_strategy_for_agent(
        self,
        agent_name: str,
        current_strategy: str = "standard",
    ) -> StrategyRecommendation | None:
        """Return the best historical recommendation before a future workflow chooses a strategy."""

        history = await self.repository.historical_strategy_performance(agent_name=agent_name)
        if not history:
            return None
        current = next(
            (item for item in reversed(history) if item.strategy_type.value == current_strategy),
            history[-1],
        )
        return next(iter(self.analyzer.recommend_strategies([current], history)), None)

    async def leaderboard(self, period: str = "all_time") -> list:
        """Generate an agent leaderboard from memory-backed reward history."""

        scores = await self.repository.reward_scores()
        trends = self.analyzer.build_trends(scores, period=period)
        return self.analyzer.build_leaderboard(scores, trends, period)

    async def dashboard(self, period: str = "all_time") -> PerformanceDashboard:
        """Generate a dashboard snapshot from persisted learning history."""

        scores = await self.repository.reward_scores()
        trends = self.analyzer.build_trends(scores, period=period)
        strategies = await self.repository.historical_strategy_performance()
        return self.analyzer.build_dashboard(
            scores=scores,
            trends=trends,
            strategies=strategies,
            failures=[],
            recommendations=[],
            period=period,
        )

    def compare_strategies(
        self,
        baseline: StrategyPerformance,
        candidate: StrategyPerformance,
    ) -> StrategyComparison:
        """Compare two strategies without side effects."""

        return self.analyzer.compare_strategies(baseline, candidate)

    def set_scoring_policy(self, weights: dict[str, float]) -> None:
        """Update configurable scoring weights."""

        self.scorer.set_policy(weights)

    def get_scoring_policy(self) -> dict[str, float]:
        """Return active normalized scoring weights."""

        return self.scorer.get_policy()

    def execution_data_from_report(self, report: ExecutionReport) -> dict[str, Any]:
        """Convert an immutable execution report into evaluator-friendly data."""

        duration = max(0.0, (report.completed_at - report.started_at).total_seconds())
        total_retries = sum(max(0, task.attempts - 1) for task in report.tasks)
        agents: dict[str, dict[str, Any]] = {}
        for task in report.tasks:
            task_duration = 0.0
            if task.started_at and task.completed_at:
                task_duration = max(0.0, (task.completed_at - task.started_at).total_seconds())
            output = task.output or {}
            agent_data = agents.setdefault(
                task.agent,
                {
                    "planning_quality": 0.0,
                    "code_quality": 0.0,
                    "verification_score": 0.0,
                    "execution_time": 0.0,
                    "attempts": 0,
                    "successes": 0,
                    "failures": 0,
                    "errors": [],
                    "recovery_attempts": 0,
                    "successful_recoveries": 0,
                    "strategy": task.metadata.get("strategy", "standard"),
                },
            )
            agent_data["planning_quality"] += self._planning_quality(task)
            agent_data["code_quality"] += self._output_score(output, "code_quality_score", 80.0)
            agent_data["verification_score"] += self._output_score(output, "verification_score", 85.0)
            agent_data["execution_time"] += task_duration
            agent_data["attempts"] += task.attempts
            agent_data["successes"] += 1 if task.status.value == "success" else 0
            agent_data["failures"] += 1 if task.status.value == "failed" else 0
            agent_data["recovery_attempts"] += max(0, task.attempts - 1)
            agent_data["successful_recoveries"] += 1 if task.attempts > 1 and task.status.value == "success" else 0
            if task.error:
                agent_data["errors"].append(task.error)

        for agent_data in agents.values():
            denominator = max(1, agent_data["successes"] + agent_data["failures"])
            agent_data["planning_quality"] /= denominator
            agent_data["code_quality"] /= denominator
            agent_data["verification_score"] /= denominator
            agent_data["success"] = agent_data["failures"] == 0

        verification_scores = [
            self._output_score(task.output or {}, "verification_score", 85.0)
            for task in report.tasks
        ]
        deployment_reports = report.deployment_reports
        deployment_success = (
            sum(1 for item in deployment_reports if item.status.value in {"deployed", "validated"})
            / len(deployment_reports)
            if deployment_reports
            else (1.0 if report.status == WorkflowStatus.SUCCESS else 0.0)
        )
        recovery_attempts = sum(data["recovery_attempts"] for data in agents.values())
        successful_recoveries = sum(data["successful_recoveries"] for data in agents.values())
        return {
            "planning_quality_score": self._workflow_planning_quality(report),
            "code_quality_score": self._average_output_score(report, "code_quality_score", 80.0),
            "verification_score": sum(verification_scores) / len(verification_scores) if verification_scores else 85.0,
            "deployment_success": deployment_success,
            "recovery_attempts": recovery_attempts,
            "successful_recoveries": successful_recoveries,
            "total_time": duration,
            "planning_time": 0.0,
            "execution_time": duration,
            "verification_time": 0.0,
            "deployment_time": 0.0,
            "total_retries": total_retries,
            "test_coverage": self._average_output_score(report, "test_coverage", 80.0),
            "resource_usage": self._average_output_score(report, "resource_usage", 50.0),
            "is_successful": report.status == WorkflowStatus.SUCCESS,
            "total_failures": report.failed_tasks,
            "human_interventions": 1 if report.escalated else 0,
            "automated_decisions": max(1, report.total_tasks + recovery_attempts),
            "decision_quality": 100.0 if report.status == WorkflowStatus.SUCCESS else 60.0,
            "resource_efficiency": max(0.0, 100.0 - self._average_output_score(report, "resource_usage", 50.0)),
            "agents": agents,
        }

    async def _evaluate_agents(
        self,
        execution_data: dict[str, Any],
    ) -> dict[str, list[AgentPerformanceMetric]]:
        agent_metrics: dict[str, list[AgentPerformanceMetric]] = {}
        for agent_name in execution_data.get("agents", {}):
            metrics = await self.evaluator.evaluate_agent_performance(agent_name, execution_data)
            agent_data = execution_data.get("agents", {}).get(agent_name, {})
            if "verification_score" in agent_data:
                now = datetime.now(UTC)
                metrics.append(
                    AgentPerformanceMetric(
                        agent_name=agent_name,
                        metric_type=MetricType.VERIFICATION_SCORE,
                        value=agent_data["verification_score"],
                        confidence=0.85,
                        period_start=now,
                        period_end=now,
                    )
                )
            agent_metrics[agent_name] = metrics
        return agent_metrics

    def _build_trace(
        self,
        workflow_score: RewardScore,
        agent_scores: list[RewardScore],
        persisted_records: list[str],
        execution_data: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "policy_weights": self.scorer.get_policy(),
            "workflow_factors": workflow_score.factors,
            "agent_factors": {score.entity_id: score.factors for score in agent_scores},
            "persisted_record_ids": persisted_records,
            "input_keys": sorted(execution_data.keys()),
            "explainability": "Scores are weighted deterministic evaluations of execution metrics; no model weights were modified.",
        }

    async def _ensure_memory_open(self) -> None:
        if not await self.memory_manager.health_check():
            await self.memory_manager.store.open()

    async def _publish(
        self,
        event: LifecycleEvent | str,
        payload: dict[str, Any],
        *,
        workflow_id: str,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        await self.event_bus.publish(
            event,
            payload,
            workflow_id=workflow_id,
            priority=priority,
            source="reward_learning_engine",
        )

    def _workflow_planning_quality(self, report: ExecutionReport) -> float:
        if report.total_tasks == 0:
            return 0.0
        ready_tasks = sum(1 for task in report.tasks if not task.missing_information)
        dependency_score = 100.0 if all(task.id not in task.dependencies for task in report.tasks) else 70.0
        acceptance_score = sum(1 for task in report.tasks if task.acceptance_criteria) / report.total_tasks * 100.0
        readiness_score = ready_tasks / report.total_tasks * 100.0
        return (dependency_score * 0.4) + (acceptance_score * 0.3) + (readiness_score * 0.3)

    def _planning_quality(self, task: Any) -> float:
        score = 70.0
        if task.acceptance_criteria:
            score += 15.0
        if task.deliverables:
            score += 10.0
        if task.missing_information:
            score -= 20.0
        return max(0.0, min(100.0, score))

    def _average_output_score(
        self,
        report: ExecutionReport,
        key: str,
        default: float,
    ) -> float:
        values = [self._output_score(task.output or {}, key, default) for task in report.tasks]
        return sum(values) / len(values) if values else default

    def _output_score(self, output: dict[str, Any], key: str, default: float) -> float:
        value = output.get(key, output.get("metrics", {}).get(key, default))
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        if key in {"deployment_success"} and numeric <= 1.0:
            return numeric
        if key == "resource_usage":
            return max(0.0, min(100.0, numeric))
        return max(0.0, min(100.0, numeric * 100.0 if numeric <= 1.0 else numeric))


def build_reward_learning_engine(
    memory_manager: MemoryManager,
    event_bus: EventBus,
    weights: dict[str, float] | None = None,
) -> RewardLearningEngine:
    """Factory used by infrastructure bootstrap."""

    scorer = RewardScorer(ScoringPolicy(weights))
    return RewardLearningEngine(memory_manager=memory_manager, event_bus=event_bus, scorer=scorer)
