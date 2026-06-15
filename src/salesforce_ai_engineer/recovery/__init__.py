"""Recovery Agent - autonomously recovers from system failures."""

from salesforce_ai_engineer.recovery.agent import RecoveryAgent, RecoveryError
from salesforce_ai_engineer.recovery.models import (
    FailureReport,
    FailureCategory,
    FailureSeverity,
    RecoveryPlan,
    RecoveryResult,
    RecoveryStatus,
    RecoveryStrategy,
    FailureSignature,
)
from salesforce_ai_engineer.recovery.analyzer import FailureAnalyzer
from salesforce_ai_engineer.recovery.executor import RecoveryExecutor
from salesforce_ai_engineer.recovery.strategies import StrategyFactory

__all__ = [
    "RecoveryAgent",
    "RecoveryError",
    "FailureReport",
    "FailureCategory",
    "FailureSeverity",
    "RecoveryPlan",
    "RecoveryResult",
    "RecoveryStatus",
    "RecoveryStrategy",
    "FailureSignature",
    "FailureAnalyzer",
    "RecoveryExecutor",
    "StrategyFactory",
]
