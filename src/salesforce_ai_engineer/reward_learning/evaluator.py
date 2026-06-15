"""Evaluation engine for completed workflows."""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from zoneinfo import ZoneInfo

from salesforce_ai_engineer.reward_learning.models import (
    WorkflowMetrics,
    AgentPerformanceMetric,
    MetricType,
    ExecutionAnalytics,
)
from salesforce_ai_engineer.reward_learning.scorer import RewardScorer

UTC = ZoneInfo("UTC")
logger = logging.getLogger(__name__)


class WorkflowEvaluator:
    """Evaluates completed workflows to generate metrics."""

    def __init__(self, scorer: Optional[RewardScorer] = None):
        """Initialize evaluator.

        Args:
            scorer: RewardScorer instance
        """
        self.scorer = scorer or RewardScorer()
        self.logger = logger

    async def evaluate_workflow(
        self,
        workflow_id: str,
        execution_data: Dict[str, Any],
    ) -> WorkflowMetrics:
        """Evaluate a completed workflow.

        Args:
            workflow_id: ID of workflow
            execution_data: Dictionary with execution details

        Returns:
            WorkflowMetrics with evaluation results
        """
        self.logger.info(f"Evaluating workflow: {workflow_id}")

        # Extract metrics from execution data
        planning_quality = self._extract_planning_quality(execution_data)
        code_quality = self._extract_code_quality(execution_data)
        verification_score = self._extract_verification_score(execution_data)
        deployment_success = self._extract_deployment_success(execution_data)
        recovery_effectiveness = self._extract_recovery_effectiveness(execution_data)
        execution_time = self._extract_execution_time(execution_data)
        total_retries = self._extract_retry_count(execution_data)
        test_coverage = self._extract_test_coverage(execution_data)
        resource_usage = self._extract_resource_usage(execution_data)
        is_successful = self._determine_success(execution_data)

        metrics = WorkflowMetrics(
            workflow_id=workflow_id,
            planning_quality_score=planning_quality,
            code_quality_score=code_quality,
            verification_score=verification_score,
            deployment_success_rate=deployment_success,
            recovery_effectiveness=recovery_effectiveness,
            execution_time_seconds=execution_time,
            total_retries=total_retries,
            test_coverage_percentage=test_coverage,
            resource_usage_percent=resource_usage,
            is_workflow_successful=is_successful,
        )

        self.logger.info(
            f"Workflow evaluated: success={is_successful}, "
            f"quality={code_quality:.1f}, time={execution_time:.1f}s"
        )

        return metrics

    async def evaluate_agent_performance(
        self,
        agent_name: str,
        execution_data: Dict[str, Any],
    ) -> List[AgentPerformanceMetric]:
        """Evaluate agent performance during workflow execution.

        Args:
            agent_name: Name of agent
            execution_data: Execution details

        Returns:
            List of performance metrics for the agent
        """
        self.logger.info(f"Evaluating agent: {agent_name}")

        metrics = []

        # Planning quality metric
        planning_score = self._extract_agent_planning_quality(
            agent_name, execution_data
        )
        metrics.append(
            AgentPerformanceMetric(
                agent_name=agent_name,
                metric_type=MetricType.PLANNING_QUALITY,
                value=planning_score,
                confidence=0.8,
                period_start=datetime.now(UTC),
                period_end=datetime.now(UTC),
            )
        )

        # Code quality metric
        code_score = self._extract_agent_code_quality(agent_name, execution_data)
        metrics.append(
            AgentPerformanceMetric(
                agent_name=agent_name,
                metric_type=MetricType.CODE_QUALITY,
                value=code_score,
                confidence=0.85,
                period_start=datetime.now(UTC),
                period_end=datetime.now(UTC),
            )
        )

        # Execution efficiency
        exec_time = self._extract_agent_execution_time(agent_name, execution_data)
        metrics.append(
            AgentPerformanceMetric(
                agent_name=agent_name,
                metric_type=MetricType.EXECUTION_TIME,
                value=exec_time,
                confidence=1.0,
                period_start=datetime.now(UTC),
                period_end=datetime.now(UTC),
            )
        )

        # Recovery effectiveness
        recovery = self._extract_agent_recovery_effectiveness(
            agent_name, execution_data
        )
        metrics.append(
            AgentPerformanceMetric(
                agent_name=agent_name,
                metric_type=MetricType.RECOVERY_EFFECTIVENESS,
                value=recovery,
                confidence=0.7,
                period_start=datetime.now(UTC),
                period_end=datetime.now(UTC),
            )
        )

        return metrics

    async def generate_analytics(
        self,
        workflow_id: str,
        execution_data: Dict[str, Any],
    ) -> ExecutionAnalytics:
        """Generate comprehensive execution analytics.

        Args:
            workflow_id: ID of workflow
            execution_data: Execution details

        Returns:
            ExecutionAnalytics
        """
        self.logger.info(f"Generating analytics for: {workflow_id}")

        analytics = ExecutionAnalytics(
            workflow_id=workflow_id,
            total_execution_time_seconds=execution_data.get("total_time", 0),
            planning_time_seconds=execution_data.get("planning_time", 0),
            execution_time_seconds=execution_data.get("execution_time", 0),
            verification_time_seconds=execution_data.get("verification_time", 0),
            deployment_time_seconds=execution_data.get("deployment_time", 0),
            total_retries=execution_data.get("total_retries", 0),
            total_failures=execution_data.get("total_failures", 0),
            recovery_attempts=execution_data.get("recovery_attempts", 0),
            successful_recoveries=execution_data.get("successful_recoveries", 0),
            human_interventions=execution_data.get("human_interventions", 0),
            automated_decisions=execution_data.get("automated_decisions", 0),
            decision_quality_average=execution_data.get("decision_quality", 75),
            resource_efficiency_score=execution_data.get("resource_efficiency", 80),
        )

        return analytics

    # ===== Extraction Methods =====

    def _extract_planning_quality(self, execution_data: Dict[str, Any]) -> float:
        """Extract planning quality score."""
        return execution_data.get("planning_quality_score", 75.0)

    def _extract_code_quality(self, execution_data: Dict[str, Any]) -> float:
        """Extract code quality score."""
        return execution_data.get("code_quality_score", 80.0)

    def _extract_verification_score(self, execution_data: Dict[str, Any]) -> float:
        """Extract verification score."""
        return execution_data.get("verification_score", 85.0)

    def _extract_deployment_success(self, execution_data: Dict[str, Any]) -> float:
        """Extract deployment success rate."""
        return execution_data.get("deployment_success", 1.0)

    def _extract_recovery_effectiveness(
        self,
        execution_data: Dict[str, Any],
    ) -> float:
        """Extract recovery effectiveness."""
        total = execution_data.get("recovery_attempts", 0)
        if total == 0:
            return 1.0  # No recovery needed = perfect

        successful = execution_data.get("successful_recoveries", 0)
        return successful / total if total > 0 else 0.0

    def _extract_execution_time(self, execution_data: Dict[str, Any]) -> float:
        """Extract total execution time in seconds."""
        return execution_data.get("total_time", 0.0)

    def _extract_retry_count(self, execution_data: Dict[str, Any]) -> int:
        """Extract number of retries."""
        return execution_data.get("total_retries", 0)

    def _extract_test_coverage(self, execution_data: Dict[str, Any]) -> float:
        """Extract test coverage percentage."""
        return execution_data.get("test_coverage", 80.0)

    def _extract_resource_usage(self, execution_data: Dict[str, Any]) -> float:
        """Extract resource usage percentage."""
        return execution_data.get("resource_usage", 50.0)

    def _determine_success(self, execution_data: Dict[str, Any]) -> bool:
        """Determine if workflow succeeded."""
        return execution_data.get("is_successful", False)

    def _extract_agent_planning_quality(
        self,
        agent_name: str,
        execution_data: Dict[str, Any],
    ) -> float:
        """Extract planning quality for specific agent."""
        agents = execution_data.get("agents", {})
        agent_data = agents.get(agent_name, {})
        return agent_data.get("planning_quality", 75.0)

    def _extract_agent_code_quality(
        self,
        agent_name: str,
        execution_data: Dict[str, Any],
    ) -> float:
        """Extract code quality for specific agent."""
        agents = execution_data.get("agents", {})
        agent_data = agents.get(agent_name, {})
        return agent_data.get("code_quality", 80.0)

    def _extract_agent_execution_time(
        self,
        agent_name: str,
        execution_data: Dict[str, Any],
    ) -> float:
        """Extract execution time for specific agent."""
        agents = execution_data.get("agents", {})
        agent_data = agents.get(agent_name, {})
        return agent_data.get("execution_time", 0.0)

    def _extract_agent_recovery_effectiveness(
        self,
        agent_name: str,
        execution_data: Dict[str, Any],
    ) -> float:
        """Extract recovery effectiveness for specific agent."""
        agents = execution_data.get("agents", {})
        agent_data = agents.get(agent_name, {})

        total = agent_data.get("recovery_attempts", 0)
        if total == 0:
            return 1.0

        successful = agent_data.get("successful_recoveries", 0)
        return successful / total if total > 0 else 0.0
