"""Recovery strategies for different failure types."""

import logging
from typing import Any
import asyncio

from salesforce_ai_engineer.recovery.models import (
    FailureReport,
    RecoveryPlan,
    RecoveryAction,
    RecoveryStrategy,
    FailureCategory,
)

logger = logging.getLogger(__name__)


class RecoveryStrategyBase:
    """Base class for recovery strategies."""

    async def build_plan(
        self,
        failure_report: FailureReport,
        root_cause: str,
        confidence: float,
    ) -> RecoveryPlan:
        """Build a recovery plan for the failure.

        Args:
            failure_report: The failure report
            root_cause: Analyzed root cause
            confidence: Confidence in the analysis

        Returns:
            RecoveryPlan
        """
        raise NotImplementedError

    async def validate_plan(self, plan: RecoveryPlan) -> bool:
        """Validate that plan is executable."""
        return len(plan.actions) > 0 and plan.confidence >= 0.5


class RetryStrategy(RecoveryStrategyBase):
    """Retry strategy with exponential backoff."""

    async def build_plan(
        self,
        failure_report: FailureReport,
        root_cause: str,
        confidence: float,
    ) -> RecoveryPlan:
        """Build a retry plan."""
        plan = RecoveryPlan(
            failure_id=failure_report.id,
            failure_category=failure_report.category,
            root_cause_analysis=f"Transient failure detected. {root_cause}",
            confidence=confidence,
            strategy=RecoveryStrategy.RETRY,
            estimated_duration_seconds=60.0,
        )

        # Add retry actions with exponential backoff
        for attempt in range(1, 4):
            wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s
            plan.actions.append(
                RecoveryAction(
                    step_number=attempt,
                    description=f"Retry attempt {attempt} (after {wait_time}s wait)",
                    action_type="wait_and_retry",
                    parameters={
                        "wait_seconds": wait_time,
                        "retry_target": failure_report.affected_task_id,
                    },
                    timeout_seconds=300,
                    max_retries=1,
                    backoff_multiplier=2.0,
                )
            )

        return plan


class RegenerateStrategy(RecoveryStrategyBase):
    """Regenerate failed artifact."""

    async def build_plan(
        self,
        failure_report: FailureReport,
        root_cause: str,
        confidence: float,
    ) -> RecoveryPlan:
        """Build a regeneration plan."""
        plan = RecoveryPlan(
            failure_id=failure_report.id,
            failure_category=failure_report.category,
            root_cause_analysis=f"Code generation error. {root_cause}",
            confidence=confidence,
            strategy=RecoveryStrategy.REGENERATE,
            estimated_duration_seconds=120.0,
        )

        plan.actions.append(
            RecoveryAction(
                step_number=1,
                description="Invoke Salesforce Engineer to regenerate artifact",
                action_type="invoke_engineer",
                parameters={
                    "artifact_id": failure_report.affected_artifact,
                    "task_id": failure_report.affected_task_id,
                    "include_context": True,
                },
                timeout_seconds=300,
                max_retries=2,
            )
        )

        plan.actions.append(
            RecoveryAction(
                step_number=2,
                description="Invoke Verifier to validate regenerated artifact",
                action_type="invoke_verifier",
                parameters={
                    "artifact_id": failure_report.affected_artifact,
                },
                timeout_seconds=120,
                max_retries=1,
            )
        )

        return plan


