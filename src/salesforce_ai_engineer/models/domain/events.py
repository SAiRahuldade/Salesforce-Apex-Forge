"""Domain event models and lifecycle event definitions.

Events are immutable facts published by agents, tools, and infrastructure.
They carry correlation metadata so independent components can participate in
the same workflow without compile-time coupling.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any
from uuid import uuid4

from pydantic import Field, field_validator

from salesforce_ai_engineer.models.domain.shared import ImmutableDomainModel, utc_now


class EventPriority(IntEnum):
    """Delivery and history priority for domain events."""

    LOW = 10
    NORMAL = 50
    HIGH = 80
    CRITICAL = 100


class LifecycleEvent(StrEnum):
    """Standard lifecycle events emitted by the multi-agent system."""

    TASK_CREATED = "task.created"
    TASK_EXECUTION_STARTED = "task.execution.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_RETRYING = "task.retrying"
    RECOVERY_STARTED = "recovery.started"
    RECOVERY_COMPLETED = "recovery.completed"
    RECOVERY_FAILED = "recovery.failed"
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_COMPLETED = "verification.completed"
    VERIFICATION_FAILED = "verification.failed"
    DEPLOYMENT_STARTED = "deployment.started"
    DEPLOYMENT_COMPLETED = "deployment.completed"
    DEPLOYMENT_FAILED = "deployment.failed"
    MEMORY_UPDATED = "memory.updated"
    REWARD_UPDATED = "reward.updated"
    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_CHECKPOINTED = "workflow.checkpointed"
    WORKFLOW_RESUMED = "workflow.resumed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_ESCALATED = "workflow.escalated"
    AGENT_REQUESTED = "agent.requested"
    AGENT_RESPONDED = "agent.responded"
    TOOL_REQUESTED = "tool.requested"
    TOOL_RESPONDED = "tool.responded"


class DomainEvent(ImmutableDomainModel):
    """Immutable structured event shared by every component."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    workflow_id: str | None = None
    task_id: str | None = None
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    causation_id: str | None = None
    source: str = "system"
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("name", "source")
    @classmethod
    def text_fields_must_not_be_blank(cls, value: str) -> str:
        """Reject blank event names and sources."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("Event name and source must not be blank")
        return normalized

    @classmethod
    def lifecycle(
        cls,
        event: LifecycleEvent,
        *,
        payload: dict[str, Any] | None = None,
        priority: EventPriority = EventPriority.NORMAL,
        workflow_id: str | None = None,
        task_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        source: str = "system",
    ) -> "DomainEvent":
        """Create a standard lifecycle event with explicit metadata."""

        return cls(
            name=event.value,
            payload=payload or {},
            priority=priority,
            workflow_id=workflow_id,
            task_id=task_id,
            correlation_id=correlation_id or str(uuid4()),
            causation_id=causation_id,
            source=source,
        )


class EventHistoryQuery(ImmutableDomainModel):
    """Filters for querying in-memory event history."""

    name: str | None = None
    workflow_id: str | None = None
    correlation_id: str | None = None
    source: str | None = None
    min_priority: EventPriority | None = None
    limit: int | None = Field(default=None, gt=0)
