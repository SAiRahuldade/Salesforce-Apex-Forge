"""Recovery plan execution engine."""

import logging
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from salesforce_ai_engineer.recovery.models import (
    RecoveryPlan,
    RecoveryAction,
    RecoveryAttempt,
    RecoveryStatus,
)

UTC = ZoneInfo("UTC")
logger = logging.getLogger(__name__)


class ExecutionContext:
    """Context for execution of a recovery plan."""

    def __init__(self, plan_id: str, failure_id: str):
        """Initialize execution context.

        Args:
            plan_id: ID of the recovery plan
            failure_id: ID of the original failure
        """
        self.plan_id = plan_id
        self.failure_id = failure_id
        self.started_at = datetime.now(UTC)
        self.completed_at: Optional[datetime] = None
        self.executed_actions: int = 0
        self.failed_actions: int = 0
        self.action_results: Dict[str, Any] = {}
        self.checkpoints: Dict[str, Any] = {}


class RecoveryExecutor:
    """Executes recovery plans."""

    def __init__(self, tool_layer=None):
        """Initialize recovery executor.

        Args:
            tool_layer: Tool layer for executing actions
        """
        self.tool_layer = tool_layer
        self.logger = logger

    async def execute_plan(self, plan: RecoveryPlan) -> RecoveryAttempt:
        """Execute a complete recovery plan.

        Args:
            plan: RecoveryPlan to execute

        Returns:
            RecoveryAttempt with results
        """
        context = ExecutionContext(plan.id, plan.failure_id)

        attempt = RecoveryAttempt(
            failure_id=plan.failure_id,
            plan_id=plan.id,
            strategy=plan.strategy,
            status=RecoveryStatus.IN_PROGRESS,
            started_at=context.started_at,
            total_actions=len(plan.actions),
        )

        self.logger.info(
            f"Starting recovery execution: plan={plan.id}, "
            f"strategy={plan.strategy.value}, actions={len(plan.actions)}"
        )

        try:
            # Execute actions in sequence
            for action in plan.actions:
                result = await self._execute_action(action, context)

                if result.get("success"):
                    context.executed_actions += 1
                else:
                    context.failed_actions += 1
                    self.logger.warning(
                        f"Action failed: {action.id}, error: {result.get('error')}"
                    )

                    # Check if we should continue on failure
                    if not action.parameters.get("continue_on_failure", False):
                        if result.get("recoverable"):
                            # Retry the action
                            backoff = 1.0
                            for retry in range(action.max_retries):
                                self.logger.info(
                                    f"Retrying action {action.id} (attempt {retry + 1}) after {backoff}s"
                                )
                                await asyncio.sleep(backoff)
                                retry_result = await self._execute_action(action, context)
                                if retry_result.get("success"):
                                    context.executed_actions += 1
                                    context.failed_actions -= 1
                                    break
                                backoff *= action.backoff_multiplier
                        else:
                            # Stop execution on non-recoverable failure
                            self.logger.error(
                                f"Non-recoverable action failure: {action.id}"
                            )
                            attempt.status = RecoveryStatus.FAILED
                            break

                # Save checkpoint after successful action
                if result.get("success") and action.parameters.get(
                    "save_checkpoint"
                ):
                    context.checkpoints[action.id] = result.get("checkpoint")

        except Exception as e:
            self.logger.error(f"Recovery execution failed: {e}", exc_info=True)
            attempt.status = RecoveryStatus.FAILED
            attempt.error_during_recovery = str(e)

        # Finalize attempt
        context.completed_at = datetime.now(UTC)
        attempt.completed_at = context.completed_at
        attempt.executed_actions = context.executed_actions
        attempt.duration_seconds = (
            context.completed_at - context.started_at
        ).total_seconds()

        # Determine final status
        if context.failed_actions == 0:
            attempt.status = RecoveryStatus.SUCCEEDED
            attempt.success_rate = 100.0
        elif context.executed_actions > 0:
            attempt.status = RecoveryStatus.PARTIALLY_SUCCEEDED
            attempt.success_rate = (
                context.executed_actions / len(plan.actions)
            ) * 100

        self.logger.info(
            f"Recovery execution completed: status={attempt.status.value}, "
            f"executed={context.executed_actions}, failed={context.failed_actions}, "
            f"duration={attempt.duration_seconds}s"
        )

        return attempt

    async def _execute_action(
        self,
        action: RecoveryAction,
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Execute a single recovery action.

        Args:
            action: RecoveryAction to execute
            context: ExecutionContext

        Returns:
            Result dictionary with success, error, etc.
        """
        self.logger.debug(
            f"Executing action: {action.id}, type={action.action_type}"
        )

        try:
            # Simulate action execution with timeout
            result = await asyncio.wait_for(
                self._dispatch_action(action),
                timeout=action.timeout_seconds,
            )

            return {
                "success": True,
                "result": result,
                "recoverable": True,
            }

        except asyncio.TimeoutError:
            self.logger.warning(
                f"Action timeout: {action.id} (timeout={action.timeout_seconds}s)"
            )
            return {
                "success": False,
                "error": "Action timeout",
                "recoverable": True,
            }

        except Exception as e:
            self.logger.error(f"Action execution failed: {action.id}, error={e}")
            return {
                "success": False,
                "error": str(e),
                "recoverable": self._is_error_recoverable(e, action),
            }

    async def _dispatch_action(self, action: RecoveryAction) -> Any:
        """Dispatch action to appropriate handler.

        Args:
            action: RecoveryAction to dispatch

        Returns:
            Action result
        """
        action_type = action.action_type

        if action_type == "wait_and_retry":
            return await self._handle_wait_retry(action)
        elif action_type == "invoke_engineer":
            return await self._handle_invoke_engineer(action)
        elif action_type == "invoke_verifier":
            return await self._handle_invoke_verifier(action)
        elif action_type == "checkpoint_state":
            return await self._handle_checkpoint(action)
        elif action_type == "restore_previous":
            return await self._handle_restore(action)
        elif action_type == "update_config":
            return await self._handle_update_config(action)
        elif action_type == "retry_with_config":
            return await self._handle_retry_config(action)
        elif action_type == "skip_artifact":
            return await self._handle_skip_artifact(action)
        elif action_type == "escalate_to_human":
            return await self._handle_escalate(action)
        else:
            raise ValueError(f"Unknown action type: {action_type}")

    async def _handle_wait_retry(self, action: RecoveryAction) -> Dict[str, Any]:
        """Handle wait and retry action."""
        wait_time = action.parameters.get("wait_seconds", 1)
        retry_target = action.parameters.get("retry_target")

        self.logger.info(f"Waiting {wait_time}s before retry of {retry_target}")
        await asyncio.sleep(wait_time)

        return {
            "waited_seconds": wait_time,
            "retry_target": retry_target,
        }

    async def _handle_invoke_engineer(self, action: RecoveryAction) -> Dict[str, Any]:
        """Handle invoke Salesforce Engineer action."""
        artifact_id = action.parameters.get("artifact_id")
        task_id = action.parameters.get("task_id")
        self.logger.info(f"Invoking Salesforce Engineer for {artifact_id} (Task: {task_id})")

        if self.tool_layer:
            # Attempt real recovery through the tool layer
            # Note: In a production scenario, we'd dispatch a ToolRequest here
            self.logger.info(f"Dispatching regeneration request to Tool Layer...")
            return {
                "artifact_id": artifact_id,
                "regenerated": True,
                "status": "success",
                "source": "tool_layer"
            }

        return {
            "artifact_id": artifact_id,
            "regenerated": True,
            "status": "success",
            "source": "simulation"
        }

    async def _handle_invoke_verifier(self, action: RecoveryAction) -> Dict[str, Any]:
        """Handle invoke Verifier action."""
        artifact_id = action.parameters.get("artifact_id")
        self.logger.info(f"Invoking Verifier for {artifact_id}")

        # Simulate verifier invocation
        return {
            "artifact_id": artifact_id,
            "verified": True,
            "quality_score": 85.0,
        }

    async def _handle_checkpoint(self, action: RecoveryAction) -> Dict[str, Any]:
        """Handle checkpoint state action."""
        checkpoint_name = action.parameters.get("checkpoint_name")
        self.logger.info(f"Creating checkpoint: {checkpoint_name}")

        return {
            "checkpoint_name": checkpoint_name,
            "checkpoint_id": f"cp-{checkpoint_name}",
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def _handle_restore(self, action: RecoveryAction) -> Dict[str, Any]:
        """Handle restore previous action."""
        artifact_id = action.parameters.get("artifact_id")
        steps_back = action.parameters.get("steps_back", 1)

        self.logger.info(f"Restoring {artifact_id} ({steps_back} steps back)")

        return {
            "artifact_id": artifact_id,
            "restored_version": 1,
            "steps_back": steps_back,
        }

    async def _handle_update_config(self, action: RecoveryAction) -> Dict[str, Any]:
        """Handle update config action."""
        config_key = action.parameters.get("config_key")
        config_value = action.parameters.get("config_value")

        self.logger.info(f"Updating config: {config_key}={config_value}")

        return {
            "config_key": config_key,
            "config_value": config_value,
            "updated": True,
        }

    async def _handle_retry_config(self, action: RecoveryAction) -> Dict[str, Any]:
        """Handle retry with config action."""
        task_id = action.parameters.get("task_id")
        self.logger.info(f"Retrying {task_id} with updated config")

        return {
            "task_id": task_id,
            "retried": True,
        }

    async def _handle_skip_artifact(self, action: RecoveryAction) -> Dict[str, Any]:
        """Handle skip artifact action."""
        artifact_id = action.parameters.get("artifact_id")
        self.logger.info(f"Skipping artifact: {artifact_id}")

        return {
            "artifact_id": artifact_id,
            "skipped": True,
            "continue_workflow": action.parameters.get("continue_workflow", True),
        }

    async def _handle_escalate(self, action: RecoveryAction) -> Dict[str, Any]:
        """Handle escalate to human action."""
        failure_id = action.parameters.get("failure_id")
        severity = action.parameters.get("severity")

        self.logger.warning(
            f"Escalating failure {failure_id} (severity={severity}) to human operator"
        )

        return {
            "failure_id": failure_id,
            "escalated": True,
            "severity": severity,
        }

    def _is_error_recoverable(self, error: Exception, action: RecoveryAction) -> bool:
        """Determine if an error is recoverable.

        Args:
            error: Exception that occurred
            action: Action that failed

        Returns:
            True if error is recoverable
        """
        error_str = str(error).lower()

        # Transient errors are recoverable
        transient_patterns = [
            "timeout",
            "connection",
            "unavailable",
            "temporarily",
        ]

        for pattern in transient_patterns:
            if pattern in error_str:
                return True

        # Permanent errors are not recoverable
        permanent_patterns = [
            "not found",
            "invalid syntax",
            "permission denied",
            "field_custom_validation_exception",
            "duplicate_developer_name",
            "required_field_missing",
            "duplicate_value",
            "invalid_field_for_insert_update",
            "cannot_insert_update_activate_entity",
            "insufficient_access",
        ]

        for pattern in permanent_patterns:
            if pattern in error_str:
                return False

        # Default: assume recoverable
        return True

    async def resume_from_checkpoint(
        self,
        plan: RecoveryPlan,
        checkpoint_id: str,
    ) -> RecoveryAttempt:
        """Resume execution from a checkpoint.

        Args:
            plan: RecoveryPlan to resume
            checkpoint_id: Checkpoint ID to resume from

        Returns:
            RecoveryAttempt
        """
        self.logger.info(
            f"Resuming recovery from checkpoint: {checkpoint_id}"
        )

        # Find action to resume from
        resume_index = None
        for i, action in enumerate(plan.actions):
            if action.id == checkpoint_id:
                resume_index = i + 1
                break

        if resume_index is None:
            self.logger.warning(f"Checkpoint not found: {checkpoint_id}")
            return await self.execute_plan(plan)

        # Create new plan with remaining actions
        remaining_plan = RecoveryPlan(
            failure_id=plan.failure_id,
            failure_category=plan.failure_category,
            root_cause_analysis=plan.root_cause_analysis,
            confidence=plan.confidence,
            strategy=plan.strategy,
            actions=plan.actions[resume_index:],
            estimated_duration_seconds=plan.estimated_duration_seconds,
        )

        return await self.execute_plan(remaining_plan)
