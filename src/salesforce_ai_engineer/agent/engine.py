import asyncio
import logging
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any, Set
from uuid import uuid4

from salesforce_ai_engineer.agent.models import (
    ExecutionPlan, ExecutionTask, TaskResult, TaskStatus, 
    WorkflowStatus, RecoveryAction
)
from salesforce_ai_engineer.workflow.dag import DAG

logger = logging.getLogger(__name__)

class WorkflowExecutionEngine:
    """The core engine that executes a DAG of tasks using registered agents."""
    
    STATE_NAMESPACE = "workflow_snapshots"

    def __init__(
        self,
        agent_registry: Any,
        recovery_agent: Any,
        event_bus: Any,
        memory_manager: Optional[Any] = None,
        state_manager: Optional[Any] = None,
        max_parallel_tasks: int = 4
    ):
        self.agent_registry = agent_registry
        self.recovery_agent = recovery_agent
        self.event_bus = event_bus
        self.memory_manager = memory_manager
        self.state_manager = state_manager
        self.semaphore = asyncio.Semaphore(max_parallel_tasks)
        self.running_tasks: Set[str] = set()
        self._workflow_artifacts: Dict[str, dict[str, Any]] = {}

    def _collect_workflow_artifacts(self, workflow_id: str, plan: ExecutionPlan) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for task in plan.tasks:
            if task.status != TaskStatus.SUCCESS or not task.output:
                continue
            task_artifacts = task.output.get("artifacts", {})
            if isinstance(task_artifacts, dict):
                merged.update(task_artifacts)
        cached = self._workflow_artifacts.get(workflow_id, {})
        return {**cached, **merged}

    def _inject_upstream_artifacts(self, workflow_id: str, plan: ExecutionPlan, task: ExecutionTask) -> None:
        upstream = self._collect_workflow_artifacts(workflow_id, plan)
        if upstream:
            existing = task.input.get("artifacts", {})
            if not isinstance(existing, dict):
                existing = {}
            task.input["artifacts"] = {**upstream, **existing}
        task.input["workflow_id"] = workflow_id

    async def execute_plan(
        self, 
        plan: ExecutionPlan, 
        request: str, 
        workflow_id: str = None
    ) -> Any:
        workflow_id = workflow_id or str(uuid4())
        dag = DAG.from_plan(plan)
        
        await self._emit("workflow.started", {"workflow_id": workflow_id, "plan_id": plan.id})

        try:
            while True:
                ready_task_ids = dag.ready_tasks(self.running_tasks)
                
                if not ready_task_ids and not self.running_tasks:
                    break
                
                if not ready_task_ids:
                    await asyncio.sleep(0.5)
                    continue
                
                for task_id in ready_task_ids:
                    task = next(t for t in plan.tasks if t.id == task_id)
                    asyncio.create_task(self._run_task(task, dag, workflow_id))
                
                await asyncio.sleep(0.1)

            success = all(t.status == TaskStatus.SUCCESS for t in plan.tasks)
            status = WorkflowStatus.SUCCESS if success else WorkflowStatus.FAILED
            
            if self.state_manager:
                snapshot = {
                    "workflow_id": workflow_id,
                    "request": request,
                    "plan": plan.model_dump(),
                    "completed_task_ids": [t.id for t in plan.tasks if t.status == TaskStatus.SUCCESS],
                    "updated_at": datetime.now(UTC),
                }
                snapshots = self.state_manager.get(self.STATE_NAMESPACE, {})
                if not isinstance(snapshots, dict):
                    snapshots = {}
                snapshots[workflow_id] = snapshot
                self.state_manager.set(self.STATE_NAMESPACE, snapshots)
            
            return {
                "workflow_id": workflow_id,
                "status": status,
                "tasks": plan.tasks
            }

        except Exception as e:
            logger.exception("Critical workflow failure")
            await self._emit("workflow.failed", {"workflow_id": workflow_id, "error": str(e)})
            raise

    async def _run_task(self, task: ExecutionTask, dag: DAG, workflow_id: str):
        async with self.semaphore:
            self.running_tasks.add(task.id)
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(UTC)
            task.attempts += 1

            await self._emit("task.started", {"workflow_id": workflow_id, "task_id": task.id})

            try:
                agent = self.agent_registry.resolve(task.agent)
                self._inject_upstream_artifacts(workflow_id, plan, task)
                
                result: TaskResult = await agent.execute(task)

                if result.success:
                    task.status = TaskStatus.SUCCESS
                    task.output = result.output
                    if result.output and isinstance(result.output.get("artifacts"), dict):
                        cached = self._workflow_artifacts.setdefault(workflow_id, {})
                        cached.update(result.output["artifacts"])
                    dag.mark_completed(task.id)
                    await self._emit("task.completed", {"workflow_id": workflow_id, "task_id": task.id})
                else:
                    await self._handle_task_failure(task, result.error, dag, workflow_id)

            except Exception as e:
                await self._handle_task_failure(task, str(e), dag, workflow_id)
            finally:
                task.completed_at = datetime.now(UTC)
                self.running_tasks.remove(task.id)

    async def _handle_task_failure(self, task: ExecutionTask, error: str, dag: DAG, workflow_id: str):
        decision = await self.recovery_agent.recover(task, error)
        
        if decision.action == RecoveryAction.RETRY:
            logger.info("Retrying task %s: %s", task.id, decision.reason)
            if decision.updated_input:
                task.input.update(decision.updated_input)
            task.status = TaskStatus.PENDING
        else:
            logger.error("Task %s failed permanently: %s", task.id, decision.reason)
            task.status = TaskStatus.FAILED
            task.error = error
            await self._emit("task.failed", {"workflow_id": workflow_id, "task_id": task.id, "error": error})

    async def _emit(self, event_name: str, payload: Dict[str, Any]):
        if self.event_bus:
            await self.event_bus.publish(f"engine.{event_name}", payload)

    async def resume(self, workflow_id: str) -> Any:
        if not self.state_manager:
            raise ValueError(f"No state_manager configured for resume")
        snapshots = self.state_manager.get(self.STATE_NAMESPACE, {})
        if not isinstance(snapshots, dict) or workflow_id not in snapshots:
            raise ValueError(f"No snapshot found for workflow {workflow_id!r}")
        snapshot = snapshots[workflow_id]
        plan_data = snapshot.get("plan", {})
        task_data_list = plan_data.get("tasks", [])
        completed_task_ids = set(snapshot.get("completed_task_ids", []))
        
        tasks = []
        for t_data in task_data_list:
            if isinstance(t_data, dict):
                task = ExecutionTask.model_validate(t_data)
                # Mark already completed tasks as SUCCESS
                if task.id in completed_task_ids:
                    task.status = TaskStatus.SUCCESS
                tasks.append(task)
            else:
                tasks.append(t_data)
        
        plan = ExecutionPlan(
            id=plan_data.get("id", workflow_id),
            objective=snapshot.get("request", ""),
            tasks=tasks
        )
        
        # Mark completed tasks in the DAG
        dag = DAG.from_plan(plan)
        for task_id in completed_task_ids:
            dag.mark_completed(task_id)
        
        workflow_id = workflow_id
        await self._emit("workflow.started", {"workflow_id": workflow_id, "plan_id": plan.id})

        try:
            while True:
                ready_task_ids = dag.ready_tasks(self.running_tasks)
                
                if not ready_task_ids and not self.running_tasks:
                    break
                
                if not ready_task_ids:
                    await asyncio.sleep(0.5)
                    continue
                
                for task_id in ready_task_ids:
                    task = next(t for t in plan.tasks if t.id == task_id)
                    asyncio.create_task(self._run_task(task, dag, workflow_id))
                
                await asyncio.sleep(0.1)

            success = all(t.status == TaskStatus.SUCCESS for t in plan.tasks)
            status = WorkflowStatus.SUCCESS if success else WorkflowStatus.FAILED
            
            return {
                "workflow_id": workflow_id,
                "status": status,
                "tasks": plan.tasks
            }

        except Exception as e:
            logger.exception("Critical workflow failure during resume")
            await self._emit("workflow.failed", {"workflow_id": workflow_id, "error": str(e)})
            raise

