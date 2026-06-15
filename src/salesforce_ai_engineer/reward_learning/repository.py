"""Memory-backed repository for reward and learning records."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.models.domain.memory import MemoryCategory, MemoryMetadata, create_memory_record
from salesforce_ai_engineer.reward_learning.models import (
    AgentPerformanceMetric,
    ExecutionAnalytics,
    FailurePattern,
    RewardScore,
    StrategyPerformance,
    StrategyRecommendation,
    WorkflowMetrics,
)

logger = logging.getLogger(__name__)


class RewardLearningRepository:
    """Persists and retrieves learning artifacts through the Memory Agent."""

    CREATED_BY = "reward_learning_engine"

    def __init__(self, memory_manager: MemoryManager) -> None:
        self.memory_manager = memory_manager
        self.logger = logger

    async def persist_workflow_evaluation(
        self,
        workflow_metrics: WorkflowMetrics,
        workflow_score: RewardScore,
        agent_scores: list[RewardScore],
        agent_metrics: dict[str, list[AgentPerformanceMetric]],
        analytics: ExecutionAnalytics,
        strategy_performance: list[StrategyPerformance],
        failure_patterns: list[FailurePattern],
        recommendations: list[StrategyRecommendation],
    ) -> list[str]:
        """Persist all records produced by one learning pass."""

        record_ids: list[str] = []
        record_ids.append(await self._store_reward_score(workflow_metrics.workflow_id, None, workflow_score))
        record_ids.append(await self._store_execution_metric("workflow_reward_score", workflow_score.score, "score", workflow_metrics.workflow_id))
        record_ids.extend(await self._store_workflow_metrics(workflow_metrics))
        record_ids.extend(await self._store_analytics(analytics))

        for score in agent_scores:
            record_ids.append(await self._store_reward_score(workflow_metrics.workflow_id, score.entity_id, score))
            record_ids.append(await self._store_execution_metric("agent_reward_score", score.score, "score", workflow_metrics.workflow_id, score.entity_id))

        for metrics in agent_metrics.values():
            for metric in metrics:
                record_ids.append(
                    await self._store_execution_metric(
                        metric.metric_type.value,
                        metric.value,
                        "score" if metric.metric_type.value.endswith("quality") else "value",
                        workflow_metrics.workflow_id,
                        metric.agent_name,
                        {
                            "confidence": metric.confidence,
                            "context": metric.context,
                            "period_start": metric.period_start.isoformat(),
                            "period_end": metric.period_end.isoformat(),
                        },
                    )
                )

        for item in strategy_performance:
            record_ids.append(
                await self._store_execution_metric(
                    "strategy_effectiveness",
                    item.effectiveness_score,
                    "ratio",
                    workflow_metrics.workflow_id,
                    item.agent_name,
                    item.model_dump(mode="json"),
                )
            )

        for pattern in failure_patterns:
            record_ids.append(
                await self.memory_manager.store_known_error(
                    error_type=pattern.failure_category,
                    error_message=pattern.pattern_description,
                    severity=pattern.pattern_severity,
                    created_by=self.CREATED_BY,
                    content=pattern.model_dump(mode="json"),
                    metadata=self._metadata(pattern.confidence, {"kind": "failure_pattern"}),
                )
            )

        for recommendation in recommendations:
            record_ids.append(
                await self._store_execution_metric(
                    "strategy_recommendation",
                    recommendation.improvement_potential,
                    "percent",
                    workflow_metrics.workflow_id,
                    recommendation.agent_name,
                    recommendation.model_dump(mode="json"),
                )
            )

        return record_ids

    async def reward_scores(self, limit: int = 1000) -> list[RewardScore]:
        """Load recent reward scores from memory."""

        records, _ = await self.memory_manager.store.list_by_category(
            MemoryCategory.REWARD_RECORD,
            limit=limit,
        )
        scores: list[RewardScore] = []
        for record in records:
            raw = record.metadata.custom.get("reward_score") if hasattr(record, "metadata") else None
            if isinstance(raw, dict):
                scores.append(RewardScore.model_validate(raw))
        return scores

    async def execution_metrics(self, limit: int = 1000) -> list[Any]:
        """Load recent execution metric records from memory."""

        records, _ = await self.memory_manager.store.list_by_category(
            MemoryCategory.EXECUTION_METRIC,
            limit=limit,
        )
        return records

    async def historical_strategy_performance(
        self,
        agent_name: str | None = None,
        limit: int = 1000,
    ) -> list[StrategyPerformance]:
        """Load historical strategy effectiveness records."""

        records = await self.execution_metrics(limit)
        strategies: list[StrategyPerformance] = []
        for record in records:
            if getattr(record, "metric_name", None) != "strategy_effectiveness":
                continue
            if agent_name and getattr(record, "agent_name", None) != agent_name:
                continue
            raw = getattr(record, "metadata", None).custom.get("details", {}) if getattr(record, "metadata", None) else {}
            if isinstance(raw, dict):
                strategies.append(StrategyPerformance.model_validate(raw))
        return strategies

    async def _store_reward_score(
        self,
        workflow_id: str,
        agent_name: str | None,
        score: RewardScore,
    ) -> str:
        normalized = max(-1.0, min(1.0, (score.score / 50.0) - 1.0))
        reason = self._reward_reason(score)
        record = create_memory_record(
            category=MemoryCategory.REWARD_RECORD,
            title=f"Reward: {score.entity_type} {score.entity_id}",
            created_by=self.CREATED_BY,
            agent_name=agent_name or score.entity_id,
            task_id=workflow_id,
            task_type=score.entity_type,
            reward_amount=normalized,
            reason=reason,
            timestamp=score.calculated_at,
            metadata=self._metadata(
                score.confidence,
                {
                    "kind": "reward_score",
                    "workflow_id": workflow_id,
                    "agent_name": agent_name,
                    "reward_score": score.model_dump(mode="json"),
                    "explanation": reason,
                },
            ),
        )
        return await self.memory_manager.store.create(record)

    async def _store_workflow_metrics(self, metrics: WorkflowMetrics) -> list[str]:
        values = {
            "planning_quality_score": metrics.planning_quality_score,
            "code_quality_score": metrics.code_quality_score,
            "verification_score": metrics.verification_score,
            "deployment_success_rate": metrics.deployment_success_rate,
            "recovery_effectiveness": metrics.recovery_effectiveness,
            "execution_time_seconds": metrics.execution_time_seconds,
            "total_retries": float(metrics.total_retries),
            "test_coverage_percentage": metrics.test_coverage_percentage,
            "resource_usage_percent": metrics.resource_usage_percent,
        }
        return [
            await self._store_execution_metric(
                name,
                value,
                "seconds" if name.endswith("seconds") else "count" if name == "total_retries" else "score",
                metrics.workflow_id,
                details={"workflow_metrics_id": metrics.id},
            )
            for name, value in values.items()
        ]

    async def _store_analytics(self, analytics: ExecutionAnalytics) -> list[str]:
        values = {
            "total_failures": analytics.total_failures,
            "recovery_attempts": analytics.recovery_attempts,
            "successful_recoveries": analytics.successful_recoveries,
            "human_interventions": analytics.human_interventions,
            "automated_decisions": analytics.automated_decisions,
            "decision_quality_average": analytics.decision_quality_average,
            "resource_efficiency_score": analytics.resource_efficiency_score,
        }
        return [
            await self._store_execution_metric(
                name,
                float(value),
                "count" if name.endswith("s") or name == "total_failures" else "score",
                analytics.workflow_id,
                details={"analytics": analytics.model_dump(mode="json")},
            )
            for name, value in values.items()
        ]

    async def _store_execution_metric(
        self,
        metric_name: str,
        metric_value: float,
        unit: str,
        workflow_id: str,
        agent_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> str:
        now = datetime.utcnow()
        record = create_memory_record(
            category=MemoryCategory.EXECUTION_METRIC,
            title=f"Metric: {metric_name}",
            created_by=self.CREATED_BY,
            metric_name=metric_name,
            metric_value=float(metric_value),
            unit=unit,
            agent_name=agent_name,
            execution_id=workflow_id,
            timewindow_start=now,
            timewindow_end=now,
            tags_dict={
                "workflow_id": workflow_id,
                "agent_name": agent_name or "",
                "source": self.CREATED_BY,
            },
            metadata=self._metadata(
                1.0,
                {
                    "kind": "execution_metric",
                    "workflow_id": workflow_id,
                    "agent_name": agent_name,
                    "details": details or {},
                },
            ),
        )
        return await self.memory_manager.store.create(record)

    def _metadata(self, confidence: float, custom: dict[str, Any]) -> MemoryMetadata:
        return MemoryMetadata(
            source=self.CREATED_BY,
            confidence=max(0.0, min(1.0, confidence)),
            relevance=1.0,
            priority=7,
            custom=custom,
        )

    def _reward_reason(self, score: RewardScore) -> str:
        important = sorted(score.factors.items(), key=lambda item: item[1], reverse=True)[:3]
        factor_text = ", ".join(f"{name}={value:.1f}" for name, value in important)
        return (
            f"{score.entity_type} {score.entity_id} scored {score.score:.1f}/100 "
            f"with confidence {score.confidence:.2f}; strongest factors: {factor_text}."
        )
