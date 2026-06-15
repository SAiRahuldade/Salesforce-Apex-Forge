"""Central async orchestrator agent."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from salesforce_ai_engineer.agent.contracts import PlannerAgent, RecoveryAgent
from salesforce_ai_engineer.agent.models import (
    ExecutionPlan,
    ExecutionReport,
    TaskStatus,
    WorkflowCheckpoint,
    WorkflowStatus,
)
from salesforce_ai_engineer.agent.registry import AgentRegistry
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.core.state import StateManager
from salesforce_ai_engineer.workflow.engine import (
    WorkflowExecutionEngine,
    execution_report_from_result,
)

if TYPE_CHECKING:
    from salesforce_ai_engineer.memory.manager import MemoryManager
    from salesforce_ai_engineer.reward_learning import RewardLearningEngine

logger = logging.getLogger(__name__)


class OrchestratorError(RuntimeError):
    """Raised when workflow orchestration cannot continue."""


class WorkflowEscalatedError(OrchestratorError):
    """Raised when automated recovery cannot resolve a failed task."""


class WorkflowGraphState(TypedDict, total=False):
    request: str
    workflow_id: str
    resume: bool
    checkpoint: WorkflowCheckpoint | None
    plan: ExecutionPlan
    engine_result: Any
    report: ExecutionReport
    started_at: datetime


class OrchestratorAgent:
    """Central brain that plans, dispatches, tracks, recovers, and reports."""

    CHECKPOINT_NAMESPACE = "workflow_checkpoints"

    def __init__(
        self,
        planner: PlannerAgent,
        recovery_agent: RecoveryAgent,
        agent_registry: AgentRegistry,
        state_manager: StateManager,
        event_bus: EventBus,
        memory_manager: "MemoryManager | None" = None,
        reward_learning_engine: "RewardLearningEngine | None" = None,
        workflow_engine: WorkflowExecutionEngine | None = None,
    ) -> None:
        self.planner = planner
        self.recovery_agent = recovery_agent
        self.agent_registry = agent_registry
        self.state_manager = state_manager
        self.event_bus = event_bus
        self.memory_manager = memory_manager
        self.reward_learning_engine = reward_learning_engine
        self.workflow_engine = workflow_engine or WorkflowExecutionEngine(
            agent_registry=agent_registry,
            recovery_agent=recovery_agent,
            event_bus=event_bus,
            state_manager=state_manager,
        )
        self._graph = self._build_graph()

    async def run(self, request: str, workflow_id: str | None = None) -> ExecutionReport:
        """Run a new workflow from a natural language request."""

        selected_workflow_id = workflow_id or str(uuid4())
        final_state = await self._graph.ainvoke(
            {
                "request": request,
                "workflow_id": selected_workflow_id,
                "resume": False,
                "started_at": datetime.now(UTC),
            }
        )
        report = final_state["report"]
        await self._save_workflow_checkpoint(selected_workflow_id, request, report)
        return report

    async def resume(self, workflow_id: str) -> ExecutionReport:
        """Resume a workflow from its latest checkpoint."""

        try:
            snapshot = self.load_checkpoint(workflow_id)
            if snapshot is None:
                raise OrchestratorError(f"No checkpoint found for workflow {workflow_id!r}")
            result = await self.workflow_engine.resume(workflow_id)
        except OrchestratorError:
            raise
        except Exception as exc:
            raise OrchestratorError(f"Could not resume workflow {workflow_id!r}: {exc}") from exc
        report = execution_report_from_result(result)
        await self._save_workflow_checkpoint(workflow_id, snapshot.request, report)
        await self._learn_from_report(report)
        await self._persist_workflow_memory(report)
        return report

    async def _save_workflow_checkpoint(self, workflow_id: str, request: str, report: ExecutionReport) -> None:
        if self.state_manager is None:
            return
        try:
            from salesforce_ai_engineer.agent.models import ExecutionPlan
            plan = getattr(report, "plan", None)
            if isinstance(plan, ExecutionPlan):
                snapshot = {
                    "workflow_id": workflow_id,
                    "request": request,
                    "plan": plan.model_dump(),
                    "completed_task_ids": [task.id for task in report.tasks if task.status == TaskStatus.SUCCESS],
                    "updated_at": datetime.now(UTC),
                }
                self.state_manager.set(self.CHECKPOINT_NAMESPACE, {**self.state_manager.get(self.CHECKPOINT_NAMESPACE, {}), workflow_id: snapshot})
        except Exception as exc:
            logger.debug("Failed to save workflow checkpoint for %s: %s", workflow_id, exc)

    def load_checkpoint(self, workflow_id: str) -> WorkflowCheckpoint | None:
        snapshots = self.state_manager.get(WorkflowExecutionEngine.STATE_NAMESPACE, {})
        if isinstance(snapshots, dict) and workflow_id in snapshots:
            snapshot = self.workflow_engine_snapshot_to_checkpoint(snapshots[workflow_id])
            if snapshot is not None:
                return snapshot
        checkpoints = self.state_manager.get(self.CHECKPOINT_NAMESPACE, {})
        if not isinstance(checkpoints, dict):
            return None
        payload = checkpoints.get(workflow_id)
        return WorkflowCheckpoint.model_validate(payload) if payload else None

    def workflow_engine_snapshot_to_checkpoint(self, payload: Any) -> WorkflowCheckpoint | None:
        try:
            from salesforce_ai_engineer.workflow import WorkflowSnapshot

            snapshot = WorkflowSnapshot.model_validate(payload)
            return WorkflowCheckpoint(
                workflow_id=snapshot.workflow_id,
                request=snapshot.request,
                plan=snapshot.plan,
                completed_task_ids=snapshot.completed_task_ids,
                updated_at=snapshot.updated_at,
                metadata={"source": "workflow_execution_engine", "version": snapshot.version},
            )
        except Exception:
            return None

    async def _plan_node(self, state: WorkflowGraphState) -> WorkflowGraphState:
        if state.get("resume") and state.get("checkpoint") is not None:
            checkpoint = state["checkpoint"]
            await self._emit(
                "orchestrator.workflow.resumed",
                {
                    "workflow_id": checkpoint.workflow_id,
                    "completed_task_ids": checkpoint.completed_task_ids,
                },
            )
            return {**state, "plan": checkpoint.plan}

        request = state["request"]
        workflow_id = state["workflow_id"]
        await self._emit("orchestrator.plan.requested", {"workflow_id": workflow_id})
        plan = await self.planner.create_plan(request)
        await self._emit(
            "orchestrator.plan.created",
            {
                "workflow_id": workflow_id,
                "plan_id": plan.id,
                "task_count": len(plan.tasks),
            },
        )
        return {**state, "plan": plan}

    async def _execute_node(self, state: WorkflowGraphState) -> WorkflowGraphState:
        plan = state["plan"]
        workflow_id = state["workflow_id"]

        await self._emit(
            "orchestrator.workflow.started",
            {"workflow_id": workflow_id, "plan_id": plan.id},
        )
        result = await self.workflow_engine.execute_plan(
            plan=plan,
            request=state["request"],
            workflow_id=workflow_id,
        )
        return {**state, "plan": plan, "engine_result": result}

    async def _report_node(self, state: WorkflowGraphState) -> WorkflowGraphState:
        engine_result = state.get("engine_result")
        if engine_result is not None:
            report = execution_report_from_result(engine_result)
            await self._emit(
                "orchestrator.workflow.completed",
                {
                    "workflow_id": report.workflow_id,
                    "status": report.status,
                    "successful_tasks": report.successful_tasks,
                    "failed_tasks": report.failed_tasks,
                    "escalated": report.escalated,
                },
            )
            await self._learn_from_report(report)
            await self._persist_workflow_memory(report)
            return {**state, "report": report}

        plan = state["plan"]
        workflow_id = state["workflow_id"]
        started_at = state["started_at"]
        successful_tasks = [task for task in plan.tasks if task.status == TaskStatus.SUCCESS]
        failed_tasks = [task for task in plan.tasks if task.status == TaskStatus.FAILED]
        pending_tasks = [task for task in plan.tasks if task.status == TaskStatus.PENDING]
        escalated = bool(failed_tasks or pending_tasks)
        status = (
            WorkflowStatus.ESCALATED
            if escalated
            else WorkflowStatus.SUCCESS
            if len(successful_tasks) == len(plan.tasks)
            else WorkflowStatus.FAILED
        )
        summary = self._build_summary(plan, status)

        report = ExecutionReport(
            workflow_id=workflow_id,
            request=state["request"],
            status=status,
            plan_id=plan.id,
            total_tasks=len(plan.tasks),
            successful_tasks=len(successful_tasks),
            failed_tasks=len(failed_tasks),
            escalated=escalated,
            tasks=plan.tasks,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            summary=summary,
        )
        await self._emit(
            "orchestrator.workflow.completed",
            {
                "workflow_id": workflow_id,
                "status": report.status,
                "successful_tasks": report.successful_tasks,
                "failed_tasks": report.failed_tasks,
                "escalated": report.escalated,
            },
        )
        await self._learn_from_report(report)
        await self._persist_workflow_memory(report)
        return {**state, "report": report}

    async def _persist_workflow_memory(self, report: ExecutionReport) -> None:
        if self.memory_manager is None:
            return
        try:
            duration = max(0.0, (report.completed_at - report.started_at).total_seconds())
            await self.memory_manager.store_workflow_history(
                workflow_id=report.workflow_id,
                workflow_type=report.plan_id,
                workflow_status=report.status.value,
                duration_seconds=duration,
                steps_executed=[task.id for task in report.tasks if task.status == TaskStatus.SUCCESS],
                created_by="orchestrator",
                request=report.request,
            )
            for task in report.tasks:
                task_duration = 0.0
                if task.started_at and task.completed_at:
                    task_duration = max(0.0, (task.completed_at - task.started_at).total_seconds())
                await self.memory_manager.store_execution_history(
                    agent_name=task.agent,
                    task_description=task.title,
                    success=task.status == TaskStatus.SUCCESS,
                    duration_seconds=task_duration,
                    created_by="orchestrator",
                    workflow_id=report.workflow_id,
                    task_id=task.id,
                )
        except Exception as exc:
            logger.exception("Failed to persist workflow memory for %s", report.workflow_id)
            await self._emit(
                "orchestrator.workflow.memory_failed",
                {"workflow_id": report.workflow_id, "error": str(exc)},
            )

    async def _learn_from_report(self, report: ExecutionReport) -> None:
        if self.reward_learning_engine is None:
            return
        try:
            learning_result = await self.reward_learning_engine.evaluate_execution_report(report)
            await self._emit(
                "orchestrator.workflow.learned",
                {
                    "workflow_id": report.workflow_id,
                    "workflow_score": learning_result.workflow_score.score,
                    "agent_count": len(learning_result.agent_scores),
                    "recommendation_count": len(learning_result.recommendations),
                },
            )
        except Exception as exc:
            logger.exception("Reward learning failed for workflow %s", report.workflow_id)
            await self._emit(
                "orchestrator.workflow.learning_failed",
                {
                    "workflow_id": report.workflow_id,
                    "error": str(exc),
                },
            )

    def _build_summary(self, plan: ExecutionPlan, status: WorkflowStatus) -> str:
        successful = len([task for task in plan.tasks if task.status == TaskStatus.SUCCESS])
        failed = len([task for task in plan.tasks if task.status == TaskStatus.FAILED])
        pending = len([task for task in plan.tasks if task.status == TaskStatus.PENDING])
        return (
            f"Workflow {status.value}. "
            f"{successful} succeeded, {failed} failed, {pending} pending."
        )

    async def _emit(self, name: str, payload: dict[str, Any]) -> None:
        await self.event_bus.publish(name, payload)

    def _build_graph(self):
        graph = StateGraph(WorkflowGraphState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("execute", self._execute_node)
        graph.add_node("report", self._report_node)
        graph.set_entry_point("plan")
        graph.add_edge("plan", "execute")
        graph.add_edge("execute", "report")
        graph.add_edge("report", END)
        return graph.compile()
