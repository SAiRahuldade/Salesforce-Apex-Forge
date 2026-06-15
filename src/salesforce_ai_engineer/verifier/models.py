"""Domain models for the Verifier Agent."""

from enum import Enum
from typing import Any
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

UTC = ZoneInfo("UTC")


class IssueSeverity(str, Enum):
    """Severity levels for verification issues."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IssueCategory(str, Enum):
    """Categories of verification issues."""
    SYNTAX_ERROR = "syntax_error"
    LOGIC_ERROR = "logic_error"
    SECURITY = "security"
    GOVERNOR_LIMIT = "governor_limit"
    CRUD_FLS = "crud_fls"
    BULKIFICATION = "bulkification"
    PERFORMANCE = "performance"
    NAMING_CONVENTION = "naming_convention"
    DOCUMENTATION = "documentation"
    ARCHITECTURE = "architecture"
    BEST_PRACTICE = "best_practice"
    METADATA_CONSISTENCY = "metadata_consistency"
    DEPENDENCY = "dependency"
    DUPLICATE = "duplicate"


class ArtifactType(str, Enum):
    """Types of Salesforce artifacts."""
    APEX_CLASS = "apex_class"
    APEX_TRIGGER = "apex_trigger"
    BATCH_APEX = "batch_apex"
    QUEUEABLE_APEX = "queueable_apex"
    SCHEDULED_APEX = "scheduled_apex"
    LWC = "lwc"
    AURA = "aura"
    FLOW = "flow"
    VALIDATION_RULE = "validation_rule"
    PERMISSION_SET = "permission_set"
    PROFILE = "profile"
    SHARING_RULE = "sharing_rule"
    CUSTOM_OBJECT = "custom_object"
    CUSTOM_FIELD = "custom_field"
    PAGE_LAYOUT = "page_layout"
    RECORD_TYPE = "record_type"
    SOQL = "soql"
    SOSL = "sosl"
    DEPLOYMENT_MANIFEST = "deployment_manifest"


class VerificationIssue(BaseModel):
    """Individual verification issue found during analysis."""
    id: str = Field(default_factory=lambda: f"issue-{datetime.now(UTC).timestamp()}")
    artifact_id: str
    artifact_type: ArtifactType
    category: IssueCategory
    severity: IssueSeverity
    title: str
    description: str
    location: dict[str, Any] = Field(default_factory=dict)  # line, column, method, etc.
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)  # 0-1 confidence score
    recommendations: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    remediation_effort: str = Field(default="medium")  # low, medium, high, critical
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ComponentMetrics(BaseModel):
    """Metrics for a single component."""
    component_id: str
    component_type: ArtifactType
    total_lines: int = 0
    complexity_score: float = 0.0  # 0-10
    security_score: float = 0.0  # 0-10
    performance_score: float = 0.0  # 0-10
    maintainability_score: float = 0.0  # 0-10
    coverage_score: float = 0.0  # 0-100 (test coverage %)
    issue_count: int = 0
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0
    info_issues: int = 0


class QualityScore(BaseModel):
    """Overall quality score for a project."""
    project_id: str
    overall_score: float = Field(ge=0.0, le=100.0)
    security_score: float = Field(ge=0.0, le=100.0)
    performance_score: float = Field(ge=0.0, le=100.0)
    maintainability_score: float = Field(ge=0.0, le=100.0)
    best_practices_score: float = Field(ge=0.0, le=100.0)
    component_metrics: list[ComponentMetrics] = Field(default_factory=list)
    breakdown: dict[str, float] = Field(default_factory=dict)
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VerificationReport(BaseModel):
    """Complete verification report for a project."""
    id: str = Field(default_factory=lambda: f"report-{datetime.now(UTC).timestamp()}")
    workflow_id: str
    plan_id: str
    artifacts_analyzed: int
    total_issues: int
    critical_issues: int
    high_issues: int
    medium_issues: int
    low_issues: int
    info_issues: int
    issues: list[VerificationIssue] = Field(default_factory=list)
    quality_score: QualityScore
    approved_for_deployment: bool
    approval_notes: str = ""
    rejection_reason: str = ""
    recovery_recommendations: list[str] = Field(default_factory=list)
    verification_duration_seconds: float
    verified_by_agent: str = "VerifierAgent"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_approved(self) -> bool:
        """Check if approved for deployment."""
        return self.approved_for_deployment

    @property
    def has_critical_issues(self) -> bool:
        """Check if any critical issues exist."""
        return self.critical_issues > 0

    @property
    def approval_percentage(self) -> float:
        """Get approval confidence as percentage."""
        if self.quality_score.overall_score >= 85:
            return 100.0
        elif self.quality_score.overall_score >= 70:
            return 75.0
        elif self.quality_score.overall_score >= 60:
            return 50.0
        else:
            return 0.0
