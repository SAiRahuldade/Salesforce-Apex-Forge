"""Metrics and monitoring routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, status

from salesforce_ai_engineer.api.dependencies import APIContainer, get_api_container
from salesforce_ai_engineer.api.schemas import MetricsResponse
from salesforce_ai_engineer.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsResponse, status_code=status.HTTP_200_OK)
async def get_metrics(
    container: APIContainer = Depends(get_api_container),
) -> MetricsResponse:
    """Get system metrics."""
    try:
        memory_manager = container.memory_manager
        agent_registry = container.agent_registry

        total_workflows = 0
        completed_workflows = 0
        failed_workflows = 0
        escalated_workflows = 0
        agents_available = 0
        agents_total = 0

        if agent_registry is not None:
            registered = agent_registry.registered_names()
            agents_total = len(registered)
            for agent_name in registered:
                try:
                    agent_registry.resolve(agent_name)
                    agents_available += 1
                except Exception:
                    pass

        try:
            if memory_manager is not None:
                records, total = await memory_manager.store.list_by_category(
                    "EXECUTION_METRIC", limit=1000
                )
                total_workflows = total

                for record in records:
                    data = record.get("data", {}) if isinstance(record, dict) else {}
                    status_val = str(data.get("status", "")).lower()
                    if "success" in status_val or "completed" in status_val:
                        completed_workflows += 1
                    elif "failed" in status_val:
                        failed_workflows += 1
                    elif "escalated" in status_val:
                        escalated_workflows += 1
        except Exception as exc:
            logger.warning(f"Failed to get workflow metrics: {exc}")

        success_rate = (
            (completed_workflows / total_workflows * 100)
            if total_workflows > 0
            else 0.0
        )

        return MetricsResponse(
            total_workflows=total_workflows,
            completed_workflows=completed_workflows,
            failed_workflows=failed_workflows,
            escalated_workflows=escalated_workflows,
            success_rate=success_rate,
            agents_available=agents_available,
            agents_total=agents_total,
            timestamp=datetime.utcnow(),
        )
    except Exception as exc:
        logger.error(f"Failed to get metrics: {exc}")
        return MetricsResponse(timestamp=datetime.utcnow())