class RollbackStrategy(RecoveryStrategyBase):
    """Rollback to previous state."""

    async def build_plan(
        self,
        failure_report: FailureReport,
        root_cause: str,
        confidence: float,
    ) -> RecoveryPlan:
        """Build a rollback plan."""
        plan = RecoveryPlan(
            failure_id=failure_report.id,
            failure_category=failure_report.category,
            root_cause_analysis=f"Deployment/state error. {root_cause}",
            confidence=confidence,
            strategy=RecoveryStrategy.ROLLBACK,
            estimated_duration_seconds=300.0,
        )

        plan.actions.append(
            RecoveryAction(
                step_number=1,
                description="Save current state checkpoint",
                action_type="checkpoint_state",
                parameters={
                    "checkpoint_name": f"rollback-{failure_report.id}",
                    "include_artifacts": True,
                },
                timeout_seconds=60,
                max_retries=1,
            )
        )

        plan.actions.append(
            RecoveryAction(
                step_number=2,
                description="Restore previous version of artifacts",
                action_type="restore_previous",
                parameters={
                    "artifact_id": failure_report.affected_artifact,
                    "steps_back": 1,
                },
                timeout_seconds=120,
                max_retries=1,
            )
        )

        plan.actions.append(
            RecoveryAction(
                step_number=3,
                description="Verify restored state",
                action_type="invoke_verifier",
                parameters={
                    "artifact_id": failure_report.affected_artifact,
                    "validation_level": "complete",
                },
                timeout_seconds=120,
                max_retries=1,
            )
        )

        return plan


class FallbackStrategy(RecoveryStrategyBase):
    """Use fallback/alternative approach."""

    async def build_plan(
        self,
        failure_report: FailureReport,
        root_cause: str,
        confidence: float,
    ) -> RecoveryPlan:
        """Build a fallback plan."""
        plan = RecoveryPlan(
            failure_id=failure_report.id,
            failure_category=failure_report.category,
            root_cause_analysis=f"Primary approach failed. {root_cause}",
            confidence=confidence,
            strategy=RecoveryStrategy.FALLBACK,
            estimated_duration_seconds=180.0,
        )

        plan.actions.append(
            RecoveryAction(
                step_number=1,
                description="Attempt using alternative generation parameters",
                action_type="invoke_engineer_with_parameters",
                parameters={
                    "artifact_id": failure_report.affected_artifact,
                    "use_template": True,
                    "alternative_parameters": {
                        "strict_mode": False,
                        "allow_warnings": True,
                    },
                },
                timeout_seconds=300,
                max_retries=2,
            )
        )

        plan.actions.append(
            RecoveryAction(
                step_number=2,
                description="Invoke Verifier with relaxed constraints",
                action_type="invoke_verifier_relaxed",
                parameters={
                    "artifact_id": failure_report.affected_artifact,
                    "allow_warnings": True,
                    "minimum_quality_score": 65,
                },
                timeout_seconds=120,
                max_retries=1,
            )
        )

        return plan


class ReconfigureStrategy(RecoveryStrategyBase):
    """Adjust configuration and retry."""

    async def build_plan(
        self,
        failure_report: FailureReport,
        root_cause: str,
        confidence: float,
    ) -> RecoveryPlan:
        """Build a reconfiguration plan."""
        plan = RecoveryPlan(
            failure_id=failure_report.id,
            failure_category=failure_report.category,
            root_cause_analysis=f"Configuration issue. {root_cause}",
            confidence=confidence,
            strategy=RecoveryStrategy.RECONFIGURE,
            estimated_duration_seconds=120.0,
        )

        plan.actions.append(
            RecoveryAction(
                step_number=1,
                description="Update configuration based on failure context",
                action_type="update_config",
                parameters={
                    "config_key": "batch_size" if failure_report.category == FailureCategory.GOVERNOR_LIMIT else "recovery_mode",
                    "config_value": "200" if failure_report.category == FailureCategory.GOVERNOR_LIMIT else "enabled",
                    "affected_component": failure_report.source_agent,
                    "reason": root_cause
                },
                timeout_seconds=30,
                max_retries=1,
            )
        )

        plan.actions.append(
            RecoveryAction(
                step_number=2,
                description="Retry failed operation with new configuration",
                action_type="retry_with_config",
                parameters={
                    "task_id": failure_report.affected_task_id,
                    "use_updated_config": True,
                },
                timeout_seconds=300,
                max_retries=2,
            )
        )

        return plan


