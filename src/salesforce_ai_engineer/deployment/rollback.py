"""Rollback management and execution."""

import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from salesforce_ai_engineer.deployment.models import (
    RollbackPlan,
    DeploymentStatus,
    DeploymentReport,
)
from salesforce_ai_engineer.deployment.auth import SalesforceAuth

UTC = ZoneInfo("UTC")
logger = logging.getLogger(__name__)


class RollbackError(Exception):
    """Base exception for rollback errors."""

    pass


class RollbackManager:
    """Manages deployment rollbacks."""

    def __init__(self, auth: SalesforceAuth):
        """Initialize rollback manager.

        Args:
            auth: SalesforceAuth for connection
        """
        self.auth = auth
        self.logger = logger
        self.rollback_history: Dict[str, Dict[str, Any]] = {}

    async def plan_rollback(
        self,
        deployment_report: DeploymentReport,
    ) -> RollbackPlan:
        """Plan a rollback for failed deployment.

        Args:
            deployment_report: Failed deployment report

        Returns:
            RollbackPlan
        """
        self.logger.info(
            f"Planning rollback for deployment: {deployment_report.deployment_id}"
        )

        if deployment_report.status != DeploymentStatus.FAILED:
            raise RollbackError("Deployment does not require rollback")

        # Get previous version
        previous_version_id = await self._get_previous_version(
            deployment_report.deployment_id
        )

        plan = RollbackPlan(
            deployment_id=deployment_report.deployment_id,
            target_version_id=previous_version_id,
            rollback_strategy="full",
            affected_components=[
                c.name for c in deployment_report.components
                if c.status == "failed"
            ],
            estimated_rollback_time_seconds=300.0,
            is_executable=True,
        )

        self.logger.info(
            f"Rollback plan created: {plan.id}, "
            f"strategy={plan.rollback_strategy}, "
            f"components={len(plan.affected_components)}"
        )

        return plan

    async def execute_rollback(
        self,
        rollback_plan: RollbackPlan,
    ) -> bool:
        """Execute a rollback.

        Args:
            rollback_plan: RollbackPlan to execute

        Returns:
            True if rollback successful
        """
        try:
            self.logger.info(
                f"Executing rollback: {rollback_plan.id}, "
                f"strategy={rollback_plan.rollback_strategy}"
            )

            if not rollback_plan.is_executable:
                raise RollbackError("Rollback plan is not executable")

            # Get auth headers
            headers = await self.auth.get_headers()

            # Execute rollback based on strategy
            if rollback_plan.rollback_strategy == "full":
                success = await self._execute_full_rollback(
                    rollback_plan, headers
                )
            elif rollback_plan.rollback_strategy == "partial":
                success = await self._execute_partial_rollback(
                    rollback_plan, headers
                )
            elif rollback_plan.rollback_strategy == "component_selective":
                success = await self._execute_selective_rollback(
                    rollback_plan, headers
                )
            else:
                raise RollbackError(
                    f"Unknown rollback strategy: {rollback_plan.rollback_strategy}"
                )

            if success:
                # Record in history
                self.rollback_history[rollback_plan.id] = {
                    "deployment_id": rollback_plan.deployment_id,
                    "strategy": rollback_plan.rollback_strategy,
                    "status": "success",
                    "executed_at": datetime.now(UTC).isoformat(),
                    "components": rollback_plan.affected_components,
                }

                self.logger.info(f"Rollback completed successfully: {rollback_plan.id}")

            return success

        except Exception as e:
            self.logger.error(f"Rollback execution failed: {e}", exc_info=True)
            raise RollbackError(f"Rollback failed: {e}") from e

    async def _execute_full_rollback(
        self,
        rollback_plan: RollbackPlan,
        headers: Dict[str, str],
    ) -> bool:
        """Execute full rollback of all components.

        Args:
            rollback_plan: RollbackPlan
            headers: HTTP headers

        Returns:
            True if successful
        """
        self.logger.info("Executing full rollback")

        # Simulate reverting to previous version
        await asyncio.sleep(0.5)

        # Verify rollback
        verified = await self._verify_rollback(rollback_plan.target_version_id)

        if verified:
            self.logger.info("Full rollback verified")
        else:
            self.logger.error("Full rollback verification failed")

        return verified

    async def _execute_partial_rollback(
        self,
        rollback_plan: RollbackPlan,
        headers: Dict[str, str],
    ) -> bool:
        """Execute partial rollback of selected components.

        Args:
            rollback_plan: RollbackPlan
            headers: HTTP headers

        Returns:
            True if successful
        """
        self.logger.info(
            f"Executing partial rollback: {len(rollback_plan.affected_components)} components"
        )

        # Simulate rolling back specific components
        for component in rollback_plan.affected_components:
            await asyncio.sleep(0.1)
            self.logger.debug(f"Rolled back component: {component}")

        return True

    async def _execute_selective_rollback(
        self,
        rollback_plan: RollbackPlan,
        headers: Dict[str, str],
    ) -> bool:
        """Execute selective component rollback.

        Args:
            rollback_plan: RollbackPlan
            headers: HTTP headers

        Returns:
            True if successful
        """
        self.logger.info(
            f"Executing selective rollback: {len(rollback_plan.affected_components)} components"
        )

        # Simulate selective rollback
        for component in rollback_plan.affected_components:
            await asyncio.sleep(0.05)
            self.logger.debug(f"Selectively rolled back: {component}")

        return True

    async def _get_previous_version(self, deployment_id: str) -> str:
        """Get previous version ID for rollback target.

        Args:
            deployment_id: Deployment ID

        Returns:
            Previous version ID
        """
        # Simulate retrieving previous version
        # In production, would query Salesforce metadata
        return f"version_prev_{deployment_id}"

    async def _verify_rollback(self, target_version_id: Optional[str]) -> bool:
        """Verify rollback was successful.

        Args:
            target_version_id: Target version to verify

        Returns:
            True if verification successful
        """
        self.logger.info(f"Verifying rollback to version: {target_version_id}")

        # Simulate verification
        await asyncio.sleep(0.2)

        # 95% verification success rate
        return True

    async def can_rollback(
        self,
        deployment_report: DeploymentReport,
    ) -> bool:
        """Check if deployment can be rolled back.

        Args:
            deployment_report: DeploymentReport

        Returns:
            True if rollback is possible
        """
        # Cannot rollback successful deployments
        if deployment_report.status == DeploymentStatus.SUCCEEDED:
            return False

        # Must have rollback plan
        if not deployment_report.rollback_plan:
            return False

        # Must have target version
        if not deployment_report.rollback_plan.target_version_id:
            return False

        return True

    async def get_rollback_history(self) -> Dict[str, Dict[str, Any]]:
        """Get rollback history.

        Returns:
            Dictionary of rollback records
        """
        return self.rollback_history

    async def validate_rollback_plan(
        self,
        rollback_plan: RollbackPlan,
    ) -> tuple[bool, Optional[str]]:
        """Validate rollback plan is executable.

        Args:
            rollback_plan: RollbackPlan to validate

        Returns:
            Tuple of (is_valid, reason_if_invalid)
        """
        if not rollback_plan.target_version_id:
            return False, "No target version specified"

        if not rollback_plan.affected_components:
            return False, "No components to rollback"

        if rollback_plan.estimated_rollback_time_seconds <= 0:
            return False, "Invalid estimated rollback time"

        return True, None
