"""
Memory domain models for the autonomous multi-agent AI system.

Defines strongly-typed memory records that represent all persistent information
generated during the system's lifetime. All models use Pydantic for validation.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Literal
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class MemoryCategory(str, Enum):
    """Categories of memory records."""
    PROJECT_MEMORY = "project_memory"
    WORKFLOW_HISTORY = "workflow_history"
    EXECUTION_HISTORY = "execution_history"
    AGENT_INTERACTION = "agent_interaction"
    COMPLETED_TASK = "completed_task"
    RECOVERY_HISTORY = "recovery_history"
    DEPLOYMENT_HISTORY = "deployment_history"
    ARCHITECTURE_DECISION = "architecture_decision"
    KNOWN_ERROR = "known_error"
    SUCCESSFUL_FIX = "successful_fix"
    USER_PREFERENCE = "user_preference"
    CODING_PATTERN = "coding_pattern"
    REWARD_RECORD = "reward_record"
    EXECUTION_METRIC = "execution_metric"


class MemoryStatus(str, Enum):
    """Status of a memory record."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class MemoryTag(BaseModel):
    """Tag for categorizing and organizing memory records."""
    name: str = Field(..., min_length=1, max_length=100)
    value: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def __str__(self) -> str:
        if self.value:
            return f"{self.name}={self.value}"
        return self.name


class MemoryMetadata(BaseModel):
    """Metadata associated with a memory record."""
    source: str = Field(..., description="Source that created this record")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score (0-1)")
    relevance: float = Field(default=1.0, ge=0.0, le=1.0, description="Relevance score (0-1)")
    priority: int = Field(default=5, ge=1, le=10, description="Priority level (1-10)")
    ttl_seconds: Optional[int] = Field(None, description="Time to live in seconds")
    custom: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata")


