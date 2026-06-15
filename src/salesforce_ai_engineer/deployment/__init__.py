"""Deployment Agent - safe deployment and validation of Salesforce projects."""

from salesforce_ai_engineer.deployment.agent import (
    DeploymentAgent,
    DeploymentAgentError,
)
from salesforce_ai_engineer.deployment.models import (
    DeploymentEnvironment,
    DeploymentStrategy,
    DeploymentStatus,
    ConnectionType,
    DeploymentRequest,
    DeploymentReport,
    DeploymentConnection,
    DeploymentComponent,
    DeploymentMetrics,
    TestSummary,
    RollbackPlan,
    DeploymentHistory,
)
from salesforce_ai_engineer.deployment.auth import (
    ConnectionManager,
    SalesforceAuth,
    SalesforceAuthError,
)
from salesforce_ai_engineer.deployment.executor import (
    DeploymentExecutor,
    DeploymentError,
)
from salesforce_ai_engineer.deployment.rollback import RollbackManager
from salesforce_ai_engineer.deployment.monitor import DeploymentMonitor

__all__ = [
    "DeploymentAgent",
    "DeploymentAgentError",
    "DeploymentEnvironment",
    "DeploymentStrategy",
    "DeploymentStatus",
    "ConnectionType",
    "DeploymentRequest",
    "DeploymentReport",
    "DeploymentConnection",
    "DeploymentComponent",
    "DeploymentMetrics",
    "TestSummary",
    "RollbackPlan",
    "DeploymentHistory",
    "ConnectionManager",
    "SalesforceAuth",
    "SalesforceAuthError",
    "DeploymentExecutor",
    "DeploymentError",
    "RollbackManager",
    "DeploymentMonitor",
]
