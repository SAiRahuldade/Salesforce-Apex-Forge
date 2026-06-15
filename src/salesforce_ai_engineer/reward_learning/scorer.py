"""Reward scoring engine."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from salesforce_ai_engineer.reward_learning.models import (
    RewardScore,
    AgentPerformanceMetric,
    WorkflowMetrics,
    MetricType,
    RewardStatus,
)

UTC = ZoneInfo("UTC")
logger = logging.getLogger(__name__)


class ScoringPolicy:
    """Configurable scoring policy."""

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialize scoring policy.

        Args:
            weights: Optional custom weights for metrics
        """
        # Default weights for workflow scoring
        self.default_weights = {
            "planning_quality": 0.15,
            "code_quality": 0.25,
            "verification": 0.20,
            "deployment": 0.15,
            "recovery": 0.10,
            "execution_efficiency": 0.10,
            "reliability": 0.05,
        }

        self.weights = weights or self.default_weights

    def normalize_weights(self) -> Dict[str, float]:
        """Normalize weights to sum to 1.0."""
        total = sum(self.weights.values())
        if total == 0:
            return self.default_weights

        return {k: v / total for k, v in self.weights.items()}


class RewardScorer:
    """Calculates reward scores for agents and workflows."""

    def __init__(self, policy: Optional[ScoringPolicy] = None):
        """Initialize reward scorer.

        Args:
            policy: Scoring policy (uses defaults if not provided)
        """
        self.policy = policy or ScoringPolicy()
        self.logger = logger

    async def score_agent(
        self,
        agent_name: str,
        metrics: list[AgentPerformanceMetric],
        period: str = "daily",
    ) -> RewardScore:
        """Calculate reward score for an agent.

        Args:
            agent_name: Name of agent
            metrics: List of performance metrics
            period: Evaluation period

        Returns:
            RewardScore for the agent
        """
        self.logger.info(f"Scoring agent: {agent_name}")

        if not metrics:
            return RewardScore(
                entity_type="agent",
                entity_id=agent_name,
                score=50.0,
                confidence=0.5,
                period=period,
            )

        # Calculate base score from metrics
        metric_scores = {}
        for metric in metrics:
            normalized_score = self._normalize_metric_score(
                metric.value, metric.metric_type
            )
            metric_scores[metric.metric_type.value] = normalized_score

        # Calculate weighted score
        total_score = self._calculate_weighted_score(metric_scores)

        # Calculate confidence based on number of metrics
        confidence = min(1.0, len(metrics) / 5)

        # Build factors dictionary
        factors = {
            metric_type: metric_scores.get(metric_type, 0.0)
            for metric_type in [mt.value for mt in MetricType]
        }

        return RewardScore(
            entity_type="agent",
            entity_id=agent_name,
            score=total_score,
            confidence=confidence,
            factors=factors,
            weights=self.policy.normalize_weights(),
            period=period,
        )

    async def score_workflow(
        self,
        workflow_id: str,
        metrics: WorkflowMetrics,
        period: str = "all_time",
    ) -> RewardScore:
        """Calculate reward score for a workflow.

        Args:
            workflow_id: ID of workflow
            metrics: Workflow metrics
            period: Evaluation period

        Returns:
            RewardScore for the workflow
        """
        self.logger.info(f"Scoring workflow: {workflow_id}")

        # Calculate component scores
        planning_score = metrics.planning_quality_score
        code_score = metrics.code_quality_score
        verification_score = metrics.verification_score
        deployment_score = self._deployment_score(
            metrics.deployment_success_rate
        )
        recovery_score = self._recovery_score(metrics.recovery_effectiveness)
        efficiency_score = self._efficiency_score(
            metrics.execution_time_seconds, metrics.total_retries
        )
        reliability_score = self._reliability_score(
            metrics.is_workflow_successful, metrics.total_retries
        )

        # Combine scores using weighted policy
        factors = {
            "planning_quality": planning_score,
            "code_quality": code_score,
            "verification": verification_score,
            "deployment": deployment_score,
            "recovery": recovery_score,
            "execution_efficiency": efficiency_score,
            "reliability": reliability_score,
        }

        weights = self.policy.normalize_weights()
        total_score = sum(
            factors.get(k, 0) * weights.get(k, 0)
            for k in weights.keys()
        )

        # Calculate confidence
        confidence = self._calculate_confidence(metrics)

        return RewardScore(
            entity_type="workflow",
            entity_id=workflow_id,
            score=total_score,
            confidence=confidence,
            factors=factors,
            weights=weights,
            period=period,
        )

    def _normalize_metric_score(
        self,
        value: float,
        metric_type: MetricType,
    ) -> float:
        """Normalize metric value to 0-100 score.

        Args:
            value: Metric value
            metric_type: Type of metric

        Returns:
            Normalized score 0-100
        """
        if metric_type == MetricType.EXECUTION_TIME:
            # Lower is better, max 3600 seconds
            return max(0, 100 - (value / 3600 * 100))

        elif metric_type == MetricType.RETRY_COUNT:
            # Lower is better, max 10 retries
            return max(0, 100 - (value / 10 * 100))

        elif metric_type == MetricType.RESOURCE_USAGE:
            # Lower is better, 100% usage = 0 score
            return 100 - value

        else:
            # For percentage-based metrics (0-1 or 0-100)
            if value <= 1.0:
                return value * 100
            else:
                return value

    def _calculate_weighted_score(
        self,
        metric_scores: Dict[str, float],
    ) -> float:
        """Calculate weighted score from metrics.

        Args:
            metric_scores: Dictionary of metric type -> score

        Returns:
            Weighted total score
        """
        weights = self.policy.normalize_weights()

        # Map metric types to policy weights
        mapping = {
            "planning_quality": "planning_quality",
            "code_quality": "code_quality",
            "verification_score": "verification",
            "recovery_effectiveness": "recovery",
        }

        total = 0.0
        applied_weight = 0.0
        for metric_key, score in metric_scores.items():
            weight_key = mapping.get(metric_key, metric_key)
            weight = weights.get(weight_key, 0.0)
            total += score * weight
            applied_weight += weight

        if applied_weight == 0:
            return 50.0
        return total / applied_weight

    def _deployment_score(self, success_rate: float) -> float:
        """Calculate deployment score.

        Args:
            success_rate: Deployment success rate (0-1)

        Returns:
            Deployment score (0-100)
        """
        return success_rate * 100

    def _recovery_score(self, effectiveness: float) -> float:
        """Calculate recovery effectiveness score.

        Args:
            effectiveness: Recovery effectiveness (0-1)

        Returns:
            Recovery score (0-100)
        """
        return effectiveness * 100

    def _efficiency_score(
        self,
        execution_time_seconds: float,
        retry_count: int,
    ) -> float:
        """Calculate efficiency score.

        Args:
            execution_time_seconds: Total execution time
            retry_count: Number of retries

        Returns:
            Efficiency score (0-100)
        """
        # Lower time and retries = higher score
        time_factor = max(0, 100 - (execution_time_seconds / 3600 * 50))
        retry_factor = max(0, 100 - (retry_count / 10 * 50))

        return (time_factor + retry_factor) / 2

    def _reliability_score(
        self,
        is_successful: bool,
        retry_count: int,
    ) -> float:
        """Calculate reliability score.

        Args:
            is_successful: Whether workflow succeeded
            retry_count: Number of retries

        Returns:
            Reliability score (0-100)
        """
        base_score = 100 if is_successful else 50

        # Penalize for retries
        retry_penalty = min(50, retry_count * 5)

        return max(0, base_score - retry_penalty)

    def _calculate_confidence(self, metrics: WorkflowMetrics) -> float:
        """Calculate confidence in workflow score.

        Args:
            metrics: Workflow metrics

        Returns:
            Confidence (0-1)
        """
        # Higher confidence for successful workflows with good metrics
        factors = [
            1.0 if metrics.is_workflow_successful else 0.5,
            min(1.0, metrics.test_coverage_percentage / 75),
            1.0 if metrics.total_retries < 3 else 0.7,
            min(1.0, metrics.deployment_success_rate),
        ]

        return sum(factors) / len(factors)

    async def batch_score_workflows(
        self,
        workflows: Dict[str, WorkflowMetrics],
        period: str = "daily",
    ) -> Dict[str, RewardScore]:
        """Score multiple workflows.

        Args:
            workflows: Dictionary of workflow_id -> metrics
            period: Evaluation period

        Returns:
            Dictionary of workflow_id -> reward_score
        """
        results = {}

        for workflow_id, metrics in workflows.items():
            score = await self.score_workflow(workflow_id, metrics, period)
            results[workflow_id] = score

        return results

    def get_policy(self) -> Dict[str, float]:
        """Get current scoring policy.

        Returns:
            Dictionary of weights
        """
        return self.policy.normalize_weights()

    def set_policy(self, weights: Dict[str, float]) -> None:
        """Update scoring policy.

        Args:
            weights: New weights
        """
        self.policy = ScoringPolicy(weights)
        self.logger.info(f"Scoring policy updated: {self.policy.normalize_weights()}")
