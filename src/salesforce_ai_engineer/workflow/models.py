"""Runtime models for workflow execution."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from salesforce_ai_engineer.agent.models import ExecutionPlan, ExecutionTask, TaskStatus
from salesforce_ai_engineer.models.domain import WorkflowStatus, utc_now


class WorkflowRunStatus(StrEnum):
    """Runtime lifecycle states for workflow execution."""

    INITIALIZED = "initialized"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    SUCCESS = "success"
    FAILED = "failed"
    ESCALATED = "escalated"
    ARCHIVED = "archived"


class StateTransition(BaseModel):
    """Auditable state transition for a workflow task."""

    from_state: str
    to_state: str
    at: datetime = Field(default_factory=utc_now)
    reason: str = ""


class RetryAttempt(BaseModel):
    """Trace of one task execution attempt."""

    attempt: int
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    success: bool = False
    error: str | None = None
    recovery_action: str | None = None
    backoff_seconds: float = 0.0


class TaskExecutionTrace(BaseModel):
    """Complete trace for one task in a workflow run."""

    task_id: str
    agent: str
    dependencies: list[str] = Field(default_factory=list)
    execution_context: dict[str, Any] = Field(default_factory=dict)
    state_transitions: list[StateTransition] = Field(default_factory=list)
    retry_history: list[RetryAttempt] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    output: dict[str, Any] | None = None
    error: str | None = None


class WorkflowRetryPolicy(BaseModel):
    """Configurable retry and backoff policy."""

    max_attempts: int = Field(default=2, ge=1)
    initial_backoff_seconds: float = Field(default=0.05, ge=0.0)
    max_backoff_seconds: float = Field(default=2.0, ge=0.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    recoverable_exceptions: list[str] = Field(default_factory=lambda: ["Exception"])

    def delay_for(self, retry_index: int) -> float:
        return min(
            self.initial_backoff_seconds * (self.backoff_multiplier**retry_index),
            self.max_backoff_seconds,
        )


class WorkflowExecutionPolicy(BaseModel):
    """Runtime execution policy for a workflow."""

    max_parallel_tasks: int = Field(default=4, ge=1)
    task_timeout_seconds: float | None = Field(default=None, gt=0)
    retry_policy: WorkflowRetryPolicy = Field(default_factory=WorkflowRetryPolicy)
    fail_fast: bool = True
    rollback_on_failure: bool = True
    checkpoint_after_each_task: bool = True


class WorkflowSnapshot(BaseModel):
    """Serializable workflow state for persistence and restoration."""

    workflow_id: str
    request: str
    plan: ExecutionPlan
    version: int = Field(default=1, ge=1)
    status: WorkflowRunStatus = WorkflowRunStatus.INITIALIZED
    current_task_ids: list[str] = Field(default_factory=list)
    completed_task_ids: list[str] = Field(default_factory=list)
    failed_task_ids: list[str] = Field(default_factory=list)
    skipped_task_ids: list[str] = Field(default_factory=list)
    cancelled_task_ids: list[str] = Field(default_factory=list)
    traces: dict[str, TaskExecutionTrace] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowProgress(BaseModel):
    """Progress summary emitted during workflow execution."""

    workflow_id: str
    status: WorkflowRunStatus
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    skipped_tasks: int
    running_tasks: int
    percent_complete: float = Field(ge=0.0, le=100.0)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowExecutionResult(BaseModel):
    """Final result returned by the workflow engine."""

    workflow_id: str
    request: str
    status: WorkflowStatus
    run_status: WorkflowRunStatus
    plan_id: str
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    skipped_tasks: int = 0
    cancelled_tasks: int = 0
    escalated: bool = False
    tasks: list[ExecutionTask]
    traces: dict[str, TaskExecutionTrace] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime
    summary: str


class WorkflowDefinition(BaseModel):
    """Submitted workflow definition with runtime metadata."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    request: str
    plan: ExecutionPlan
    version: int = 1
    policy: WorkflowExecutionPolicy = Field(default_factory=WorkflowExecutionPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)
