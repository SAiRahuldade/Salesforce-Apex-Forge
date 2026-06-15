"""TaskAgent adapters wrapping specialist agents for the workflow engine."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from salesforce_ai_engineer.agent.models import (
    ExecutionPlan,
    ExecutionTask,
    RecoveryAction,
    RecoveryDecision,
    TaskResult,
)
from salesforce_ai_engineer.deployment.agent import DeploymentAgent
from salesforce_ai_engineer.deployment.models import (
    ConnectionType,
    DeploymentConnection,
    DeploymentEnvironment,
    DeploymentRequest,
    DeploymentStrategy,
)
from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus
from salesforce_ai_engineer.recovery.agent import RecoveryAgent as FullRecoveryAgent
from salesforce_ai_engineer.recovery.models import (
    FailureCategory,
    FailureReport,
    FailureSeverity,
)
from salesforce_ai_engineer.agent.artifact_paths import (
    ensure_meta_files,
    iter_artifact_files,
    resolve_salesforce_path,
)

logger = logging.getLogger(__name__)


async def write_artifacts_to_force_app(
    tool_executor: ToolExecutor | None,
    artifacts: dict[str, Any],
    *,
    workflow_id: str,
    task_id: str,
) -> list[str]:
    """Persist generated artifacts under force-app using the filesystem tool."""

    if tool_executor is None or not artifacts:
        return []

    written: list[str] = []
    for filename, content in ensure_meta_files(iter_artifact_files(artifacts)):
        relative_path = resolve_salesforce_path(filename)
        response = await tool_executor.execute(
            ToolRequest(
                tool_name="filesystem",
                workflow_id=workflow_id,
                task_id=task_id,
                input={
                    "operation": "write_text",
                    "path": relative_path,
                    "content": content,
                },
            )
        )
        if response.status == ToolStatus.SUCCESS and response.output:
            written.append(response.output.get("path", relative_path))
    return written


class LLMEngineerTaskAdapter:
    """Wraps the LLM-based SalesforceEngineerAgent from agent.engineer."""

    def __init__(
        self,
        agent: Any,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self.agent = agent
        self.tool_executor = tool_executor

    async def execute(self, task: ExecutionTask) -> TaskResult:
        workflow_id = _workflow_id(task)
        try:
            task_result = await self.agent.execute(task)
            if not task_result.success:
                return TaskResult(
                    task_id=task.id,
                    success=False,
                    error=task_result.error or "Salesforce engineer task failed",
                    output=task_result.output,
                )

            artifacts = task_result.output.get("artifacts", {}) if task_result.output else {}
            written_paths = await write_artifacts_to_force_app(
                self.tool_executor,
                artifacts,
                workflow_id=workflow_id,
                task_id=task.id,
            )
            output = {**(task_result.output or {}), "written_paths": written_paths}
            return TaskResult(task_id=task.id, success=True, output=output)
        except Exception as exc:
            logger.exception("LLM engineer adapter failed for task %s", task.id)
            return TaskResult(task_id=task.id, success=False, error=str(exc))


class LLMVerifierTaskAdapter:
    """Wraps the LLM-based VerifierAgent from agent.verifier."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def execute(self, task: ExecutionTask) -> TaskResult:
        try:
            return await self.agent.execute(task)
        except Exception as exc:
            logger.exception("LLM verifier adapter failed for task %s", task.id)
            return TaskResult(task_id=task.id, success=False, error=str(exc))


def _workflow_id(task: ExecutionTask) -> str:
    return str(task.input.get("workflow_id") or task.metadata.get("workflow_id") or "unknown")


def _plan_for_task(task: ExecutionTask) -> ExecutionPlan:
    task_copy = task.model_copy(deep=True)
    task_copy.dependencies = []
    return ExecutionPlan(
        objective=task.description or task.title,
        tasks=[task_copy],
        metadata=dict(task.metadata),
    )


