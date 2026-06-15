"""Deployment Agent - orchestrates safe deployment of Salesforce projects."""

import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.deployment.cli_helper import SalesforceCliHelper
from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.tools.executor import ToolExecutor
from salesforce_ai_engineer.deployment.models import (
    DeploymentRequest,
    DeploymentReport,
    DeploymentStatus,
    DeploymentConnection,
    DeploymentStrategy,
    DeploymentEnvironment,
)
from salesforce_ai_engineer.deployment.auth import ConnectionManager, SalesforceAuthError
from salesforce_ai_engineer.deployment.executor import (
    DeploymentExecutor,
    DeploymentError,
)
from salesforce_ai_engineer.deployment.rollback import RollbackManager, RollbackError
from salesforce_ai_engineer.deployment.monitor import DeploymentMonitor

UTC = ZoneInfo("UTC")
logger = logging.getLogger(__name__)


class DeploymentAgentError(Exception):
    """Base exception for Deployment Agent."""

    pass


class DeploymentAgent:
    """Orchestrates safe deployment of Salesforce projects."""

    def __init__(
        self,
        event_bus: EventBus,
        memory_manager: MemoryManager,
        tool_executor: ToolExecutor | None = None,
        cli_helper: SalesforceCliHelper | None = None,
        default_connection: DeploymentConnection | None = None,
    ):
        """Initialize Deployment Agent.

        Args:
            event_bus: EventBus for publishing events
            memory_manager: MemoryManager for persistence
            tool_executor: ToolExecutor for Salesforce CLI operations
            cli_helper: Optional pre-built CLI helper
            default_connection: Default org connection from settings
        """
        self.event_bus = event_bus
        self.memory_manager = memory_manager
        self.tool_executor = tool_executor
        self.cli_helper = cli_helper or SalesforceCliHelper(tool_executor=tool_executor)
        self.default_connection = default_connection
        self.connection_manager = ConnectionManager(cli_helper=self.cli_helper)
        self.logger = logger
        self.active_deployments: dict = {}

    async def deploy(
        self,
        request: DeploymentRequest,
    ) -> DeploymentReport:
        """Deploy artifacts to Salesforce.

        Args:
            request: DeploymentRequest

        Returns:
            DeploymentReport with results
        """
        try:
            deployment_id = str(uuid.uuid4())

            self.logger.info(
                f"Deployment Agent starting: strategy={request.strategy.value}, "
                f"environment={request.environment.value}, "
                f"artifacts={len(request.artifacts)}"
            )

            # Publish deployment started event
            await self.event_bus.publish(
                "deployment.started",
                {
                    "deployment_id": deployment_id,
                    "workflow_id": request.workflow_id,
                    "environment": request.environment.value,
                    "strategy": request.strategy.value,
                },
            )

            # Verify prerequisites
            await self._verify_prerequisites(request)

            # Create connection
            auth = await self.connection_manager.create_connection(
                request.connection
            )
            
            # Production Guard: Ensure we aren't using a simulated connection for Production
            auth_details = await auth.authenticate()
            if request.environment == DeploymentEnvironment.PRODUCTION and auth_details.get("source") == "simulated":
                raise DeploymentAgentError(
                    "Security Block: Cannot use simulated authentication for Production environment."
                )

            # Execute deployment
            report = await self._execute_deployment(request, auth)

            # Store in history
            await self._record_deployment_history(report)

            # Publish deployment completed event
            await self.event_bus.publish(
                "deployment.completed",
                {
                    "deployment_id": report.deployment_id,
                    "status": report.status.value,
                    "duration_seconds": report.deployment_duration_seconds,
                },
            )

            self.logger.info(
                f"Deployment completed: status={report.status.value}, "
                f"duration={report.deployment_duration_seconds}s"
            )

            return report

        except Exception as e:
            self.logger.error(f"Deployment failed: {e}", exc_info=True)
            await self.event_bus.publish(
                "deployment.failed",
                {
                    "workflow_id": request.workflow_id,
                    "error": str(e),
                },
            )
            raise DeploymentAgentError(f"Deployment failed: {e}") from e

    async def _verify_prerequisites(self, request: DeploymentRequest) -> None:
        """Verify deployment prerequisites.

        Args:
            request: DeploymentRequest

        Raises:
            DeploymentAgentError: If prerequisites not met
        """
        self.logger.info("Verifying deployment prerequisites")

        # Check connection details
        if not request.connection.org_id:
            raise DeploymentAgentError("Missing org_id")

        # Check artifacts
        if not request.artifacts:
            raise DeploymentAgentError("No artifacts to deploy")

        # Check environment compatibility
        if request.environment == DeploymentEnvironment.PRODUCTION:
            if not request.connection.is_production:
                raise DeploymentAgentError(
                    "Production deployment requires production connection"
                )

    async def _execute_deployment(
        self,
        request: DeploymentRequest,
        auth,
    ) -> DeploymentReport:
        """Execute the deployment.

        Args:
            request: DeploymentRequest
            auth: SalesforceAuth instance

        Returns:
            DeploymentReport
        """
        executor = DeploymentExecutor(auth, cli_helper=self.cli_helper)
        monitor = DeploymentMonitor(auth, cli_helper=self.cli_helper)

        # Execute deployment
        report = await executor.execute_deployment(request)

        # Monitor progress
        report = await monitor.monitor_progress(
            report,
            max_wait_minutes=request.max_wait_time_minutes,
        )

        # Collect logs and metrics
        if report.status in [
            DeploymentStatus.SUCCEEDED,
            DeploymentStatus.PARTIALLY_SUCCEEDED,
        ]:
            report.metrics.test_summary = await monitor.collect_test_results(
                report.deployment_id
            )

        # Analyze failures if any
        if report.status == DeploymentStatus.FAILED:
            failure_analysis = await monitor.analyze_deployment_failures(report)
            report.error_details = failure_analysis

            # Check if recoverable
            if await self._is_failure_recoverable(report):
                # Attempt recovery via Recovery Agent
                await self._attempt_recovery(report, request)
            else:
                # Plan rollback
                rollback_mgr = RollbackManager(auth)
                if await rollback_mgr.can_rollback(report):
                    report.rollback_plan = await rollback_mgr.plan_rollback(report)
                    report.rollback_plan.is_executable = True

        return report

    async def _is_failure_recoverable(self, report: DeploymentReport) -> bool:
        """Check if deployment failure is recoverable.

        Args:
            report: DeploymentReport

        Returns:
            True if failure appears recoverable
        """
        if not report.error_details:
            return False

        failure_categories = report.error_details.get(
            "failure_categories", {}
        )

        # Security/auth failures not recoverable
        unrecoverable = ["security_error", "auth_error"]

        for category in failure_categories:
            if category in unrecoverable:
                return False

        return True

    async def _attempt_recovery(
        self,
        report: DeploymentReport,
        request: DeploymentRequest,
    ) -> None:
        """Attempt recovery via Recovery Agent.

        Args:
            report: Failed DeploymentReport
            request: Original DeploymentRequest
        """
        self.logger.info(
            f"Attempting recovery for failed deployment: {report.deployment_id}"
        )

        # Publish recovery attempt event
        await self.event_bus.publish(
            "deployment.recovery_attempted",
            {
                "deployment_id": report.deployment_id,
                "failure_reason": report.failure_reason,
            },
        )

    async def _record_deployment_history(self, report: DeploymentReport) -> None:
        """Record deployment in history.

        Args:
            report: DeploymentReport
        """
        try:
            test_success = (
                report.metrics.test_summary.success_rate
                if report.metrics and report.metrics.test_summary
                and hasattr(report.metrics.test_summary, "success_rate")
                else 0.0
            )

            code_coverage = (
                report.metrics.test_summary.code_coverage_percentage
                if report.metrics and report.metrics.test_summary
                and hasattr(report.metrics.test_summary, "code_coverage_percentage")
                else 0.0
            )

            deployed_count = (
                report.metrics.deployed_components
                if report.metrics
                else 0
            )

            await self.memory_manager.store_deployment_history(
                deployment_id=report.deployment_id,
                environment=report.environment.value,
                status=report.status.value,
                version_id=str(uuid.uuid4()),
                components_count=deployed_count,
                deployment_time_seconds=report.deployment_duration_seconds,
                test_success_rate=test_success,
                code_coverage_percentage=code_coverage,
                created_by="deployment_agent",
            )
        except Exception as e:
            self.logger.warning(f"Failed to record deployment history: {e}")

    async def quick_deploy(
        self,
        connection: DeploymentConnection,
        deployment_id: str,
    ) -> DeploymentReport:
        """Quick deploy a previously validated deployment.

        Args:
            connection: DeploymentConnection
            deployment_id: ID of validated deployment

        Returns:
            DeploymentReport
        """
        self.logger.info(f"Quick deploying: {deployment_id}")

        # Create connection
        auth = await self.connection_manager.create_connection(connection)

        # Execute quick deploy
        executor = DeploymentExecutor(auth, cli_helper=self.cli_helper)
        report = await executor.quick_deploy(deployment_id)

        return report

    async def rollback_deployment(
        self,
        connection: DeploymentConnection,
        deployment_report: DeploymentReport,
    ) -> bool:
        """Rollback a failed deployment.

        Args:
            connection: DeploymentConnection
            deployment_report: DeploymentReport to rollback

        Returns:
            True if rollback successful
        """
        try:
            self.logger.info(
                f"Rolling back deployment: {deployment_report.deployment_id}"
            )

            # Create connection
            auth = await self.connection_manager.create_connection(connection)

            # Initialize rollback manager
            rollback_mgr = RollbackManager(auth)

            # Check if can rollback
            if not await rollback_mgr.can_rollback(deployment_report):
                self.logger.warning("Deployment cannot be rolled back")
                return False

            # Execute rollback
            success = await rollback_mgr.execute_rollback(
                deployment_report.rollback_plan
            )

            if success:
                deployment_report.status = DeploymentStatus.ROLLED_BACK

            # Publish event
            await self.event_bus.publish(
                "deployment.rollback_completed",
                {
                    "deployment_id": deployment_report.deployment_id,
                    "success": success,
                },
            )

            return success

        except Exception as e:
            self.logger.error(f"Rollback failed: {e}", exc_info=True)
            await self.event_bus.publish(
                "deployment.rollback_failed",
                {
                    "deployment_id": deployment_report.deployment_id,
                    "error": str(e),
                },
            )
            return False

    async def get_deployment_status(self, deployment_id: str) -> Optional[dict]:
        """Get status of a deployment.

        Args:
            deployment_id: Deployment ID

        Returns:
            Status dictionary or None
        """
        return self.active_deployments.get(deployment_id)

    async def list_deployments(self) -> dict:
        """List all active deployments.

        Returns:
            Dictionary of active deployments
        """
        return self.active_deployments

    async def close(self) -> None:
        """Close all connections."""
        await self.connection_manager.close_all()
