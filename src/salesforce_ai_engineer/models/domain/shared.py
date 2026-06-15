"""Shared domain models for the autonomous Salesforce AI Engineer.

The objects in this module form the stable vocabulary used by agents,
tools, APIs, persistence, and workflow orchestration. Models are designed
for JSON serialization, explicit validation, and long-term extensibility.
Runtime execution objects remain mutable because the orchestrator updates
their state; records and reports are immutable once created.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class DomainModel(BaseModel):
    """Base model with predictable JSON behavior for shared domain objects."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        use_enum_values=False,
        validate_assignment=True,
    )


class ImmutableDomainModel(DomainModel):
    """Base model for append-only records and completed reports."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        use_enum_values=False,
    )


class TaskStatus(StrEnum):
    """Lifecycle state for a workflow task."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class WorkflowStatus(StrEnum):
    """Lifecycle state for an end-to-end workflow."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ESCALATED = "escalated"


class RecoveryAction(StrEnum):
    """Action selected by a recovery agent."""

    RETRY = "retry"
    ESCALATE = "escalate"


class SalesforceWorkType(StrEnum):
    """Supported Salesforce engineering work categories."""

    SALESFORCE_PROJECT = "salesforce_project"
    METADATA_GENERATION = "metadata_generation"
    APEX = "apex"
    LWC = "lwc"
    FLOW = "flow"
    SECURITY = "security"
    DEPLOYMENT = "deployment"
    ANALYSIS = "analysis"
    TESTING = "testing"
    DOCUMENTATION = "documentation"


class Severity(StrEnum):
    """Standard severity scale for structured reports."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ToolStatus(StrEnum):
    """Status returned by tool execution."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ToolErrorType(StrEnum):
    """Normalized error categories for tool execution."""

    VALIDATION = "validation"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    PERMISSION = "permission"
    EXTERNAL_PROCESS = "external_process"
    NETWORK = "network"
    SERIALIZATION = "serialization"
    DATABASE = "database"
    UNKNOWN = "unknown"


class VerificationStatus(StrEnum):
    """Result state for verification activity."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


class DeploymentStatus(StrEnum):
    """Result state for deployment activity."""

    PLANNED = "planned"
    VALIDATED = "validated"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ExecutionTask(DomainModel):
    """A single atomic unit of work in an execution plan."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str
    agent: str
    work_type: SalesforceWorkType = SalesforceWorkType.SALESFORCE_PROJECT
    priority: int = Field(default=3, ge=1, le=5)
    dependencies: list[str] = Field(default_factory=list)
    input: dict[str, Any] = Field(default_factory=dict)
    deliverables: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=2, ge=1)
    output: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: Any) -> Any:
        """Clamp priority to valid range [1, 5] if LLM hallucinates values."""
        if isinstance(value, (int, float, str)):
            try:
                v = int(value)
                return max(1, min(5, v))
            except (ValueError, TypeError):
                return 3
        return value

    @field_validator("input", mode="before")
    @classmethod
    def normalize_input(cls, value: Any) -> dict[str, Any]:
        """Ensure the input field is always a dictionary, converting lists if necessary."""
        if isinstance(value, list):
            if not value:
                return {}
            # If list of key-value pairs/dicts, merge them
            if all(isinstance(item, dict) for item in value):
                result = {}
                for item in value:
                    result.update(item)
                return result
        return value if isinstance(value, dict) else {}

    @field_validator("work_type", mode="before")
    @classmethod
    def normalize_work_type(cls, value: Any) -> Any:
        """Accept enum member names (e.g. SALESFORCE_PROJECT) from LLM output."""

        if isinstance(value, SalesforceWorkType):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped in SalesforceWorkType.__members__:
                return SalesforceWorkType[stripped].value
            lowered = stripped.lower()
            for member in SalesforceWorkType:
                if member.value == lowered:
                    return lowered
        return value

    @field_validator("dependencies")
    @classmethod
    def dependencies_must_be_unique(cls, dependencies: list[str]) -> list[str]:
        """Ensure dependency declarations cannot produce ambiguous edges."""

        if len(dependencies) != len(set(dependencies)):
            raise ValueError("Task dependencies must be unique")
        return dependencies

    @field_validator("description", "title")
    @classmethod
    def text_must_not_include_code_blocks(cls, value: str) -> str:
        """Keep planning models free of generated executable code blocks."""

        if "```" in value or ("public " in value and ("class " in value or "interface " in value)):
            raise ValueError("Domain task text must not include executable code blocks")
        return value


class ExecutionPlan(DomainModel):
    """Dependency graph of tasks produced by the planner."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    project: str = "Unspecified Project"
    objective: str
    summary: str = ""
    missing_information: list[str] = Field(default_factory=list)
    tasks: list[ExecutionTask]
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        """Return true when no plan-level or task-level information is missing."""

        return not self.missing_information and all(
            not task.missing_information for task in self.tasks
        )

    @model_validator(mode="after")
    def validate_dependencies(self) -> "ExecutionPlan":
        """Validate that task dependencies reference known tasks and are acyclic."""

        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("Task ids must be unique")

        known_ids = set(ids)
        for task in self.tasks:
            missing = [dependency for dependency in task.dependencies if dependency not in known_ids]
            if missing:
                raise ValueError(f"Task {task.id!r} has unknown dependencies: {missing}")
            if task.id in task.dependencies:
                raise ValueError(f"Task {task.id!r} cannot depend on itself")

        self._ensure_acyclic()
        return self

    def task_map(self) -> dict[str, ExecutionTask]:
        """Return tasks keyed by their stable ids."""

        return {task.id: task for task in self.tasks}

    def _ensure_acyclic(self) -> None:
        graph = {task.id: set(task.dependencies) for task in self.tasks}
        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in permanent:
                return
            if task_id in temporary:
                raise ValueError("Execution plan contains a dependency cycle")
            temporary.add(task_id)
            for dependency in graph[task_id]:
                visit(dependency)
            temporary.remove(task_id)
            permanent.add(task_id)

        for task_id in graph:
            visit(task_id)


