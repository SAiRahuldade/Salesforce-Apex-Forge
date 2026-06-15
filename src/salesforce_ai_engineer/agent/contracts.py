"""Agent contracts used by the orchestrator."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from salesforce_ai_engineer.agent.models import (
    ExecutionPlan,
    ExecutionTask,
    RecoveryDecision,
    TaskResult,
)


@runtime_checkable
class PlannerAgent(Protocol):
    async def create_plan(self, request: str) -> ExecutionPlan:
        """Create a structured execution plan from natural language."""


@runtime_checkable
class TaskAgent(Protocol):
    async def execute(self, task: ExecutionTask) -> TaskResult:
        """Execute a single plan task."""


@runtime_checkable
class RecoveryAgent(Protocol):
    async def recover(self, task: ExecutionTask, error: Exception | str) -> RecoveryDecision:
        """Decide whether and how a failed task should be retried."""

