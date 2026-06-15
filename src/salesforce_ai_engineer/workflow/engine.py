"""Production workflow execution engine for autonomous multi-agent workflows."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from salesforce_ai_engineer.agent.contracts import RecoveryAgent
from salesforce_ai_engineer.agent.models import (
    ExecutionPlan,
    ExecutionReport,
    ExecutionTask,
    RecoveryAction,
    TaskResult,
    TaskStatus,
    WorkflowStatus,
)
from salesforce_ai_engineer.agent.registry import AgentNotRegisteredError, AgentRegistry
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.core.state import StateManager
from salesforce_ai_engineer.memory.manager import MemoryManager
from salesforce_ai_engineer.models.domain import EventPriority, LifecycleEvent
from salesforce_ai_engineer.workflow.models import (
    RetryAttempt,
    StateTransition,
    TaskExecutionTrace,
    WorkflowExecutionPolicy,
    WorkflowExecutionResult,
    WorkflowProgress,
    WorkflowRunStatus,
    WorkflowSnapshot,
)
from salesforce_ai_engineer.workflow.persistence import WorkflowPersistence
from salesforce_ai_engineer.workflow.scheduler import SchedulingStrategy, TopologicalSchedulingStrategy
from salesforce_ai_engineer.workflow.dag import DAG

logger = logging.getLogger(__name__)


class WorkflowEngineError(RuntimeError):
    """Raised when workflow execution cannot continue."""


class WorkflowNotFoundError(WorkflowEngineError):
    """Raised when a workflow cannot be restored."""


class WorkflowExecutionEngine:
    """Runtime for executing, monitoring, controlling, and persisting workflows."""

    STATE_NAMESPACE = "workflow_engine_snapshots"

    def __init__(
        self,
        agent_registry: AgentRegistry,
        recovery_agent: RecoveryAgent,
        event_bus: EventBus,
        *,
        memory_manager: MemoryManager | None = None,
        state_manager: StateManager | None = None,
        scheduler: SchedulingStrategy | None = None,
        default_policy: WorkflowExecutionPolicy | None = None,
    ) -> None:
        self.agent_registry = agent_registry
        self.recovery_agent = recovery_agent
        self.event_bus = event_bus
        self.state_manager = state_manager
        self.scheduler = scheduler or TopologicalSchedulingStrategy()
        self.default_policy = default_policy or WorkflowExecutionPolicy()
        self.persistence = WorkflowPersistence(memory_manager)
        self._pause_requests: set[str] = set()
        self._cancel_requests: set[str] = set()
        self._resume_events: dict[str, asyncio.Event] = {}
        self._dag_map: dict[str, DAG] = {}
        self._active_snapshots: dict[str, WorkflowSnapshot] = {}
        self.logger = logger

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        request: str,
        workflow_id: str | None = None,
        *,
        policy: WorkflowExecutionPolicy | None = None,
        resume_from: WorkflowSnapshot | None = None,
    ) -> WorkflowExecutionResult:
        """Execute an execution plan to a terminal workflow result."""

        selected_policy = policy or self.default_policy
        snapshot = resume_from or WorkflowSnapshot(
            workflow_id=workflow_id or str(uuid4()),
            request=request,
            plan=plan,
            status=WorkflowRunStatus.INITIALIZED,
            metadata={"policy": selected_policy.model_dump(mode="json")},
        )
        snapshot.status = WorkflowRunStatus.RUNNING
        snapshot.updated_at = datetime.now(UTC)
        self._active_snapshots[snapshot.workflow_id] = snapshot
        # Initialize DAG for this workflow execution
        self._dag_map[snapshot.workflow_id] = DAG.from_plan(snapshot.plan)
        # Mark already completed and skipped tasks as completed in the DAG to avoid re-running them on resume
        for completed_id in snapshot.completed_task_ids + snapshot.skipped_task_ids:
            self._dag_map[snapshot.workflow_id].mark_completed(completed_id)
        await self._checkpoint(snapshot, "workflow initialized")
        await self._publish(
            LifecycleEvent.WORKFLOW_STARTED,
            {"workflow_id": snapshot.workflow_id, "plan_id": snapshot.plan.id},
            snapshot.workflow_id,
        )

        try:
            await self._run_until_terminal(snapshot, selected_policy)
        finally:
            self._active_snapshots.pop(snapshot.workflow_id, None)

        result = self._build_result(snapshot)
        await self._publish(
            self._terminal_event(result.status),
            {
                "workflow_id": snapshot.workflow_id,
                "status": result.status.value,
                "successful_tasks": result.successful_tasks,
                "failed_tasks": result.failed_tasks,
                "skipped_tasks": result.skipped_tasks,
                "metrics": result.metrics,
            },
            snapshot.workflow_id,
            priority=EventPriority.HIGH,
        )
        return result

    async def resume(self, workflow_id: str) -> WorkflowExecutionResult:
        """Resume a persisted workflow from its latest checkpoint."""

        snapshot = await self.load_snapshot(workflow_id)
        if snapshot is None:
            raise WorkflowNotFoundError(f"No persisted workflow exists for {workflow_id!r}")
        if snapshot.status in {
            WorkflowRunStatus.SUCCESS,
            WorkflowRunStatus.FAILED,
            WorkflowRunStatus.ESCALATED,
            WorkflowRunStatus.CANCELLED,
        }:
            return self._build_result(snapshot)
        self._pause_requests.discard(workflow_id)
        self._cancel_requests.discard(workflow_id)
        self._resume_events.setdefault(workflow_id, asyncio.Event()).set()
        policy = WorkflowExecutionPolicy.model_validate(
            snapshot.metadata.get("policy", self.default_policy.model_dump(mode="json"))
        )
        await self._publish(
            LifecycleEvent.WORKFLOW_RESUMED,
            {"workflow_id": workflow_id, "version": snapshot.version},
            workflow_id,
        )
        return await self.execute_plan(
            snapshot.plan,
            snapshot.request,
            workflow_id,
            policy=policy,
            resume_from=snapshot,
        )

    async def pause(self, workflow_id: str) -> WorkflowProgress:
        """Request pause at the next scheduling boundary."""

        self._pause_requests.add(workflow_id)
        snapshot = await self.load_snapshot(workflow_id)
        if snapshot is None:
            raise WorkflowNotFoundError(f"No workflow exists for {workflow_id!r}")
        await self._publish("workflow.pause_requested", {"workflow_id": workflow_id}, workflow_id)
        return self._progress(snapshot)

    async def cancel(self, workflow_id: str) -> WorkflowProgress:
        """Request cancellation at the next scheduling boundary."""

        self._cancel_requests.add(workflow_id)
        self._resume_events.setdefault(workflow_id, asyncio.Event()).set()
        snapshot = await self.load_snapshot(workflow_id)
        if snapshot is None:
            raise WorkflowNotFoundError(f"No workflow exists for {workflow_id!r}")
        snapshot.status = WorkflowRunStatus.CANCEL_REQUESTED
        await self._checkpoint(snapshot, "cancel requested")
        await self._publish("workflow.cancel_requested", {"workflow_id": workflow_id}, workflow_id)
        return self._progress(snapshot)

    async def restart(self, workflow_id: str) -> WorkflowExecutionResult:
        """Restart a persisted workflow from the beginning with a new version."""

        snapshot = await self.load_snapshot(workflow_id)
        if snapshot is None:
            raise WorkflowNotFoundError(f"No workflow exists for {workflow_id!r}")
        for task in snapshot.plan.tasks:
            task.status = TaskStatus.PENDING
            task.attempts = 0
            task.output = None
            task.error = None
            task.started_at = None
            task.completed_at = None
        snapshot.version += 1
        snapshot.completed_task_ids = []
        snapshot.failed_task_ids = []
        snapshot.skipped_task_ids = []
        snapshot.cancelled_task_ids = []
        snapshot.current_task_ids = []
        snapshot.traces = {}
        await self._checkpoint(snapshot, "workflow restarted")
        await self._publish("workflow.restarted", {"workflow_id": workflow_id}, workflow_id)
        return await self.execute_plan(snapshot.plan, snapshot.request, workflow_id, resume_from=snapshot)

    async def resume_paused(self, workflow_id: str) -> WorkflowProgress:
        """Release a paused workflow that is executing in another task."""

        self._pause_requests.discard(workflow_id)
        self._resume_events.setdefault(workflow_id, asyncio.Event()).set()
        snapshot = await self.load_snapshot(workflow_id)
        if snapshot is None:
            raise WorkflowNotFoundError(f"No workflow exists for {workflow_id!r}")
        await self._publish("workflow.resume_requested", {"workflow_id": workflow_id}, workflow_id)
        return self._progress(snapshot)

    async def status(self, workflow_id: str) -> WorkflowProgress:
        """Return current persisted workflow progress."""

        snapshot = await self.load_snapshot(workflow_id)
        if snapshot is None:
            raise WorkflowNotFoundError(f"No workflow exists for {workflow_id!r}")
        return self._progress(snapshot)

    async def load_snapshot(self, workflow_id: str) -> WorkflowSnapshot | None:
        """Load a snapshot from active memory, Memory Agent, or local state fallback."""

        active = self._active_snapshots.get(workflow_id)
        if active is not None:
            return active.model_copy(deep=True)
        snapshot = await self.persistence.load_snapshot(workflow_id)
        if snapshot is not None:
            return snapshot
        if self.state_manager is None:
            return None
        snapshots = self.state_manager.get(self.STATE_NAMESPACE, {})
        payload = snapshots.get(workflow_id) if isinstance(snapshots, dict) else None
        return WorkflowSnapshot.model_validate(payload) if payload else None

    async def archive(self, workflow_id: str) -> None:
        """Archive a completed workflow snapshot."""

        snapshot = await self.load_snapshot(workflow_id)
        if snapshot is None:
            raise WorkflowNotFoundError(f"No workflow exists for {workflow_id!r}")
        snapshot.status = WorkflowRunStatus.ARCHIVED
        await self._checkpoint(snapshot, "workflow archived")
        await self.persistence.archive_snapshot(workflow_id)
        await self._publish("workflow.archived", {"workflow_id": workflow_id}, workflow_id)

    async def _run_until_terminal(
        self,
        snapshot: WorkflowSnapshot,
        policy: WorkflowExecutionPolicy,
    ) -> None:
        while True:
            await self._handle_controls(snapshot)
            if snapshot.status in {WorkflowRunStatus.CANCELLED, WorkflowRunStatus.PAUSED}:
                return

            self._apply_conditional_branches(snapshot)
            # After applying conditional branches, ensure any tasks that were skipped are marked as completed in the DAG
            dag = self._dag_map.get(snapshot.workflow_id)
            if dag:
                for task in snapshot.plan.tasks:
                    if task.id in snapshot.skipped_task_ids:
                        dag.mark_completed(task.id)
                if self._all_terminal(snapshot):
                    snapshot.status = self._final_run_status(snapshot)
                    snapshot.completed_at = datetime.now(UTC)
                    await self._checkpoint(snapshot, "workflow terminal")
                    return

                # Use DAG to compute ready tasks based on completed tasks and current running tasks
                ready_ids = dag.ready_tasks(snapshot.current_task_ids)
                task_by_id = snapshot.plan.task_map()
                ready = [task_by_id[tid] for tid in ready_ids if tid in task_by_id]
                if not ready:
                    snapshot.status = WorkflowRunStatus.ESCALATED
                    snapshot.completed_at = datetime.now(UTC)
                    await self._checkpoint(snapshot, "no runnable tasks remain")
                    return

                snapshot.status = WorkflowRunStatus.SCHEDULED
                await self._checkpoint(snapshot, "tasks scheduled")
                batch = ready[: max(1, policy.max_parallel_tasks)]
                snapshot.status = WorkflowRunStatus.RUNNING
                snapshot.current_task_ids = [task.id for task in batch]
                await self._publish_progress(snapshot)
                results = await asyncio.gather(
                    *(self._execute_task(snapshot, task, policy) for task in batch),
                    return_exceptions=True,
                )
                snapshot.current_task_ids = []
                for result in results:
                    if isinstance(result, Exception):
                        self.logger.exception("Task execution escaped workflow engine", exc_info=result)
                self._refresh_metrics(snapshot)
                await self._checkpoint(snapshot, "task batch completed")

                if snapshot.failed_task_ids and policy.fail_fast:
                    if policy.rollback_on_failure:
                        await self._rollback(snapshot, policy)
                    snapshot.status = self._final_run_status(snapshot)
                    snapshot.completed_at = datetime.now(UTC)
                    await self._checkpoint(snapshot, "failure propagated")
                    return

    async def _execute_task(
        self,
        snapshot: WorkflowSnapshot,
        task: ExecutionTask,
        policy: WorkflowExecutionPolicy,
    ) -> None:
        self._inject_upstream_artifacts(snapshot, task)
        trace = snapshot.traces.setdefault(
            task.id,
            TaskExecutionTrace(
                task_id=task.id,
                agent=task.agent,
                dependencies=list(task.dependencies),
                execution_context={"workflow_id": snapshot.workflow_id, "task_input": task.input},
            ),
        )
        effective_attempts = max(task.max_attempts, policy.retry_policy.max_attempts)
        while task.attempts < effective_attempts and task.status != TaskStatus.SUCCESS:
            await self._handle_controls(snapshot)
            if snapshot.status == WorkflowRunStatus.CANCELLED:
                self._transition(task, trace, TaskStatus.FAILED, "workflow cancelled")
                snapshot.cancelled_task_ids.append(task.id)
                return

            started_at = datetime.now(UTC)
            task.started_at = task.started_at or started_at
            task.attempts += 1
            task.error = None
            self._transition(task, trace, TaskStatus.RUNNING, f"attempt {task.attempts} started")
            attempt = RetryAttempt(attempt=task.attempts, started_at=started_at)
            trace.retry_history.append(attempt)
            await self._publish(
                LifecycleEvent.TASK_EXECUTION_STARTED,
                {"workflow_id": snapshot.workflow_id, "task_id": task.id, "agent": task.agent, "attempt": task.attempts},
                snapshot.workflow_id,
                task_id=task.id,
            )

            try:
                result = await self._invoke_agent(task, policy)
                self._apply_task_result(task, result)
                completed_at = datetime.now(UTC)
                self._finish_attempt(attempt, completed_at, True)
                trace.output = task.output
                trace.completed_at = completed_at
                trace.duration_seconds = self._duration(trace.started_at or task.started_at, completed_at)
                self._transition(task, trace, TaskStatus.SUCCESS, "task completed")
                self._mark(snapshot.completed_task_ids, task.id)
                # Record task completion in DAG
                self._dag_map[snapshot.workflow_id].mark_completed(task.id)
                await self.persistence.save_task_history(snapshot.workflow_id, snapshot.request, trace, True)
                await self._checkpoint(snapshot, f"task {task.id} completed")
                await self._publish(
                    LifecycleEvent.TASK_COMPLETED,
                    {"workflow_id": snapshot.workflow_id, "task_id": task.id, "attempts": task.attempts},
                    snapshot.workflow_id,
                    task_id=task.id,
                )
                self._apply_dynamic_tasks(snapshot, task)
                return
            except Exception as exc:
                completed_at = datetime.now(UTC)
                self._finish_attempt(attempt, completed_at, False, str(exc))
                await self._handle_task_failure(snapshot, task, trace, attempt, exc, policy)

        if task.status != TaskStatus.SUCCESS:
            self._transition(task, trace, TaskStatus.FAILED, "retry policy exhausted")
            task.completed_at = datetime.now(UTC)
            trace.completed_at = task.completed_at
            trace.error = task.error or "Retry policy exhausted"
            trace.duration_seconds = self._duration(trace.started_at or task.started_at, trace.completed_at)
            self._mark(snapshot.failed_task_ids, task.id)
            await self.persistence.save_task_history(snapshot.workflow_id, snapshot.request, trace, False)
            await self._checkpoint(snapshot, f"task {task.id} failed")

    def _collect_workflow_artifacts(self, snapshot: WorkflowSnapshot) -> dict[str, Any]:
        """Merge artifacts produced by completed upstream tasks."""

        merged: dict[str, Any] = {}
        for completed_id in snapshot.completed_task_ids:
            completed_task = snapshot.plan.task_map().get(completed_id)
            if completed_task is None or not completed_task.output:
                continue
            task_artifacts = completed_task.output.get("artifacts", {})
            if isinstance(task_artifacts, dict):
                merged.update(task_artifacts)
        return merged

    def _inject_upstream_artifacts(self, snapshot: WorkflowSnapshot, task: ExecutionTask) -> None:
        """Pass generated artifacts from dependencies into the current task input."""

        upstream = self._collect_workflow_artifacts(snapshot)
        if not upstream:
            task.input.setdefault("workflow_id", snapshot.workflow_id)
            return

        existing = task.input.get("artifacts", {})
        if not isinstance(existing, dict):
            existing = {}
        task.input["artifacts"] = {**upstream, **existing}
        task.input["workflow_id"] = snapshot.workflow_id

    async def _invoke_agent(
        self,
        task: ExecutionTask,
        policy: WorkflowExecutionPolicy,
    ) -> TaskResult:
        task.input.setdefault("workflow_id", task.input.get("workflow_id"))
        agent = self.agent_registry.resolve(task.agent)
        if policy.task_timeout_seconds is None:
            return await agent.execute(task)
        return await asyncio.wait_for(agent.execute(task), timeout=policy.task_timeout_seconds)

    async def _handle_task_failure(
        self,
        snapshot: WorkflowSnapshot,
        task: ExecutionTask,
        trace: TaskExecutionTrace,
        attempt: RetryAttempt,
        error: Exception,
        policy: WorkflowExecutionPolicy,
    ) -> None:
        task.error = str(error)
        trace.error = str(error)
        await self._publish(
            LifecycleEvent.TASK_FAILED,
            {"workflow_id": snapshot.workflow_id, "task_id": task.id, "agent": task.agent, "attempt": task.attempts, "error": str(error)},
            snapshot.workflow_id,
            task_id=task.id,
            priority=EventPriority.HIGH,
        )

        if isinstance(error, AgentNotRegisteredError):
            self._transition(task, trace, TaskStatus.FAILED, str(error))
            self._mark(snapshot.failed_task_ids, task.id)
            return

        try:
            decision = await self.recovery_agent.recover(task, error)
            attempt.recovery_action = decision.action.value
            await self._publish(
                LifecycleEvent.RECOVERY_COMPLETED,
                {"workflow_id": snapshot.workflow_id, "task_id": task.id, "action": decision.action.value, "reason": decision.reason},
                snapshot.workflow_id,
                task_id=task.id,
            )
        except Exception as recovery_error:
            self._transition(task, trace, TaskStatus.FAILED, f"recovery failed: {recovery_error}")
            task.completed_at = datetime.now(UTC)
            self._mark(snapshot.failed_task_ids, task.id)
            await self._publish(
                LifecycleEvent.RECOVERY_FAILED,
                {"workflow_id": snapshot.workflow_id, "task_id": task.id, "error": str(recovery_error)},
                snapshot.workflow_id,
                task_id=task.id,
                priority=EventPriority.HIGH,
            )
            return

        if decision.action == RecoveryAction.RETRY and task.attempts < max(task.max_attempts, policy.retry_policy.max_attempts):
            if decision.updated_input:
                task.input.update(decision.updated_input)
            backoff = policy.retry_policy.delay_for(max(0, task.attempts - 1))
            attempt.backoff_seconds = backoff
            self._transition(task, trace, TaskStatus.RETRYING, decision.reason)
            await self._publish(
                LifecycleEvent.TASK_RETRYING,
                {"workflow_id": snapshot.workflow_id, "task_id": task.id, "next_attempt": task.attempts + 1, "backoff_seconds": backoff},
                snapshot.workflow_id,
                task_id=task.id,
            )
            await self._checkpoint(snapshot, f"task {task.id} retrying")
            if backoff > 0:
                await asyncio.sleep(backoff)
            return

        self._transition(task, trace, TaskStatus.FAILED, decision.reason)
        task.completed_at = datetime.now(UTC)
        self._mark(snapshot.failed_task_ids, task.id)

    async def _rollback(
        self,
        snapshot: WorkflowSnapshot,
        policy: WorkflowExecutionPolicy,
    ) -> None:
        snapshot.status = WorkflowRunStatus.ROLLING_BACK
        await self._checkpoint(snapshot, "rollback started")
        await self._publish("workflow.rollback.started", {"workflow_id": snapshot.workflow_id}, snapshot.workflow_id)
        task_by_id = snapshot.plan.task_map()
        for task_id in reversed(snapshot.completed_task_ids):
            task = task_by_id[task_id]
            rollback_payload = task.metadata.get("rollback_task")
            if not isinstance(rollback_payload, dict):
                continue
            rollback_task = ExecutionTask.model_validate(
                {
                    "id": rollback_payload.get("id", f"rollback-{task.id}"),
                    "title": rollback_payload.get("title", f"Rollback {task.title}"),
                    "description": rollback_payload.get("description", f"Rollback task {task.id}"),
                    "agent": rollback_payload.get("agent", task.agent),
                    "input": rollback_payload.get("input", {"rolled_back_task_id": task.id}),
                    "max_attempts": rollback_payload.get("max_attempts", policy.retry_policy.max_attempts),
                    "metadata": {"rollback_for": task.id},
                }
            )
            await self._execute_task(snapshot, rollback_task, policy)
        snapshot.status = WorkflowRunStatus.ROLLED_BACK
        await self._publish("workflow.rollback.completed", {"workflow_id": snapshot.workflow_id}, snapshot.workflow_id)

    def _apply_conditional_branches(self, snapshot: WorkflowSnapshot) -> None:
        task_by_id = snapshot.plan.task_map()
        for task in snapshot.plan.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            condition = task.metadata.get("condition")
            if not isinstance(condition, dict):
                continue
            dependency_id = condition.get("task_id") or next(iter(task.dependencies), None)
            if dependency_id is None or dependency_id not in task_by_id:
                continue
            dependency = task_by_id[dependency_id]
            if dependency.status != TaskStatus.SUCCESS:
                continue
            output = dependency.output or {}
            key = condition.get("output_key")
            actual = output.get(key) if key else output
            expected = condition.get("equals")
            not_equals = condition.get("not_equals")
            exists = condition.get("exists")
            should_run = True
            if "equals" in condition and should_run:
                should_run = (actual == expected)
            if "not_equals" in condition and should_run:
                should_run = (actual != not_equals)
            if "exists" in condition and should_run:
                should_run = ((actual is not None) == bool(exists))
            if not should_run:
                task.status = TaskStatus.SUCCESS
                task.output = {"skipped": True, "condition": condition}
                task.completed_at = datetime.now(UTC)
                self._mark(snapshot.skipped_task_ids, task.id)
                # Mark the skipped task as completed in the DAG to avoid blocking dependent tasks
                self._dag_map[snapshot.workflow_id].mark_completed(task.id)

    def _apply_dynamic_tasks(self, snapshot: WorkflowSnapshot, source_task: ExecutionTask) -> None:
        generated = (source_task.output or {}).get("generated_tasks")
        if not isinstance(generated, list):
            return
        known_ids = {task.id for task in snapshot.plan.tasks}
        for item in generated:
            if not isinstance(item, dict):
                continue
            task = ExecutionTask.model_validate(item)
            if task.id in known_ids:
                continue
            missing = [dependency for dependency in task.dependencies if dependency not in known_ids]
            if missing:
                raise WorkflowEngineError(f"Generated task {task.id!r} has unknown dependencies: {missing}")
            snapshot.plan.tasks.append(task)
            known_ids.add(task.id)
            # Add generated task to DAG for future scheduling
            self._dag_map[snapshot.workflow_id].add_generated_task(task)

    async def _handle_controls(self, snapshot: WorkflowSnapshot) -> None:
        workflow_id = snapshot.workflow_id
        if workflow_id in self._cancel_requests:
            snapshot.status = WorkflowRunStatus.CANCELLED
            for task in snapshot.plan.tasks:
                if task.status in (TaskStatus.PENDING, TaskStatus.RETRYING, TaskStatus.RUNNING):
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now(UTC)
                    self._mark(snapshot.cancelled_task_ids, task.id)
            await self._checkpoint(snapshot, "workflow cancelled")
            await self._publish("workflow.cancelled", {"workflow_id": workflow_id}, workflow_id)
            return
        if workflow_id in self._pause_requests:
            snapshot.status = WorkflowRunStatus.PAUSED
            await self._checkpoint(snapshot, "workflow paused")
            await self._publish("workflow.paused", {"workflow_id": workflow_id}, workflow_id)
            event = self._resume_events.setdefault(workflow_id, asyncio.Event())
            event.clear()
            await event.wait()
            if workflow_id not in self._cancel_requests:
                snapshot.status = WorkflowRunStatus.RUNNING
                await self._checkpoint(snapshot, "workflow resumed")

    def _apply_task_result(self, task: ExecutionTask, result: TaskResult) -> None:
        if result.task_id != task.id:
            raise WorkflowEngineError(f"Agent returned result for {result.task_id!r}, expected {task.id!r}")
        if not result.success:
            raise WorkflowEngineError(result.error or f"Task {task.id} failed without details")
        task.output = result.output
        task.error = None
        task.completed_at = datetime.now(UTC)

    def _transition(
        self,
        task: ExecutionTask,
        trace: TaskExecutionTrace,
        status: TaskStatus,
        reason: str,
    ) -> None:
        previous = task.status
        task.status = status
        if trace.started_at is None and status == TaskStatus.RUNNING:
            trace.started_at = datetime.now(UTC)
        trace.state_transitions.append(
            StateTransition(from_state=previous.value, to_state=status.value, reason=reason)
        )

    def _finish_attempt(
        self,
        attempt: RetryAttempt,
        completed_at: datetime,
        success: bool,
        error: str | None = None,
    ) -> None:
        attempt.completed_at = completed_at
        attempt.success = success
        attempt.error = error
        attempt.duration_seconds = self._duration(attempt.started_at, completed_at)

    async def _checkpoint(self, snapshot: WorkflowSnapshot, reason: str) -> None:
        snapshot.version += 1
        snapshot.updated_at = datetime.now(UTC)
        await self.persistence.save_snapshot(snapshot)
        if self.state_manager is not None:
            snapshots = self.state_manager.get(self.STATE_NAMESPACE, {})
            if not isinstance(snapshots, dict):
                snapshots = {}
            snapshots[snapshot.workflow_id] = snapshot.model_dump(mode="json")
            self.state_manager.set(self.STATE_NAMESPACE, snapshots)
        await self._publish(
            LifecycleEvent.WORKFLOW_CHECKPOINTED,
            {"workflow_id": snapshot.workflow_id, "version": snapshot.version, "reason": reason},
            snapshot.workflow_id,
        )

    async def _publish_progress(self, snapshot: WorkflowSnapshot) -> None:
        progress = self._progress(snapshot)
        await self._publish("workflow.progress", progress.model_dump(mode="json"), snapshot.workflow_id)

    async def _publish(
        self,
        event: LifecycleEvent | str,
        payload: dict[str, Any],
        workflow_id: str,
        *,
        task_id: str | None = None,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        await self.event_bus.publish(
            event,
            payload,
            workflow_id=workflow_id,
            task_id=task_id,
            priority=priority,
            source="workflow_execution_engine",
        )

    def _build_result(self, snapshot: WorkflowSnapshot) -> WorkflowExecutionResult:
        self._refresh_metrics(snapshot)
        started_at = snapshot.created_at
        completed_at = snapshot.completed_at or datetime.now(UTC)
        status = self._domain_status(snapshot.status)
        successful = len([task for task in snapshot.plan.tasks if task.status == TaskStatus.SUCCESS and task.id not in snapshot.skipped_task_ids])
        failed = len([task for task in snapshot.plan.tasks if task.status == TaskStatus.FAILED])
        return WorkflowExecutionResult(
            workflow_id=snapshot.workflow_id,
            request=snapshot.request,
            status=status,
            run_status=snapshot.status,
            plan_id=snapshot.plan.id,
            total_tasks=len(snapshot.plan.tasks),
            successful_tasks=successful,
            failed_tasks=failed,
            skipped_tasks=len(snapshot.skipped_task_ids),
            cancelled_tasks=len(snapshot.cancelled_task_ids),
            escalated=status == WorkflowStatus.ESCALATED,
            tasks=snapshot.plan.tasks,
            traces=snapshot.traces,
            metrics=snapshot.metrics,
            started_at=started_at,
            completed_at=completed_at,
            summary=self._summary(snapshot, status, successful, failed),
        )

    def _progress(self, snapshot: WorkflowSnapshot) -> WorkflowProgress:
        total = max(1, len(snapshot.plan.tasks))
        completed = len([task for task in snapshot.plan.tasks if task.status == TaskStatus.SUCCESS])
        failed = len([task for task in snapshot.plan.tasks if task.status == TaskStatus.FAILED])
        skipped = len(snapshot.skipped_task_ids)
        running = len(snapshot.current_task_ids)
        return WorkflowProgress(
            workflow_id=snapshot.workflow_id,
            status=snapshot.status,
            total_tasks=len(snapshot.plan.tasks),
            completed_tasks=completed,
            failed_tasks=failed,
            skipped_tasks=skipped,
            running_tasks=running,
            percent_complete=((completed + failed) / total) * 100.0,
        )

    def _refresh_metrics(self, snapshot: WorkflowSnapshot) -> None:
        completed_at = snapshot.completed_at or datetime.now(UTC)
        duration = self._duration(snapshot.created_at, completed_at)
        total_retries = sum(max(0, task.attempts - 1) for task in snapshot.plan.tasks)
        snapshot.metrics = {
            "duration_seconds": duration,
            "total_retries": float(total_retries),
            "completed_tasks": float(len(snapshot.completed_task_ids)),
            "failed_tasks": float(len(snapshot.failed_task_ids)),
            "skipped_tasks": float(len(snapshot.skipped_task_ids)),
            "progress_percent": self._progress(snapshot).percent_complete,
        }

    def _all_terminal(self, snapshot: WorkflowSnapshot) -> bool:
        return all(task.status in (TaskStatus.SUCCESS, TaskStatus.FAILED) for task in snapshot.plan.tasks)

    def _final_run_status(self, snapshot: WorkflowSnapshot) -> WorkflowRunStatus:
        if snapshot.cancelled_task_ids:
            return WorkflowRunStatus.CANCELLED
        if snapshot.failed_task_ids:
            return WorkflowRunStatus.ESCALATED
        return WorkflowRunStatus.SUCCESS

    def _domain_status(self, status: WorkflowRunStatus) -> WorkflowStatus:
        if status == WorkflowRunStatus.SUCCESS:
            return WorkflowStatus.SUCCESS
        if status == WorkflowRunStatus.CANCELLED:
            return WorkflowStatus.FAILED
        if status in {WorkflowRunStatus.ESCALATED, WorkflowRunStatus.ROLLED_BACK}:
            return WorkflowStatus.ESCALATED
        if status == WorkflowRunStatus.FAILED:
            return WorkflowStatus.FAILED
        return WorkflowStatus.RUNNING

    def _terminal_event(self, status: WorkflowStatus) -> LifecycleEvent:
        if status == WorkflowStatus.SUCCESS:
            return LifecycleEvent.WORKFLOW_COMPLETED
        if status == WorkflowStatus.FAILED:
            return LifecycleEvent.WORKFLOW_FAILED
        return LifecycleEvent.WORKFLOW_ESCALATED

    def _summary(
        self,
        snapshot: WorkflowSnapshot,
        status: WorkflowStatus,
        successful: int,
        failed: int,
    ) -> str:
        return (
            f"Workflow {status.value}. {successful} succeeded, {failed} failed, "
            f"{len(snapshot.skipped_task_ids)} skipped, {len(snapshot.cancelled_task_ids)} cancelled."
        )

    def _duration(self, started_at: datetime | None, completed_at: datetime | None) -> float:
        if started_at is None or completed_at is None:
            return 0.0
        return max(0.0, (completed_at - started_at).total_seconds())

    def _mark(self, collection: list[str], task_id: str) -> None:
        if task_id not in collection:
            collection.append(task_id)


def execution_report_from_result(result: WorkflowExecutionResult) -> ExecutionReport:
    """Convert workflow engine result into the stable orchestrator report model."""

    return ExecutionReport(
        workflow_id=result.workflow_id,
        request=result.request,
        status=result.status,
        plan_id=result.plan_id,
        total_tasks=result.total_tasks,
        successful_tasks=result.successful_tasks,
        failed_tasks=result.failed_tasks,
        escalated=result.escalated,
        tasks=result.tasks,
        started_at=result.started_at,
        completed_at=result.completed_at,
        summary=result.summary,
    )
