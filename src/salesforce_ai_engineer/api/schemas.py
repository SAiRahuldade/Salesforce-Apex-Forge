"""Request/response schemas for REST API."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from salesforce_ai_engineer.agent.models import ExecutionPlan, ExecutionTask, TaskStatus, WorkflowStatus


class WorkflowSubmissionRequest(BaseModel):
    """Submit a workflow for execution."""

    request: str = Field(..., description="Natural language request for the workflow")
    priority: Optional[str] = Field(default="normal", description="Workflow priority")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for tracking")


class WorkflowResponse(BaseModel):
    """Workflow status response."""

    workflow_id: str
    status: WorkflowStatus
    request: str
    plan_id: Optional[str] = None
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    escalated: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None


class TaskResponse(BaseModel):
    """Single task status."""

    id: str
    title: str
    description: str
    agent: str
    status: TaskStatus
    dependencies: List[str] = Field(default_factory=list)
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WorkflowDetailResponse(BaseModel):
    """Detailed workflow status."""

    workflow_id: str
    status: WorkflowStatus
    request: str
    plan_id: Optional[str] = None
    tasks: List[TaskResponse] = Field(default_factory=list)
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    escalated: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None


class ControlOperationRequest(BaseModel):
    """Request for control operations (pause, resume, cancel)."""

    reason: Optional[str] = Field(default=None, description="Reason for operation")


class ControlOperationResponse(BaseModel):
    """Response from control operation."""

    workflow_id: str
    operation: str
    status: str
    message: str


class HealthStatus(str, Enum):
    """Health status enum."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status of a component."""

    name: str
    status: HealthStatus
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """System health check response."""

    status: HealthStatus
    components: List[ComponentHealth] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentHealthResponse(BaseModel):
    """Agent health status."""

    agent_name: str
    available: bool
    status: HealthStatus
    last_execution: Optional[datetime] = None
    error_count: int = 0
    success_count: int = 0


class MetricsResponse(BaseModel):
    """System metrics."""

    total_workflows: int = 0
    completed_workflows: int = 0
    failed_workflows: int = 0
    escalated_workflows: int = 0
    average_execution_time: float = 0.0
    success_rate: float = 0.0
    agents_available: int = 0
    agents_total: int = 0
    memory_usage_percent: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: Optional[str] = None
    workflow_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
