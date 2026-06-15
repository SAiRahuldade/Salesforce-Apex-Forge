"""Domain models for Reward & Learning Engine."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field

UTC = ZoneInfo("UTC")


class MetricType(str, Enum):
    """Types of metrics for evaluation."""

    PLANNING_QUALITY = "planning_quality"
    CODE_QUALITY = "code_quality"
    VERIFICATION_SCORE = "verification_score"
    DEPLOYMENT_SUCCESS = "deployment_success"
    RECOVERY_EFFECTIVENESS = "recovery_effectiveness"
    EXECUTION_TIME = "execution_time"
    RETRY_COUNT = "retry_count"
    TEST_COVERAGE = "test_coverage"
    RESOURCE_USAGE = "resource_usage"
    WORKFLOW_SUCCESS = "workflow_success"


class StrategyType(str, Enum):
    """Types of execution strategies."""

    STANDARD = "standard"
    OPTIMIZED = "optimized"
    CONSERVATIVE = "conservative"
    AGGRESSIVE = "aggressive"
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"
    HYBRID = "hybrid"
    RETRY = "retry"
    FALLBACK = "fallback"
    REGENERATE = "regenerate"
    ROLLBACK = "rollback"


class RewardStatus(str, Enum):
    """Status of reward record."""

    PENDING = "pending"
    CALCULATED = "calculated"
    VALIDATED = "validated"
    ARCHIVED = "archived"


class AgentPerformanceMetric(BaseModel):
    """Performance metrics for an individual agent."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str
    metric_type: MetricType
    value: float
    confidence: float = Field(ge=0.0, le=1.0)
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period_start: datetime
    period_end: datetime
    context: Dict[str, Any] = Field(default_factory=dict)


class WorkflowMetrics(BaseModel):
    """Aggregated metrics for a complete workflow."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    planning_quality_score: float = Field(ge=0.0, le=100.0)
    code_quality_score: float = Field(ge=0.0, le=100.0)
    verification_score: float = Field(ge=0.0, le=100.0)
    deployment_success_rate: float = Field(ge=0.0, le=1.0)
    recovery_effectiveness: float = Field(ge=0.0, le=1.0)
    execution_time_seconds: float
    total_retries: int = 0
    test_coverage_percentage: float = Field(ge=0.0, le=100.0)
    resource_usage_percent: float = Field(ge=0.0, le=100.0)
    is_workflow_successful: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RewardScore(BaseModel):
    """Reward score for agent or workflow."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: str  # "agent" or "workflow"
    entity_id: str  # agent_name or workflow_id
    score: float = Field(ge=0.0, le=100.0)
    max_possible_score: float = 100.0
    confidence: float = Field(ge=0.0, le=1.0)
    status: RewardStatus = RewardStatus.CALCULATED
    factors: Dict[str, float] = Field(default_factory=dict)
    weights: Dict[str, float] = Field(default_factory=dict)
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period: str  # "daily", "weekly", "monthly", "all_time"


class StrategyPerformance(BaseModel):
    """Performance metrics for a specific strategy."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strategy_type: StrategyType
    agent_name: str
    total_uses: int = 0
    successful_uses: int = 0
    average_execution_time_seconds: float
    average_retry_count: float
    average_quality_score: float
    success_rate: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    last_used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def effectiveness_score(self) -> float:
        """Calculate effectiveness score."""
        return (self.success_rate * 0.6) + (1.0 - (self.average_execution_time_seconds / 3600) * 0.4)


class FailurePattern(BaseModel):
    """Detected recurring failure pattern."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pattern_name: str
    pattern_description: str
    agent_affected: str
    failure_category: str
    occurrence_count: int = 0
    success_count_with_recovery: int = 0
    average_recovery_time_seconds: float
    affected_workflows: List[str] = Field(default_factory=list)
    recommended_strategy: StrategyType
    confidence: float = Field(ge=0.0, le=1.0)
    first_detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    pattern_severity: str = "medium"  # low, medium, high, critical


class StrategyRecommendation(BaseModel):
    """Recommended strategy for future execution."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str
    current_strategy: StrategyType
    recommended_strategy: StrategyType
    improvement_potential: float = Field(ge=0.0, le=100.0)
    justification: str
    historical_success_rate: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_time_savings_seconds: float = 0.0
    estimated_quality_improvement_percent: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: Optional[datetime] = None


class PerformanceTrend(BaseModel):
    """Performance trend over time."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: str  # "agent" or "workflow"
    entity_id: str
    metric_type: MetricType
    time_period: str  # "daily", "weekly", "monthly"
    trend_direction: str  # "improving", "declining", "stable"
    trend_strength: float = Field(ge=0.0, le=1.0)
    values_over_time: List[float] = Field(default_factory=list)
    timestamps: List[datetime] = Field(default_factory=list)
    average_value: float
    min_value: float
    max_value: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentLeaderboardEntry(BaseModel):
    """Leaderboard entry for agent performance."""

    rank: int
    agent_name: str
    overall_score: float = Field(ge=0.0, le=100.0)
    workflows_completed: int
    average_execution_time_seconds: float
    success_rate: float = Field(ge=0.0, le=1.0)
    quality_score: float = Field(ge=0.0, le=100.0)
    recovery_effectiveness: float = Field(ge=0.0, le=1.0)
    trend_indicator: str  # "up", "down", "stable"
    period: str


class ExecutionAnalytics(BaseModel):
    """Comprehensive execution analytics."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    total_execution_time_seconds: float
    planning_time_seconds: float
    execution_time_seconds: float
    verification_time_seconds: float
    deployment_time_seconds: float
    total_retries: int
    total_failures: int
    recovery_attempts: int
    successful_recoveries: int
    human_interventions: int
    automated_decisions: int
    decision_quality_average: float
    resource_efficiency_score: float
    learning_opportunities: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StrategyComparison(BaseModel):
    """Comparison of candidate execution strategies."""

    agent_name: str
    baseline_strategy: StrategyType
    candidate_strategy: StrategyType
    baseline_score: float = Field(ge=0.0, le=100.0)
    candidate_score: float = Field(ge=0.0, le=100.0)
    score_delta: float
    confidence_delta: float
    recommendation: str


class PerformanceDashboard(BaseModel):
    """Snapshot of reward and learning health for dashboards."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period: str
    total_workflows: int
    average_workflow_score: float = Field(ge=0.0, le=100.0)
    workflow_success_rate: float = Field(ge=0.0, le=1.0)
    leaderboard: List[AgentLeaderboardEntry] = Field(default_factory=list)
    top_strategies: List[StrategyPerformance] = Field(default_factory=list)
    recurring_failures: List[FailurePattern] = Field(default_factory=list)
    recommendations: List[StrategyRecommendation] = Field(default_factory=list)
    trends: List[PerformanceTrend] = Field(default_factory=list)


class LearningEvaluationResult(BaseModel):
    """Traceable result of one completed workflow learning pass."""

    workflow_id: str
    workflow_metrics: WorkflowMetrics
    workflow_score: RewardScore
    agent_scores: List[RewardScore] = Field(default_factory=list)
    agent_metrics: Dict[str, List[AgentPerformanceMetric]] = Field(default_factory=dict)
    analytics: ExecutionAnalytics
    strategy_performance: List[StrategyPerformance] = Field(default_factory=list)
    failure_patterns: List[FailurePattern] = Field(default_factory=list)
    recommendations: List[StrategyRecommendation] = Field(default_factory=list)
    trends: List[PerformanceTrend] = Field(default_factory=list)
    trace: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