class SkipStrategy(RecoveryStrategyBase):
    """Skip failed artifact and continue."""

    async def build_plan(
        self,
        failure_report: FailureReport,
        root_cause: str,
        confidence: float,
    ) -> RecoveryPlan:
        """Build a skip plan."""
        plan = RecoveryPlan(
            failure_id=failure_report.id,
            failure_category=failure_report.category,
            root_cause_analysis=f"Non-critical failure. {root_cause}",
            confidence=confidence,
            strategy=RecoveryStrategy.SKIP,
            estimated_duration_seconds=10.0,
        )

        plan.actions.append(
            RecoveryAction(
                step_number=1,
                description="Mark artifact as optional and continue",
                action_type="skip_artifact",
                parameters={
                    "artifact_id": failure_report.affected_artifact,
                    "reason": "Non-critical, skipping to maintain workflow progress",
                    "continue_workflow": True,
                },
                timeout_seconds=10,
                max_retries=0,
            )
        )

        return plan


class EscalateStrategy(RecoveryStrategyBase):
    """Escalate to human operator."""

    async def build_plan(
        self,
        failure_report: FailureReport,
        root_cause: str,
        confidence: float,
    ) -> RecoveryPlan:
        """Build an escalation plan."""
        plan = RecoveryPlan(
            failure_id=failure_report.id,
            failure_category=failure_report.category,
            root_cause_analysis=f"Unrecoverable failure. {root_cause}",
            confidence=confidence,
            strategy=RecoveryStrategy.ESCALATE,
            estimated_duration_seconds=0.0,
        )

        plan.actions.append(
            RecoveryAction(
                step_number=1,
                description="Escalate failure to human operator",
                action_type="escalate_to_human",
                parameters={
                    "failure_id": failure_report.id,
                    "severity": failure_report.severity.value,
                    "context": failure_report.context,
                },
                timeout_seconds=0,
                max_retries=0,
            )
        )

        return plan


class StrategyFactory:
    """Factory for creating recovery strategies."""

    # Map categories to preferred strategies
    STRATEGY_MAP = {
        FailureCategory.CODE_GENERATION: RegenerateStrategy,
        FailureCategory.METADATA: RegenerateStrategy,
        FailureCategory.DEPLOYMENT: RollbackStrategy,
        FailureCategory.AUTHENTICATION: EscalateStrategy,
        FailureCategory.NETWORKING: RetryStrategy,
        FailureCategory.DEPENDENCY: FallbackStrategy,
        FailureCategory.VALIDATION: RegenerateStrategy,
        FailureCategory.GOVERNOR_LIMIT: FallbackStrategy,
        FailureCategory.SECURITY: EscalateStrategy,
        FailureCategory.RUNTIME: RetryStrategy,
        FailureCategory.FILESYSTEM: ReconfigureStrategy,
        FailureCategory.CONFIGURATION: ReconfigureStrategy,
        FailureCategory.SYSTEM: RetryStrategy,
    }

    @staticmethod
    def get_strategy(
        failure_category: FailureCategory,
        preferred_strategy: RecoveryStrategy | None = None,
    ) -> RecoveryStrategyBase:
        """Get recovery strategy for a failure category.

        Args:
            failure_category: Category of failure
            preferred_strategy: Optional preferred strategy override

        Returns:
            RecoveryStrategyBase instance
        """
        if preferred_strategy == RecoveryStrategy.RETRY:
            return RetryStrategy()
        elif preferred_strategy == RecoveryStrategy.REGENERATE:
            return RegenerateStrategy()
        elif preferred_strategy == RecoveryStrategy.ROLLBACK:
            return RollbackStrategy()
        elif preferred_strategy == RecoveryStrategy.FALLBACK:
            return FallbackStrategy()
        elif preferred_strategy == RecoveryStrategy.RECONFIGURE:
            return ReconfigureStrategy()
        elif preferred_strategy == RecoveryStrategy.SKIP:
            return SkipStrategy()
        elif preferred_strategy == RecoveryStrategy.ESCALATE:
            return EscalateStrategy()

        # Use default for category
        strategy_class = StrategyFactory.STRATEGY_MAP.get(
            failure_category, RetryStrategy
        )
        return strategy_class()

    @staticmethod
    def register_strategy(
        failure_category: FailureCategory,
        strategy_class: type,
    ):
        """Register a custom recovery strategy for a failure category.

        Args:
            failure_category: Failure category
            strategy_class: Strategy class to register
        """
        StrategyFactory.STRATEGY_MAP[failure_category] = strategy_class
