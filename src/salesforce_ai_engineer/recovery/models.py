"""Domain models for the Recovery Agent."""

from enum import Enum
from typing import Any, Optional, List
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

UTC = ZoneInfo("UTC")


class FailureCategory(str, Enum):
    """Categories of failures that can be recovered."""
    CODE_GENERATION = "code_generation"
    METADATA = "metadata"
    DEPLOYMENT = "deployment"
    AUTHENTICATION = "authentication"
    NETWORKING = "networking"
    DEPENDENCY = "dependency"
    VALIDATION = "validation"
    GOVERNOR_LIMIT = "governor_limit"
    SECURITY = "security"
    RUNTIME = "runtime"
    FILESYSTEM = "filesystem"
    CONFIGURATION = "configuration"
    SYSTEM = "system"


class FailureSeverity(str, Enum):
    """Severity levels for failures."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecoveryStrategy(str, Enum):
    """Available recovery strategies."""
    RETRY = "retry"
    FALLBACK = "fallback"
    ROLLBACK = "rollback"
    REGENERATE = "regenerate"
    RECONFIGURE = "reconfigure"
    SKIP = "skip"
    ESCALATE = "escalate"


class RecoveryStatus(str, Enum):
    """Status of a recovery attempt."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"
    ESCALATED = "escalated"


class FailureReport(BaseModel):
    """Structured failure report."""
    id: str = Field(default_factory=lambda: f"failure-{datetime.now(UTC).timestamp()}")
    workflow_id: str
    source_agent: str
    category: FailureCategory
    severity: FailureSeverity
    title: str
    description: str
    error_message: str
    context: dict[str, Any] = Field(default_factory=dict)
    affected_artifact: Optional[str] = None
    affected_task_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    original_attempt_count: int = 0
    is_repeated: bool = False


class RecoveryAction(BaseModel):
    """Individual action in a recovery plan."""
    id: str = Field(default_factory=lambda: f"action-{datetime.now(UTC).timestamp()}")
    step_number: int
    description: str
    action_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 300
    retry_count: int = 0
    max_retries: int = 3
    backoff_multiplier: float = 2.0


class RecoveryPlan(BaseModel):
    """Structured recovery plan."""
    id: str = Field(default_factory=lambda: f"plan-{datetime.now(UTC).timestamp()}")
    failure_id: str
    failure_category: FailureCategory
    root_cause_analysis: str
    confidence: float = Field(ge=0.0, le=1.0)
    strategy: RecoveryStrategy
    actions: List[RecoveryAction] = Field(default_factory=list)
    estimated_duration_seconds: float
    rollback_plan: Optional["RecoveryPlan"] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_executable(self) -> bool:
        """Check if plan is ready for execution."""
        return len(self.actions) > 0 and self.confidence >= 0.5


class RecoveryAttempt(BaseModel):
    """Record of a recovery attempt."""
    id: str = Field(default_factory=lambda: f"attempt-{datetime.now(UTC).timestamp()}")
    failure_id: str
    plan_id: str
    strategy: RecoveryStrategy
    status: RecoveryStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    executed_actions: int = 0
    total_actions: int
    success_rate: float = 0.0
    error_during_recovery: Optional[str] = None
    duration_seconds: float = 0.0
    was_escalated: bool = False
    escalation_reason: Optional[str] = None


class RecoveryResult(BaseModel):
    """Result of recovery process."""
    id: str = Field(default_factory=lambda: f"result-{datetime.now(UTC).timestamp()}")
    failure_id: str
    recovery_attempts: List[RecoveryAttempt] = Field(default_factory=list)
    final_status: RecoveryStatus
    is_recovered: bool
    recovery_time_seconds: float
    root_cause: str
    solution_applied: str
    affected_artifact_fixed: bool
    retry_count: int
    was_escalated: bool
    escalation_details: Optional[str] = None
    learned_knowledge_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def success(self) -> bool:
        """Check if recovery was successful."""
        return self.is_recovered and self.final_status == RecoveryStatus.SUCCEEDED


class FailureSignature(BaseModel):
    """Signature of a previously encountered failure for pattern matching."""
    id: str = Field(default_factory=lambda: f"sig-{datetime.now(UTC).timestamp()}")
    category: FailureCategory
    error_pattern: str
    error_message_pattern: str
    context_patterns: dict[str, str] = Field(default_factory=dict)
    successful_recovery_strategy: RecoveryStrategy
    successful_recovery_actions: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    times_encountered: int = 0
    times_successfully_recovered: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def success_rate(self) -> float:
        """Calculate success rate of this recovery pattern."""
        if self.times_encountered == 0:
            return 0.0
        return self.times_successfully_recovered / self.times_encountered