class BaseMemoryRecord(BaseModel):
    """Abstract base for all memory records."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    category: MemoryCategory
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=10000)
    content: Dict[str, Any] = Field(default_factory=dict, description="Main content")
    tags: List[MemoryTag] = Field(default_factory=list)
    metadata: MemoryMetadata
    status: MemoryStatus = MemoryStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(..., description="Agent or user who created this record")
    
    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v):
        if not isinstance(v, list):
            return v
        return [t if isinstance(t, MemoryTag) else MemoryTag(**t) for t in v]


class ProjectMemory(BaseMemoryRecord):
    """Long-term project-level knowledge."""
    category: Literal[MemoryCategory.PROJECT_MEMORY] = MemoryCategory.PROJECT_MEMORY
    key_insights: List[str] = Field(default_factory=list, description="Key insights about the project")
    technical_stack: List[str] = Field(default_factory=list, description="Technologies used")
    architecture_components: List[str] = Field(default_factory=list, description="Major components")
    constraints: List[str] = Field(default_factory=list, description="Known constraints")
    goals: List[str] = Field(default_factory=list, description="Project goals")


class WorkflowHistory(BaseMemoryRecord):
    """Record of completed workflows."""
    category: Literal[MemoryCategory.WORKFLOW_HISTORY] = MemoryCategory.WORKFLOW_HISTORY
    workflow_id: str
    workflow_type: str = Field(..., description="Type of workflow executed")
    workflow_status: str = Field(..., description="Final workflow status")
    duration_seconds: float
    start_time: datetime
    end_time: datetime
    steps_executed: List[str] = Field(default_factory=list, description="Steps executed in order")
    outcomes: Dict[str, Any] = Field(default_factory=dict, description="Workflow outcomes")
    issues_encountered: List[str] = Field(default_factory=list, description="Issues during execution")


class ExecutionHistory(BaseMemoryRecord):
    """Record of individual agent executions."""
    category: Literal[MemoryCategory.EXECUTION_HISTORY] = MemoryCategory.EXECUTION_HISTORY
    agent_name: str
    execution_id: str
    task_description: str
    duration_seconds: float
    success: bool
    error: Optional[str] = None
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    resource_usage: Dict[str, Any] = Field(default_factory=dict, description="CPU, memory, etc.")
    correlation_id: Optional[str] = None


class AgentInteraction(BaseMemoryRecord):
    """Record of interactions between agents."""
    category: Literal[MemoryCategory.AGENT_INTERACTION] = MemoryCategory.AGENT_INTERACTION
    initiator_agent: str
    target_agent: str
    interaction_type: str = Field(..., description="Type of interaction")
    request_data: Dict[str, Any]
    response_data: Dict[str, Any]
    duration_seconds: float
    success: bool
    error: Optional[str] = None


class CompletedTask(BaseMemoryRecord):
    """Record of completed tasks."""
    category: Literal[MemoryCategory.COMPLETED_TASK] = MemoryCategory.COMPLETED_TASK
    task_type: str
    task_id: str
    agent_responsible: str
    duration_seconds: float
    success: bool
    approach_used: str = Field(..., description="Approach or algorithm used")
    result_summary: str
    lessons_learned: List[str] = Field(default_factory=list)
    similar_past_tasks: List[str] = Field(default_factory=list, description="IDs of similar tasks")


class RecoveryHistory(BaseMemoryRecord):
    """Record of recovery from failures."""
    category: Literal[MemoryCategory.RECOVERY_HISTORY] = MemoryCategory.RECOVERY_HISTORY
    failure_id: str
    failure_type: str
    failure_description: str
    recovery_strategy: str
    recovery_steps: List[str]
    recovery_success: bool
    time_to_recovery_seconds: float
    root_cause: Optional[str] = None
    preventive_measures: List[str] = Field(default_factory=list)


class DeploymentHistory(BaseMemoryRecord):
    """Record of system deployments."""
    category: Literal[MemoryCategory.DEPLOYMENT_HISTORY] = MemoryCategory.DEPLOYMENT_HISTORY
    deployment_id: str
    version: str
    environment: str = Field(..., description="dev/staging/prod")
    changes: List[str] = Field(default_factory=list, description="Changes deployed")
    deployment_duration_seconds: float
    success: bool
    rollback_required: bool = False
    deployment_notes: str = ""
    metrics_before: Dict[str, Any] = Field(default_factory=dict)
    metrics_after: Dict[str, Any] = Field(default_factory=dict)


class ArchitectureDecision(BaseMemoryRecord):
    """Record of architectural decisions (ADR)."""
    category: Literal[MemoryCategory.ARCHITECTURE_DECISION] = MemoryCategory.ARCHITECTURE_DECISION
    decision_id: str
    decision_status: str = Field(..., description="proposed/accepted/deprecated")
    context: str = Field(..., description="Context that led to this decision")
    decision: str = Field(..., description="The decision made")
    consequences: List[str] = Field(default_factory=list, description="Consequences of this decision")
    alternatives_considered: List[str] = Field(default_factory=list)
    rationale: str = Field(..., description="Why this decision was made")


class KnownError(BaseMemoryRecord):
    """Record of known errors and issues."""
    category: Literal[MemoryCategory.KNOWN_ERROR] = MemoryCategory.KNOWN_ERROR
    error_type: str
    error_code: Optional[str] = None
    error_message: str
    reproduction_steps: List[str] = Field(default_factory=list)
    affected_components: List[str] = Field(default_factory=list)
    workaround: Optional[str] = None
    fix_available: bool = False
    fix_id: Optional[str] = None
    severity: str = Field(..., description="critical/high/medium/low")


class SuccessfulFix(BaseMemoryRecord):
    """Record of successful fixes for errors."""
    category: Literal[MemoryCategory.SUCCESSFUL_FIX] = MemoryCategory.SUCCESSFUL_FIX
    fix_id: str
    related_error_id: Optional[str] = None
    error_type: str
    error_description: str
    fix_description: str
    fix_steps: List[str]
    time_to_fix_minutes: float
    who_fixed: str = Field(..., description="Agent or person who fixed it")
    prevention_strategy: Optional[str] = None
    fix_verified: bool = False


class UserPreference(BaseMemoryRecord):
    """Record of user preferences."""
    category: Literal[MemoryCategory.USER_PREFERENCE] = MemoryCategory.USER_PREFERENCE
    preference_key: str
    preference_value: Any
    applies_to_agents: List[str] = Field(default_factory=list, description="Which agents use this")
    scope: str = Field(..., description="user/team/system")


class CodingPattern(BaseMemoryRecord):
    """Record of successful coding patterns."""
    category: Literal[MemoryCategory.CODING_PATTERN] = MemoryCategory.CODING_PATTERN
    pattern_name: str
    pattern_description: str
    code_example: str
    use_cases: List[str]
    pros: List[str]
    cons: List[str]
    alternatives: List[str] = Field(default_factory=list)
    best_for_languages: List[str] = Field(default_factory=list)


class RewardRecord(BaseMemoryRecord):
    """Record of rewards for successful executions."""
    category: Literal[MemoryCategory.REWARD_RECORD] = MemoryCategory.REWARD_RECORD
    agent_name: str
    task_id: str
    task_type: str
    reward_amount: float
    reason: str = Field(..., description="Why reward was given")
    timestamp: datetime


class ExecutionMetric(BaseMemoryRecord):
    """Record of execution metrics and statistics."""
    category: Literal[MemoryCategory.EXECUTION_METRIC] = MemoryCategory.EXECUTION_METRIC
    metric_name: str
    metric_value: float
    unit: str = Field(..., description="Unit of measurement")
    agent_name: Optional[str] = None
    execution_id: Optional[str] = None
    timewindow_start: datetime
    timewindow_end: datetime
    tags_dict: Dict[str, str] = Field(default_factory=dict, description="Additional metric tags")


class MemorySearchQuery(BaseModel):
    """Query for searching memory records."""
    keywords: Optional[List[str]] = None
    category: Optional[MemoryCategory] = None
    status: Optional[MemoryStatus] = None
    tags: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    created_by: Optional[str] = None
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=100, ge=1, le=10000)
    offset: int = Field(default=0, ge=0)


class MemoryFilter(BaseModel):
    """Advanced filter for memory records."""
    field: str
    operator: Literal["eq", "ne", "gt", "lt", "gte", "lte", "in", "contains", "regex"]
    value: Any


class MemoryRelationship(BaseModel):
    """Relationship between two memory records."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str = Field(..., description="ID of source record")
    target_id: str = Field(..., description="ID of target record")
    relationship_type: str = Field(..., description="Type of relationship")
    bidirectional: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MemoryVersion(BaseModel):
    """Version history entry for a memory record."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    record_id: str
    version_number: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    content_before: Dict[str, Any]
    content_after: Dict[str, Any]
    change_description: str
    change_type: str = Field(..., description="create/update/delete")


# Type union for all memory record types
MemoryRecord = (
    ProjectMemory
    | WorkflowHistory
    | ExecutionHistory
    | AgentInteraction
    | CompletedTask
    | RecoveryHistory
    | DeploymentHistory
    | ArchitectureDecision
    | KnownError
    | SuccessfulFix
    | UserPreference
    | CodingPattern
    | RewardRecord
    | ExecutionMetric
)


def create_memory_record(
    category: MemoryCategory,
    title: str,
    created_by: str,
    **kwargs
) -> MemoryRecord:
    """
    Factory function to create appropriate memory record based on category.
    
    Args:
        category: Category of memory record to create
        title: Title of the record
        created_by: Who is creating this record
        **kwargs: Additional fields for the specific record type
    
    Returns:
        Appropriate MemoryRecord subclass instance
    """
    metadata = kwargs.pop("metadata", None)
    if metadata is None:
        metadata = MemoryMetadata(source=created_by)
    elif isinstance(metadata, dict):
        metadata = MemoryMetadata(**metadata)
    
    base_fields = {
        "title": title,
        "created_by": created_by,
        "metadata": metadata,
    }
    
    if category == MemoryCategory.PROJECT_MEMORY:
        return ProjectMemory(**base_fields, **kwargs)
    elif category == MemoryCategory.WORKFLOW_HISTORY:
        return WorkflowHistory(**base_fields, **kwargs)
    elif category == MemoryCategory.EXECUTION_HISTORY:
        return ExecutionHistory(**base_fields, **kwargs)
    elif category == MemoryCategory.AGENT_INTERACTION:
        return AgentInteraction(**base_fields, **kwargs)
    elif category == MemoryCategory.COMPLETED_TASK:
        return CompletedTask(**base_fields, **kwargs)
    elif category == MemoryCategory.RECOVERY_HISTORY:
        return RecoveryHistory(**base_fields, **kwargs)
    elif category == MemoryCategory.DEPLOYMENT_HISTORY:
        return DeploymentHistory(**base_fields, **kwargs)
    elif category == MemoryCategory.ARCHITECTURE_DECISION:
        return ArchitectureDecision(**base_fields, **kwargs)
    elif category == MemoryCategory.KNOWN_ERROR:
        return KnownError(**base_fields, **kwargs)
    elif category == MemoryCategory.SUCCESSFUL_FIX:
        return SuccessfulFix(**base_fields, **kwargs)
    elif category == MemoryCategory.USER_PREFERENCE:
        return UserPreference(**base_fields, **kwargs)
    elif category == MemoryCategory.CODING_PATTERN:
        return CodingPattern(**base_fields, **kwargs)
    elif category == MemoryCategory.REWARD_RECORD:
        return RewardRecord(**base_fields, **kwargs)
    elif category == MemoryCategory.EXECUTION_METRIC:
        return ExecutionMetric(**base_fields, **kwargs)
    else:
        raise ValueError(f"Unknown memory category: {category}")