class SalesforceEngineerTaskAdapter:
    """Wraps SalesforceEngineerAgent for single-task workflow execution."""

    def __init__(
        self,
        agent: Any,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self.agent = agent
        self.tool_executor = tool_executor

    async def execute(self, task: ExecutionTask) -> TaskResult:
        workflow_id = _workflow_id(task)
        artifacts = task.input.get("artifacts", {})
        if not isinstance(artifacts, dict):
            artifacts = {}

        try:
            # Unified method call: execute instead of _execute_task
            task_result = await self.agent.execute(
                task=task,
            )
            if not task_result.success:
                return TaskResult(
                    task_id=task.id,
                    success=False,
                    error=task_result.error or "Salesforce engineer task failed",
                    output=task_result.output,
                )

            written_paths = await self._write_artifacts(task, task_result.output.get("artifacts", {}), workflow_id)
            output = {**task_result.output, "written_paths": written_paths}
            return TaskResult(task_id=task.id, success=True, output=output)
        except Exception as exc:
            logger.exception("Salesforce engineer adapter failed for task %s", task.id)
            return TaskResult(task_id=task.id, success=False, error=str(exc))

    async def _write_artifacts(
        self,
        task: ExecutionTask,
        artifacts: dict[str, Any],
        workflow_id: str,
    ) -> list[str]:
        return await write_artifacts_to_force_app(
            self.tool_executor,
            artifacts,
            workflow_id=workflow_id,
            task_id=task.id,
        )


class VerifierTaskAdapter:
    """Wraps VerifierAgent for single-task workflow execution."""

    def __init__(self, agent: VerifierAgent) -> None:
        self.agent = agent

    async def execute(self, task: ExecutionTask) -> TaskResult:
        workflow_id = _workflow_id(task)
        artifacts = task.input.get("artifacts", {})
        if not isinstance(artifacts, dict):
            artifacts = {}

        try:
            report = await self.agent.verify_plan(
                plan=_plan_for_task(task),
                artifacts=artifacts,
                workflow_id=workflow_id,
            )
            return TaskResult(
                task_id=task.id,
                success=report.approved_for_deployment,
                output={
                    "approved_for_deployment": report.approved_for_deployment,
                    "quality_score": report.quality_score.overall_score,
                    "total_issues": report.total_issues,
                    "report_id": report.id,
                },
                error=None if report.approved_for_deployment else report.rejection_reason,
            )
        except Exception as exc:
            logger.exception("Verifier adapter failed for task %s", task.id)
            return TaskResult(task_id=task.id, success=False, error=str(exc))


class DeploymentTaskAdapter:
    """Wraps DeploymentAgent for single-task workflow execution."""

    def __init__(
        self,
        agent: DeploymentAgent,
        default_connection: DeploymentConnection | None = None,
    ) -> None:
        self.agent = agent
        self.default_connection = default_connection

    async def execute(self, task: ExecutionTask) -> TaskResult:
        workflow_id = _workflow_id(task)
        connection = self._connection_from_task(task)
        artifacts = task.input.get("artifacts", {})
        if not isinstance(artifacts, dict):
            artifacts = {}

        strategy_name = str(task.input.get("strategy", "full_deploy")).lower()
        strategy = DeploymentStrategy.FULL_DEPLOY
        if strategy_name in {"validate_only", "validate"}:
            strategy = DeploymentStrategy.VALIDATE_ONLY
        elif strategy_name == "quick_deploy":
            strategy = DeploymentStrategy.QUICK_DEPLOY

        environment_name = str(task.input.get("environment", "sandbox")).lower()
        try:
            environment = DeploymentEnvironment(environment_name)
        except ValueError:
            environment = DeploymentEnvironment.SANDBOX

        request = DeploymentRequest(
            workflow_id=workflow_id,
            connection=connection,
            environment=environment,
            strategy=strategy,
            artifacts=artifacts or {"placeholder": task.description},
            test_level=str(task.input.get("test_level", "RunLocalTests")),
            rollback_on_error=bool(task.input.get("rollback_on_error", True)),
        )

        try:
            report = await self.agent.deploy(request)
            return TaskResult(
                task_id=task.id,
                success=report.is_success,
                output={
                    "deployment_id": report.deployment_id,
                    "status": report.status.value,
                    "components_deployed": len(report.components),
                },
                error=report.failure_reason if not report.is_success else None,
            )
        except Exception as exc:
            logger.exception("Deployment adapter failed for task %s", task.id)
            return TaskResult(task_id=task.id, success=False, error=str(exc))

    def _connection_from_task(self, task: ExecutionTask) -> DeploymentConnection:
        if self.default_connection is not None:
            base = self.default_connection.model_copy(deep=True)
        else:
            base = DeploymentConnection(
                connection_type=ConnectionType.SFDX,
                org_id=task.input.get("org_id", "local-org"),
                org_name=task.input.get("org_name", "local"),
                environment=DeploymentEnvironment.SANDBOX,
                instance_url=task.input.get("instance_url", "https://login.salesforce.com"),
                is_production=bool(task.input.get("is_production", False)),
            )

        if task.input.get("org_id"):
            base.org_id = str(task.input["org_id"])
        if task.input.get("org_name") or task.input.get("org_alias"):
            base.org_name = str(task.input.get("org_name") or task.input.get("org_alias"))
        if task.input.get("instance_url"):
            base.instance_url = str(task.input["instance_url"])
        if "is_production" in task.input:
            base.is_production = bool(task.input["is_production"])

        connection_type = task.input.get("connection_type")
        if connection_type:
            try:
                base.connection_type = ConnectionType(str(connection_type).lower())
            except ValueError:
                pass
        return base


class WorkflowRecoveryAdapter:
    """Adapts the full RecoveryAgent to the workflow RecoveryAgent protocol."""

    def __init__(self, recovery_agent: FullRecoveryAgent) -> None:
        self.recovery_agent = recovery_agent

    async def recover(self, task: ExecutionTask, error: Exception | str) -> RecoveryDecision:
        failure_report = FailureReport(
            id=str(uuid4()),
            workflow_id=_workflow_id(task),
            source_agent=task.agent,
            category=FailureCategory.RUNTIME,
            severity=FailureSeverity.MEDIUM,
            title=f"Task {task.id} failed",
            description=task.description,
            error_message=str(error),
            context={"task_input": task.input, "attempts": task.attempts},
            affected_artifact=task.id,
            affected_task_id=task.id,
            original_attempt_count=task.attempts,
        )

        try:
            result = await self.recovery_agent.handle_failure(
                failure_report,
                retry_count=max(0, task.attempts - 1),
            )
        except Exception as exc:
            return RecoveryDecision(
                action=RecoveryAction.ESCALATE,
                reason=f"Recovery agent failed: {exc}",
            )

        if result.is_recovered or result.final_status.value in {"succeeded", "partially_succeeded"}:
            return RecoveryDecision(
                action=RecoveryAction.RETRY,
                reason=result.solution_applied or "Recovery succeeded",
                updated_input={
                    **task.input,
                    "previous_error": str(error),
                    "recovery_attempt": task.attempts,
                },
            )

        return RecoveryDecision(
            action=RecoveryAction.ESCALATE,
            reason=result.escalation_details or result.root_cause or str(error),
        )