class AgentRequest(ImmutableDomainModel):
    """Request envelope sent to an autonomous agent."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    agent: str
    task_id: str | None = None
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class AgentResponse(ImmutableDomainModel):
    """Response envelope returned by an autonomous agent."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str
    workflow_id: str
    agent: str
    success: bool
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class TaskResult(DomainModel):
    """Execution result for one task."""

    task_id: str
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class RecoveryDecision(DomainModel):
    """Decision returned by a recovery agent after task failure."""

    action: RecoveryAction
    reason: str
    updated_input: dict[str, Any] = Field(default_factory=dict)


class WorkflowState(DomainModel):
    """Current mutable state of a workflow run."""

    workflow_id: str
    request: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    plan: ExecutionPlan | None = None
    current_task_id: str | None = None
    completed_task_ids: list[str] = Field(default_factory=list)
    failed_task_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowCheckpoint(DomainModel):
    """Serializable checkpoint used to resume workflow execution."""

    workflow_id: str
    request: str
    plan: ExecutionPlan
    completed_task_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorReport(ImmutableDomainModel):
    """Structured error report for failures across agents, tools, and workflows."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str | None = None
    task_id: str | None = None
    agent: str | None = None
    severity: Severity = Severity.ERROR
    message: str
    exception_type: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class VerificationReport(ImmutableDomainModel):
    """Report generated by verification agents or tools."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    task_id: str | None = None
    status: VerificationStatus
    checks: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class DeploymentReport(ImmutableDomainModel):
    """Report describing a Salesforce deployment or deployment validation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    environment: str
    status: DeploymentStatus
    components: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    errors: list[ErrorReport] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecoveryReport(ImmutableDomainModel):
    """Report describing recovery activity for a failed task."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    task_id: str
    action: RecoveryAction
    reason: str
    successful: bool
    attempts_used: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)


class RewardRecord(ImmutableDomainModel):
    """Feedback signal used by learning, evaluation, or ranking systems."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    task_id: str | None = None
    agent: str
    score: float = Field(ge=-1.0, le=1.0)
    reason: str
    metrics: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class MemoryRecord(ImmutableDomainModel):
    """Long-term memory item shared by agents."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    namespace: str
    key: str
    value: dict[str, Any]
    workflow_id: str | None = None
    task_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ToolRequest(ImmutableDomainModel):
    """Request envelope for invoking a tool."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    task_id: str | None = None
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0)
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)


class ToolResponse(ImmutableDomainModel):
    """Response envelope returned by a tool invocation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str
    workflow_id: str
    tool_name: str
    status: ToolStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    error_type: ToolErrorType | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=1)
    started_at: datetime | None = None
    completed_at: datetime = Field(default_factory=utc_now)


class ExecutionReport(ImmutableDomainModel):
    """Final report for a workflow execution."""

    workflow_id: str
    request: str
    status: WorkflowStatus
    plan_id: str
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    escalated: bool = False
    tasks: list[ExecutionTask]
    started_at: datetime
    completed_at: datetime
    summary: str
    errors: list[ErrorReport] = Field(default_factory=list)
    verification_reports: list[VerificationReport] = Field(default_factory=list)
    deployment_reports: list[DeploymentReport] = Field(default_factory=list)
    recovery_reports: list[RecoveryReport] = Field(default_factory=list)
