"""Salesforce CLI integration with graceful simulation fallback."""

from __future__ import annotations

import logging
from typing import Any

from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus
from salesforce_ai_engineer.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)


class SalesforceCliHelper:
    """Thin wrapper around SalesforceCliTool via ToolExecutor."""

    def __init__(
        self,
        tool_executor: ToolExecutor | None = None,
        default_org: str = "",
        enabled: bool = True,
    ) -> None:
        self.tool_executor = tool_executor
        self.default_org = default_org
        self.enabled = enabled
        self._available: bool | None = None

    async def is_available(self) -> bool:
        if not self.enabled or self.tool_executor is None:
            return False
        if self._available is not None:
            return self._available
        try:
            response = await self.tool_executor.execute(
                ToolRequest(
                    tool_name="sf",
                    input={"operation": "org_list", "json_output": True, "timeout": 30},
                )
            )
            self._available = response.status == ToolStatus.SUCCESS
        except Exception:
            self._available = False
        return self._available

    async def org_display(self, target_org: str | None = None) -> dict[str, Any] | None:
        org = target_org or self.default_org
        if not org or self.tool_executor is None:
            return None
        try:
            response = await self.tool_executor.execute(
                ToolRequest(
                    tool_name="sf",
                    input={
                        "operation": "org_info",
                        "target_org": org,
                        "json_output": True,
                        "timeout": 60,
                    },
                )
            )
            if response.status != ToolStatus.SUCCESS:
                return None
            return response.output
        except Exception as exc:
            logger.debug("sf org display failed: %s", exc)
            return None

    async def project_deploy(
        self,
        target_org: str | None = None,
        *,
        flags: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any] | None:
        org = target_org or self.default_org
        if not org or self.tool_executor is None:
            return None

        deploy_flags = dict(flags or {})
        if dry_run:
            deploy_flags.setdefault("dry-run", True)

        try:
            response = await self.tool_executor.execute(
                ToolRequest(
                    tool_name="sf",
                    input={
                        "operation": "project_deploy",
                        "target_org": org,
                        "flags": deploy_flags,
                        "json_output": True,
                        "timeout": int(deploy_flags.pop("timeout", 600)),
                    },
                )
            )
            if response.status != ToolStatus.SUCCESS:
                return None
            return response.output
        except Exception as exc:
            logger.debug("sf project deploy failed: %s", exc)
            return None

    async def project_deploy_quick(
        self,
        job_id: str,
        target_org: str | None = None,
    ) -> dict[str, Any] | None:
        org = target_org or self.default_org
        if not org or self.tool_executor is None:
            return None
        try:
            response = await self.tool_executor.execute(
                ToolRequest(
                    tool_name="sf",
                    input={
                        "operation": "custom_command",
                        "target_org": org,
                        "command": f"project deploy quick --job-id {job_id}",
                        "json_output": True,
                        "timeout": 600,
                    },
                )
            )
            if response.status != ToolStatus.SUCCESS:
                return None
            return response.output
        except Exception as exc:
            logger.debug("sf quick deploy failed: %s", exc)
            return None
