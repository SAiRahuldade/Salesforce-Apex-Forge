"""Health check routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, status

from salesforce_ai_engineer.api.dependencies import APIContainer, get_api_container
from salesforce_ai_engineer.api.schemas import AgentHealthResponse, ComponentHealth, HealthResponse, HealthStatus
from salesforce_ai_engineer.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check(
    container: APIContainer = Depends(get_api_container),
) -> HealthResponse:
    """System health check."""
    try:
        components = []
        overall_status = HealthStatus.HEALTHY

        try:
            memory_manager = container.memory_manager
            is_healthy = await memory_manager.health_check()
            status_val = HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY
            components.append(
                ComponentHealth(
                    name="memory_manager",
                    status=status_val,
                    message="Memory storage operational" if is_healthy else "Memory storage unavailable",
                )
            )
            if not is_healthy:
                overall_status = HealthStatus.DEGRADED
        except Exception as exc:
            logger.warning(f"Memory manager health check failed: {exc}")
            components.append(
                ComponentHealth(
                    name="memory_manager",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Error: {str(exc)}",
                )
            )
            overall_status = HealthStatus.DEGRADED

        try:
            event_bus = container.event_bus
            if event_bus is not None:
                components.append(
                    ComponentHealth(
                        name="event_bus",
                        status=HealthStatus.HEALTHY,
                        message="Event bus operational",
                    )
                )
        except Exception as exc:
            logger.warning(f"Event bus health check failed: {exc}")
            components.append(
                ComponentHealth(
                    name="event_bus",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Error: {str(exc)}",
                )
            )
            overall_status = HealthStatus.DEGRADED

        try:
            registry = container.agent_registry
            if registry is not None:
                component_count = len(registry.registered_names())
                components.append(
                    ComponentHealth(
                        name="agent_registry",
                        status=HealthStatus.HEALTHY,
                        message=f"Agent registry operational ({component_count} agents registered)",
                    )
                )
        except Exception as exc:
            logger.warning(f"Agent registry health check failed: {exc}")
            components.append(
                ComponentHealth(
                    name="agent_registry",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Error: {str(exc)}",
                )
            )
            overall_status = HealthStatus.DEGRADED

        return HealthResponse(
            status=overall_status,
            components=components,
            timestamp=datetime.utcnow(),
        )
    except Exception as exc:
        logger.error(f"Health check failed: {exc}")
        return HealthResponse(
            status=HealthStatus.UNHEALTHY,
            components=[
                ComponentHealth(
                    name="system",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check error: {str(exc)}",
                )
            ],
            timestamp=datetime.utcnow(),
        )


@router.get("/agents", response_model=list[AgentHealthResponse], status_code=status.HTTP_200_OK)
async def agents_health(
    container: APIContainer = Depends(get_api_container),
) -> list[AgentHealthResponse]:
    """Check health of all registered agents."""
    try:
        registry = container.agent_registry
        agent_responses = []

        if registry is not None:
            for agent_name in registry.registered_names():
                try:
                    agent = registry.resolve(agent_name)
                    is_available = agent is not None

                    agent_responses.append(
                        AgentHealthResponse(
                            agent_name=agent_name,
                            available=is_available,
                            status=HealthStatus.HEALTHY if is_available else HealthStatus.UNHEALTHY,
                        )
                    )
                except Exception as exc:
                    logger.warning(f"Agent {agent_name} health check failed: {exc}")
                    agent_responses.append(
                        AgentHealthResponse(
                            agent_name=agent_name,
                            available=False,
                            status=HealthStatus.UNHEALTHY,
                        )
                    )

        return agent_responses
    except Exception as exc:
        logger.error(f"Agents health check failed: {exc}")
        return []
