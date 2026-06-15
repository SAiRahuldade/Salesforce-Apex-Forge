"""Workflow management routes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from salesforce_ai_engineer.agent.models import ExecutionPlan, TaskStatus, WorkflowStatus
from salesforce_ai_engineer.api.dependencies import APIContainer, get_api_container
from salesforce_ai_engineer.api.schemas import (
    ControlOperationResponse,
    TaskResponse,
    WorkflowDetailResponse,
    WorkflowResponse,
    WorkflowSubmissionRequest,
)
from salesforce_ai_engineer.core.logging import get_logger
from salesforce_ai_engineer.workflow.models import WorkflowRunStatus, WorkflowSnapshot

logger = get_logger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])

_PENDING_STATUSES = {
    WorkflowRunStatus.INITIALIZED,
}
_RUNNING_STATUSES = {
    WorkflowRunStatus.SCHEDULED,
    WorkflowRunStatus.RUNNING,
    WorkflowRunStatus.CANCEL_REQUESTED,
    WorkflowRunStatus.ROLLING_BACK,
}


def _workflow_status_from_snapshot(snapshot: WorkflowSnapshot) -> WorkflowStatus:
    if snapshot.status in _PENDING_STATUSES:
        return WorkflowStatus.PENDING
    if snapshot.status in _RUNNING_STATUSES:
        return WorkflowStatus.RUNNING
    if snapshot.status == WorkflowRunStatus.SUCCESS:
        return WorkflowStatus.SUCCESS
    if snapshot.status in {WorkflowRunStatus.ESCALATED, WorkflowRunStatus.ROLLED_BACK}:
        return WorkflowStatus.ESCALATED
    if snapshot.status in {WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED}:
        return WorkflowStatus.FAILED
    return WorkflowStatus.RUNNING


def _snapshot_summary(snapshot: WorkflowSnapshot, workflow_status: WorkflowStatus) -> str:
    successful = len([task for task in snapshot.plan.tasks if task.status == TaskStatus.SUCCESS])
    failed = len([task for task in snapshot.plan.tasks if task.status == TaskStatus.FAILED])
    pending = len([task for task in snapshot.plan.tasks if task.status == TaskStatus.PENDING])
    return (
        f"Workflow {workflow_status.value}. "
        f"{successful} succeeded, {failed} failed, {pending} pending."
    )


def _response_from_snapshot(snapshot: WorkflowSnapshot) -> WorkflowResponse:
    workflow_status = _workflow_status_from_snapshot(snapshot)
    successful = len([task for task in snapshot.plan.tasks if task.status == TaskStatus.SUCCESS])
    failed = len([task for task in snapshot.plan.tasks if task.status == TaskStatus.FAILED])
    return WorkflowResponse(
        workflow_id=snapshot.workflow_id,
        status=workflow_status,
        request=snapshot.request,
        plan_id=snapshot.plan.id if snapshot.plan else None,
        total_tasks=len(snapshot.plan.tasks),
        successful_tasks=successful,
        failed_tasks=failed,
        escalated=workflow_status == WorkflowStatus.ESCALATED,
        started_at=snapshot.created_at,
        completed_at=snapshot.completed_at,
        summary=_snapshot_summary(snapshot, workflow_status),
    )


async def _seed_pending_workflow(
    workflow_engine,
    workflow_id: str,
    request: str,
) -> None:
    snapshot = WorkflowSnapshot(
        workflow_id=workflow_id,
        request=request,
        plan=ExecutionPlan(objective=request, tasks=[]),
        status=WorkflowRunStatus.INITIALIZED,
    )
    await workflow_engine._checkpoint(snapshot, "workflow submitted")


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_workflow(
    request: WorkflowSubmissionRequest,
    container: APIContainer = Depends(get_api_container),
) -> WorkflowResponse:
    """Submit a new workflow for execution."""
    try:
        workflow_id = str(uuid4())
        orchestrator = container.orchestrator
        workflow_engine = container.workflow_engine

        await _seed_pending_workflow(workflow_engine, workflow_id, request.request)

        asyncio.create_task(
            orchestrator.run(request.request, workflow_id=workflow_id)
        )

        return WorkflowResponse(
            workflow_id=workflow_id,
            status=WorkflowStatus.PENDING,
            request=request.request,
            summary="Workflow submitted and queued for execution",
        )
    except Exception as exc:
        logger.error(f"Failed to submit workflow: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit workflow: {str(exc)}",
        ) from exc


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow_status(
    workflow_id: str,
    container: APIContainer = Depends(get_api_container),
) -> WorkflowResponse:
    """Get workflow execution status."""
    try:
        workflow_engine = container.workflow_engine
        snapshot = await workflow_engine.load_snapshot(workflow_id)

        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow {workflow_id} not found",
            )

        return _response_from_snapshot(snapshot)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get workflow status: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get workflow status: {str(exc)}",
        ) from exc


@router.get("/{workflow_id}/details", response_model=WorkflowDetailResponse)
async def get_workflow_details(
    workflow_id: str,
    container: APIContainer = Depends(get_api_container),
) -> WorkflowDetailResponse:
    """Get detailed workflow status including tasks."""
    try:
        workflow_engine = container.workflow_engine
        snapshot = await workflow_engine.load_snapshot(workflow_id)

        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow {workflow_id} not found",
            )

        workflow_status = _workflow_status_from_snapshot(snapshot)
        tasks = [
            TaskResponse(
                id=task.id,
                title=task.title,
                description=task.description,
                agent=task.agent,
                status=task.status,
                dependencies=list(task.dependencies),
                input=dict(task.input),
                output=task.output,
                error=task.error,
            )
            for task in snapshot.plan.tasks
        ]

        return WorkflowDetailResponse(
            workflow_id=workflow_id,
            status=workflow_status,
            request=snapshot.request,
            plan_id=snapshot.plan.id if snapshot.plan else None,
            tasks=tasks,
            total_tasks=len(tasks),
            successful_tasks=len([task for task in tasks if task.status == TaskStatus.SUCCESS]),
            failed_tasks=len([task for task in tasks if task.status == TaskStatus.FAILED]),
            escalated=workflow_status == WorkflowStatus.ESCALATED,
            started_at=snapshot.created_at,
            completed_at=snapshot.completed_at,
            summary=_snapshot_summary(snapshot, workflow_status),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get workflow details: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get workflow details: {str(exc)}",
        ) from exc


@router.post("/{workflow_id}/pause", response_model=ControlOperationResponse)
async def pause_workflow(
    workflow_id: str,
    container: APIContainer = Depends(get_api_container),
) -> ControlOperationResponse:
    """Pause a running workflow."""
    try:
        workflow_engine = container.workflow_engine
        await workflow_engine.pause(workflow_id)

        return ControlOperationResponse(
            workflow_id=workflow_id,
            operation="pause",
            status="success",
            message=f"Workflow {workflow_id} paused",
        )
    except Exception as exc:
        logger.error(f"Failed to pause workflow: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause workflow: {str(exc)}",
        ) from exc


@router.post("/{workflow_id}/resume", response_model=ControlOperationResponse)
async def resume_workflow(
    workflow_id: str,
    container: APIContainer = Depends(get_api_container),
) -> ControlOperationResponse:
    """Resume a paused workflow."""
    try:
        workflow_engine = container.workflow_engine
        await workflow_engine.resume(workflow_id)

        return ControlOperationResponse(
            workflow_id=workflow_id,
            operation="resume",
            status="success",
            message=f"Workflow {workflow_id} resumed",
        )
    except Exception as exc:
        logger.error(f"Failed to resume workflow: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume workflow: {str(exc)}",
        ) from exc


@router.post("/{workflow_id}/cancel", response_model=ControlOperationResponse)
async def cancel_workflow(
    workflow_id: str,
    container: APIContainer = Depends(get_api_container),
) -> ControlOperationResponse:
    """Cancel a running workflow."""
    try:
        workflow_engine = container.workflow_engine
        await workflow_engine.cancel(workflow_id)

        return ControlOperationResponse(
            workflow_id=workflow_id,
            operation="cancel",
            status="success",
            message=f"Workflow {workflow_id} cancelled",
        )
    except Exception as exc:
        logger.error(f"Failed to cancel workflow: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel workflow: {str(exc)}",
        ) from exc
