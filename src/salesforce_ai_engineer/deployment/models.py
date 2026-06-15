"""Domain models for Deployment Agent."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

UTC = ZoneInfo("UTC")


class DeploymentEnvironment(str, Enum):
    """Deployment environment types."""

    DEV = "dev"
    SCRATCH_ORG = "scratch_org"
    SANDBOX = "sandbox"
    STAGING = "staging"
    PRODUCTION = "production"


class DeploymentStrategy(str, Enum):
    """Deployment strategies."""

    VALIDATE_ONLY = "validate_only"
    QUICK_DEPLOY = "quick_deploy"
    FULL_DEPLOY = "full_deploy"


class DeploymentStatus(str, Enum):
    """Deployment status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ConnectionType(str, Enum):
    """Salesforce connection types."""

    JWT = "jwt"
    OAUTH2 = "oauth2"
    SFDX = "sfdx"
    USERNAME_PASSWORD = "username_password"


class TestResult(BaseModel):
    """Individual test result."""

    test_class: str
    test_method: str
    status: str  # pass, fail, skip
    duration_ms: float
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None


class TestSummary(BaseModel):
    """Test execution summary."""

    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    total_duration_ms: float
    code_coverage_percentage: float
    test_results: list[TestResult] = Field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate test success rate."""
        if self.total_tests == 0:
            return 100.0
        return (self.passed_tests / self.total_tests) * 100


class DeploymentComponent(BaseModel):
    """Individual deployed component."""

    name: str
    type: str  # ApexClass, Trigger, CustomObject, etc.
    path: str
    status: str  # success, failed, skipped
    error_message: Optional[str] = None
    details: Optional[dict] = None


class DeploymentMetrics(BaseModel):
    """Deployment metrics and statistics."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deployment_id: str
    total_components: int
    deployed_components: int
    failed_components: int
    skipped_components: int
    test_summary: Optional[TestSummary] = None
    execution_time_seconds: float
    validation_time_seconds: Optional[float] = None
    deployment_time_seconds: Optional[float] = None
    rollback_time_seconds: Optional[float] = None
    average_component_size_bytes: float
    total_size_bytes: int


class DeploymentConnection(BaseModel):
    """Salesforce connection configuration."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    connection_type: ConnectionType
    org_id: str
    org_name: str
    environment: DeploymentEnvironment
    instance_url: str
    api_version: str = "60.0"
    is_production: bool = False
    sandbox_name: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_validated_at: Optional[datetime] = None


class DeploymentStep(BaseModel):
    """Individual deployment step."""

    step_number: int
    description: str
    step_type: str  # validate, deploy, test, rollback
    parameters: dict = Field(default_factory=dict)
    timeout_seconds: int = 600
    retry_count: int = 0
    max_retries: int = 2
    is_required: bool = True


class RollbackPlan(BaseModel):
    """Plan for rolling back a deployment."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deployment_id: str
    target_version_id: Optional[str] = None
    rollback_strategy: str  # full, partial, component_selective
    affected_components: list[str] = Field(default_factory=list)
    estimated_rollback_time_seconds: float
    is_executable: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeploymentRequest(BaseModel):
    """Request to deploy artifacts."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    connection: DeploymentConnection
    environment: DeploymentEnvironment
    strategy: DeploymentStrategy
    artifacts: dict  # artifact_id -> artifact_content
    test_level: str = "RunLocalTests"  # NoTestRun, RunLocalTests, RunSpecifiedTests, RunAllTests
    specific_tests: list[str] = Field(default_factory=list)
    allow_missing_files: bool = False
    rollback_on_error: bool = True
    max_wait_time_minutes: int = 60
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeploymentReport(BaseModel):
    """Comprehensive deployment report."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deployment_id: str
    workflow_id: str
    request_id: str
    environment: DeploymentEnvironment
    strategy: DeploymentStrategy
    status: DeploymentStatus
    components: list[DeploymentComponent] = Field(default_factory=list)
    metrics: Optional[DeploymentMetrics] = None
    test_summary: Optional[TestSummary] = None
    rollback_plan: Optional[RollbackPlan] = None
    failure_reason: Optional[str] = None
    error_details: Optional[dict] = None
    recovery_recommendations: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: Optional[datetime] = None
    deployment_duration_seconds: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_success(self) -> bool:
        """Check if deployment succeeded."""
        return self.status in [
            DeploymentStatus.SUCCEEDED,
            DeploymentStatus.PARTIALLY_SUCCEEDED,
        ]

    @property
    def requires_rollback(self) -> bool:
        """Check if rollback is needed."""
        return self.status == DeploymentStatus.FAILED and self.rollback_plan and self.rollback_plan.is_executable


class DeploymentHistory(BaseModel):
    """Historical record of deployment."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    deployment_id: str
    environment: DeploymentEnvironment
    status: DeploymentStatus
    version_id: str
    components_count: int
    deployment_time_seconds: float
    test_success_rate: float
    code_coverage_percentage: float
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: Optional[str] = None
