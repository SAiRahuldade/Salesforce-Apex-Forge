"""Scheduling strategies for workflow execution."""

from __future__ import annotations

from typing import Protocol

from salesforce_ai_engineer.agent.models import ExecutionPlan, ExecutionTask, TaskStatus


class SchedulingStrategy(Protocol):
    """Select runnable tasks from a workflow plan."""

    def ready_tasks(self, plan: ExecutionPlan, running_task_ids: set[str]) -> list[ExecutionTask]:
        """Return tasks whose dependencies have succeeded and are not running."""


class TopologicalSchedulingStrategy:
    """DAG scheduler that respects dependencies and preserves plan order."""

    def ready_tasks(self, plan: ExecutionPlan, running_task_ids: set[str]) -> list[ExecutionTask]:
        task_by_id = plan.task_map()
        ready: list[ExecutionTask] = []
        for task in plan.tasks:
            if task.id in running_task_ids:
                continue
            if task.status not in (TaskStatus.PENDING, TaskStatus.RETRYING):
                continue
            dependencies_succeeded = all(
                task_by_id[dependency].status == TaskStatus.SUCCESS
                for dependency in task.dependencies
            )
            if dependencies_succeeded:
                ready.append(task)
        return ready
