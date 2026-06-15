"""Compatibility exports for shared agent domain models.

Canonical model definitions live in :mod:`salesforce_ai_engineer.models.domain`.
This module keeps existing agent imports stable while ensuring every component
uses the same strongly typed domain objects.
"""

from salesforce_ai_engineer.models.domain import (
    AgentRequest,
    AgentResponse,
    DeploymentReport,
    DeploymentStatus,
    ErrorReport,
    ExecutionPlan,
    ExecutionReport,
    ExecutionTask,
    MemoryRecord,
    RecoveryAction,
    RecoveryDecision,
    RecoveryReport,
    RewardRecord,
    SalesforceWorkType,
    Severity,
    TaskResult,
    TaskStatus,
    ToolRequest,
    ToolResponse,
    ToolErrorType,
    ToolStatus,
    VerificationReport,
    VerificationStatus,
    WorkflowCheckpoint,
    WorkflowState,
    WorkflowStatus,
)

__all__ = [
    "AgentRequest",
    "AgentResponse",
    "DeploymentReport",
    "DeploymentStatus",
    "ErrorReport",
    "ExecutionPlan",
    "ExecutionReport",
    "ExecutionTask",
    "MemoryRecord",
    "RecoveryAction",
    "RecoveryDecision",
    "RecoveryReport",
    "RewardRecord",
    "SalesforceWorkType",
    "Severity",
    "TaskResult",
    "TaskStatus",
    "ToolRequest",
    "ToolResponse",
    "ToolErrorType",
    "ToolStatus",
    "VerificationReport",
    "VerificationStatus",
    "WorkflowCheckpoint",
    "WorkflowState",
    "WorkflowStatus",
]
