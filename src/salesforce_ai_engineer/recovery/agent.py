"""Recovery Agent - autonomously recovers from failures."""

import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Any

from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.recovery.models import (
    FailureReport,
    RecoveryPlan,
    RecoveryResult,
    RecoveryStatus,
    FailureCategory,
    FailureSeverity
)
from salesforce_ai_engineer.recovery.analyzer import FailureAnalyzer
from salesforce_ai_engineer.recovery.strategies import StrategyFactory
from salesforce_ai_engineer.recovery.executor import RecoveryExecutor

UTC = ZoneInfo("UTC")
logger = logging.getLogger(__name__)


class RecoveryError(Exception):
    """Base exception for Recovery Agent."""
    pass


class RecoveryAgent:
    """Autonomously recovers from failures in the system."""

    # Max recovery attempts before escalation
    MAX_RECOVERY_ATTEMPTS = 3
    # Max failures of same type in session before escalating
    FAILURE_LOOP_THRESHOLD = 5

    class RecoveryDecision:
        """Bridge class to satisfy the WorkflowExecutionEngine interface."""
        def __init__(self, action, reason, updated_input=None):
            self.action = action
            self.reason = reason
            self.updated_input = updated_input

    def __init__(
        self,
        event_bus: EventBus,
        memory_manager: MemoryManager,
        tool_layer=None,
    ):
        """Initialize Recovery Agent.

        Args:
            event_bus: EventBus for publishing events
            memory_manager: MemoryManager for learning and retrieval
            tool_layer: Tool layer for executing actions
        """
        self.event_bus = event_bus
        self.memory_manager = memory_manager
        self.tool_layer = tool_layer
        self.executor = RecoveryExecutor(tool_layer)
        self.logger = logger

        # Track failures in current session
        self.failure_counts = {}

    async def recover(self, task: Any, error: Exception) -> "RecoveryDecision":
        """
        Entry point called by the WorkflowExecutionEngine.
        Maps a Task and Exception into a FailureReport and runs the recovery pipeline.
        """
        category = await FailureAnalyzer.categorize_error(str(error))
        task_id = getattr(task, "id", "unknown")
        
        report = FailureReport(
            workflow_id=getattr(task, "workflow_id", "unknown"),
            source_agent=getattr(task, "agent", "unknown"),
            category=category,
            severity=FailureSeverity.MEDIUM,
            title=f"Failure in {task_id}",
            description=f"Task {task_id} failed with error: {str(error)}",
            error_message=str(error),
            affected_task_id=task_id,
            affected_artifact=getattr(task, "artifact_id", None),
            context={"input": getattr(task, "input", {})}
        )

        result = await self.handle_failure(report)

        if result.is_recovered:
            return self.RecoveryDecision(EngineAction.RETRY, result.solution_applied)
        return self.RecoveryDecision(EngineAction.FAIL, result.escalation_details or "Recovery failed")

    async def handle_failure(
        self,
        failure_report: FailureReport,
        retry_count: int = 0,
    ) -> RecoveryResult:
        """Handle a failure and attempt recovery.

        Args:
            failure_report: Structured failure report
            retry_count: Current retry attempt count

        Returns:
            RecoveryResult with outcome
        """
        try:
            recovery_id = str(uuid.uuid4())

            self.logger.info(
                f"Recovery Agent handling failure: {failure_report.id}, "
                f"category={failure_report.category.value}, "
                f"severity={failure_report.severity.value}"
            )

            # Publish failure detected event
            await self.event_bus.publish(
                "recovery.failure_detected",
                {
                    "failure_id": failure_report.id,
                    "category": failure_report.category.value,
                    "recovery_id": recovery_id,
                },
            )

            # Check for failure loops
            loop_detected, escalation_reason = await self._check_failure_loop(
                failure_report
            )
            if loop_detected:
                self.logger.error(f"Failure loop detected: {escalation_reason}")
                return await self._escalate_failure(
                    failure_report,
                    RecoveryStatus.ESCALATED,
                    escalation_reason,
                    recovery_id,
                )

            # Analyze failure
            root_cause, confidence = await FailureAnalyzer.analyze_failure(
                failure_report
            )

            # Check if recoverable
            is_recoverable, recoverability_reason = await (
                FailureAnalyzer.assess_recoverability(failure_report, retry_count)
            )

            if not is_recoverable:
                self.logger.warning(
                    f"Failure not recoverable: {recoverability_reason}"
                )
                return await self._escalate_failure(
                    failure_report,
                    RecoveryStatus.ESCALATED,
                    recoverability_reason,
                    recovery_id,
                )

            # Determine severity
            severity = await FailureAnalyzer.determine_failure_severity(
                failure_report
            )

            # Build recovery plan
            plan = await self._build_recovery_plan(
                failure_report,
                root_cause,
                confidence,
            )

            self.logger.info(
                f"Recovery plan built: strategy={plan.strategy.value}, "
                f"actions={len(plan.actions)}, confidence={plan.confidence}"
            )

            # Publish plan built event
            await self.event_bus.publish(
                "recovery.plan_built",
                {
                    "failure_id": failure_report.id,
                    "plan_id": plan.id,
                    "strategy": plan.strategy.value,
                    "actions": len(plan.actions),
                },
            )

            # Execute recovery plan
            attempt = await self.executor.execute_plan(plan)

            # Create recovery result
            result = RecoveryResult(
                failure_id=failure_report.id,
                recovery_attempts=[attempt],
                final_status=attempt.status,
                is_recovered=attempt.status == RecoveryStatus.SUCCEEDED,
                recovery_time_seconds=attempt.duration_seconds,
                root_cause=root_cause,
                solution_applied=plan.strategy.value,
                affected_artifact_fixed=(
                    attempt.status == RecoveryStatus.SUCCEEDED
                ),
                retry_count=retry_count,
                was_escalated=False,
            )

            # If partial success, try another strategy
            if (
                attempt.status == RecoveryStatus.PARTIALLY_SUCCEEDED
                and retry_count < self.MAX_RECOVERY_ATTEMPTS
            ):
                self.logger.info(
                    f"Partial recovery success, attempting alternative strategy"
                )
                result = await self.handle_failure(failure_report, retry_count + 1)

            # Learn from recovery
            if result.is_recovered:
                await self._learn_from_success(failure_report, plan, result)
            else:
                await self._learn_from_failure(failure_report, plan, result)

            # Publish completion event
            await self.event_bus.publish(
                "recovery.completed",
                {
                    "failure_id": failure_report.id,
                    "recovery_id": recovery_id,
                    "success": result.is_recovered,
                    "recovery_time": result.recovery_time_seconds,
                },
            )

            self.logger.info(
                f"Recovery completed: success={result.is_recovered}, "
                f"time={result.recovery_time_seconds}s"
            )

            return result

        except Exception as e:
            self.logger.error(f"Recovery handling failed: {e}", exc_info=True)
            await self.event_bus.publish(
                "recovery.failed",
                {
                    "failure_id": failure_report.id,
                    "error": str(e),
                },
            )
            raise RecoveryError(f"Recovery failed: {e}") from e

    async def _build_recovery_plan(
        self,
        failure_report: FailureReport,
        root_cause: str,
        confidence: float,
    ) -> RecoveryPlan:
        """Build a recovery plan for the failure.

        Args:
            failure_report: The failure report
            root_cause: Analyzed root cause
            confidence: Confidence in analysis

        Returns:
            RecoveryPlan
        """
        # Try to find historical match
        known_signatures = await self._get_known_failure_signatures()
        matching_signature = await FailureAnalyzer.match_failure_signatures(
            failure_report, known_signatures
        )

        if matching_signature:
            self.logger.info(
                f"Found matching failure signature: {matching_signature.id}"
            )
            strategy = matching_signature.successful_recovery_strategy
        else:
            strategy = None

        # Get strategy for failure category
        strategy_instance = StrategyFactory.get_strategy(
            failure_report.category, strategy
        )

        # Build plan
        plan = await strategy_instance.build_plan(
            failure_report, root_cause, confidence
        )

        return plan

    async def _check_failure_loop(
        self,
        failure_report: FailureReport,
    ) -> tuple[bool, Optional[str]]:
        """Check if we're in a failure loop.

        Args:
            failure_report: The failure report

        Returns:
            Tuple of (loop_detected, reason)
        """
        failure_key = (
            f"{failure_report.category.value}:{failure_report.affected_artifact}"
        )

        count = self.failure_counts.get(failure_key, 0) + 1
        self.failure_counts[failure_key] = count

        if count > self.FAILURE_LOOP_THRESHOLD:
            return True, (
                f"Too many failures of same type: {count} "
                f"(threshold={self.FAILURE_LOOP_THRESHOLD})"
            )

        return False, None

    async def _escalate_failure(
        self,
        failure_report: FailureReport,
        status: RecoveryStatus,
        reason: str,
        recovery_id: str,
    ) -> RecoveryResult:
        """Escalate failure to human operator.

        Args:
            failure_report: The failure report
            status: Recovery status
            reason: Escalation reason
            recovery_id: Recovery ID

        Returns:
            RecoveryResult
        """
        self.logger.warning(
            f"Escalating failure {failure_report.id}: {reason}"
        )

        result = RecoveryResult(
            failure_id=failure_report.id,
            final_status=status,
            is_recovered=False,
            recovery_time_seconds=0.0,
            root_cause="Unknown - escalated for investigation",
            solution_applied="Manual operator intervention required",
            affected_artifact_fixed=False,
            retry_count=0,
            was_escalated=True,
            escalation_details=reason,
        )

        await self.event_bus.publish(
            "recovery.escalated",
            {
                "failure_id": failure_report.id,
                "recovery_id": recovery_id,
                "reason": reason,
            },
        )

        return result

    async def _learn_from_success(
        self,
        failure_report: FailureReport,
        plan: RecoveryPlan,
        result: RecoveryResult,
    ) -> None:
        """Learn from successful recovery.

        Args:
            failure_report: Original failure report
            plan: Recovery plan that was executed
            result: Recovery result
        """
        self.logger.info(f"Learning from successful recovery")

        # Store recovery knowledge in memory
        try:
            memory_id = await self.memory_manager.store_successful_fix(
                error_type=failure_report.category.value,
                error_description=failure_report.error_message,
                fix_description=plan.strategy.value,
                fix_steps=[a.description for a in plan.actions],
                time_to_resolution=result.recovery_time_seconds,
                created_by="recovery",
            )

            result.learned_knowledge_id = memory_id
        except Exception as e:
            self.logger.error(f"Failed to store recovery knowledge: {e}")

    async def _learn_from_failure(
        self,
        failure_report: FailureReport,
        plan: RecoveryPlan,
        result: RecoveryResult,
    ) -> None:
        """Learn from failed recovery attempt.

        Args:
            failure_report: Original failure report
            plan: Recovery plan that was executed
            result: Recovery result
        """
        self.logger.info(f"Learning from failed recovery attempt")

        # Store failure knowledge for future reference
        try:
            await self.memory_manager.store_known_error(
                error_type=failure_report.category.value,
                error_message=failure_report.error_message,
                severity=failure_report.severity.value,
                context_info=failure_report.context,
                created_by="recovery",
            )
        except Exception as e:
            self.logger.error(f"Failed to store error knowledge: {e}")

    async def _get_known_failure_signatures(self) -> list:
        """Get known failure signatures from memory.

        Returns:
            List of FailureSignature objects
        """
        try:
            # Query memory for known recovery patterns
            signatures = await self.memory_manager.find_past_errors("runtime")
            return signatures or []
        except Exception as e:
            self.logger.warning(f"Failed to retrieve failure signatures: {e}")
            return []

    async def get_recovery_statistics(self) -> dict:
        """Get recovery statistics for the session.

        Returns:
            Dictionary of statistics
        """
        return {
            "failure_counts": self.failure_counts,
            "max_attempts": self.MAX_RECOVERY_ATTEMPTS,
            "loop_threshold": self.FAILURE_LOOP_THRESHOLD,
        }
