"""Tool executor facade used by agents."""

from __future__ import annotations

import logging

from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.models.domain import (
    EventPriority,
    LifecycleEvent,
    ToolRequest,
    ToolResponse,
    ToolStatus,
    utc_now,
)
from salesforce_ai_engineer.tools.errors import classify_error
from salesforce_ai_engineer.tools.registry import ToolRegistry


class ToolExecutor:
    """Dispatches ToolRequest objects while enforcing the tool boundary."""

    def __init__(
        self,
        registry: ToolRegistry,
        event_bus: EventBus,
        logger: logging.Logger | None = None,
        *,
        logger_instance: logging.Logger | None = None,
    ) -> None:
        self.registry = registry
        self.event_bus = event_bus
        self.logger = logger or logger_instance or logging.getLogger(__name__)

    async def execute(self, request: ToolRequest) -> ToolResponse:
        """Execute a request through the registered tool implementation."""

        self.logger.info("Executing tool %s for workflow %s", request.tool_name, request.workflow_id)
        await self.event_bus.emit_lifecycle(
            LifecycleEvent.TOOL_REQUESTED,
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            correlation_id=request.correlation_id,
            source="tool_executor",
            payload={
                "request_id": request.id,
                "tool_name": request.tool_name,
                "input_keys": sorted(request.input.keys()),
            },
        )

        try:
            tool = self.registry.resolve(request.tool_name)
            response = await tool.execute(request)
        except Exception as exc:
            completed = utc_now()
            response = ToolResponse(
                request_id=request.id,
                workflow_id=request.workflow_id,
                tool_name=request.tool_name,
                status=ToolStatus.FAILED,
                error=str(exc),
                error_type=classify_error(exc),
                completed_at=completed,
                metrics={"completed_at": completed.isoformat()},
            )

        priority = EventPriority.HIGH if response.status != ToolStatus.SUCCESS else EventPriority.NORMAL
        await self.event_bus.emit_lifecycle(
            LifecycleEvent.TOOL_RESPONDED,
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            correlation_id=request.correlation_id,
            source="tool_executor",
            priority=priority,
            payload=response.model_dump(mode="json"),
        )
        return response