def execution_report_from_result(result: Any) -> Any:
    """Helper for Orchestrator compatibility."""
    from salesforce_ai_engineer.agent.models import ExecutionReport
    if result is None:
        return ExecutionReport(
            workflow_id="unknown",
            status=WorkflowStatus.FAILED,
            plan_id="unknown",
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=0,
            escalated=False,
            tasks=[],
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            request="unknown",
            summary="No result available",
        )
    tasks = result.get("tasks", [])
    successful = sum(1 for t in tasks if getattr(t, "status", None) == TaskStatus.SUCCESS)
    failed = sum(1 for t in tasks if getattr(t, "status", None) == TaskStatus.FAILED)
    summary = (
        f"Workflow {result.get('status', WorkflowStatus.PENDING).value}. "
        f"{successful} succeeded, {failed} failed, {len(tasks) - successful - failed} pending."
    )
    return ExecutionReport(
        workflow_id=result.get("workflow_id", "unknown"),
        status=result.get("status", WorkflowStatus.PENDING),
        plan_id=getattr(result.get("plan"), "id", "unknown") if result.get("plan") else "unknown",
        total_tasks=len(tasks),
        successful_tasks=successful,
        failed_tasks=failed,
        escalated=result.get("status", WorkflowStatus.PENDING) == WorkflowStatus.ESCALATED,
        tasks=tasks,
        started_at=result.get("started_at", datetime.now(UTC)),
        completed_at=datetime.now(UTC),
        request=result.get("request", "Inferred from result"),
        summary=summary,
    )