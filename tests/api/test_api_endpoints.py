"""Tests for REST API endpoints."""

from datetime import UTC, datetime
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from salesforce_ai_engineer.agent.models import ExecutionPlan, ExecutionTask, TaskStatus, WorkflowStatus
from salesforce_ai_engineer.api.dependencies import APIContainer
from salesforce_ai_engineer.api.main import create_app
from salesforce_ai_engineer.api.schemas import HealthStatus, WorkflowSubmissionRequest
from salesforce_ai_engineer.core.bootstrap import Container
from salesforce_ai_engineer.core.events import EventBus


@pytest.fixture
def mock_container():
    """Create a mock container with all dependencies."""
    from unittest.mock import MagicMock
    
    container = MagicMock()
    
    # Mock orchestrator
    mock_orchestrator = AsyncMock()
    
    # Define the get method to return mocks based on key
    def get_mock(key):
        mocks = {
            "orchestrator_agent": mock_orchestrator,
            "orchestrator": mock_orchestrator,
            "workflow_engine": AsyncMock(
                pause=AsyncMock(),
                resume=AsyncMock(),
                cancel=AsyncMock(),
                load_snapshot=AsyncMock(return_value=None),
                _checkpoint=AsyncMock(),
                state_manager=MagicMock(get=MagicMock(return_value={})),
            ),
            "agent_registry": MagicMock(
                _registry={"agent1": MagicMock(), "agent2": MagicMock()},
                registered_names=MagicMock(return_value=["agent1", "agent2"]),
                resolve=MagicMock(side_effect=lambda name: MagicMock()),
            ),
            "memory_manager": AsyncMock(
                health_check=AsyncMock(return_value=True),
                store=AsyncMock(
                    list_by_category=AsyncMock(return_value=([], 0))
                ),
            ),
            "event_bus": EventBus(),
            "state_manager": MagicMock(
                get=MagicMock(return_value={})
            ),
            "reward_learning_engine": AsyncMock(),
        }
        return mocks.get(key)
    
    container.resolve = MagicMock(side_effect=get_mock)
    container.get = container.resolve
    
    return container


@pytest.fixture
def client(mock_container: Container) -> TestClient:
    """Create FastAPI test client."""
    # Create app without the lifespan to avoid initialization issues
    app = FastAPI(
        title="Salesforce AI Engineer",
        description="Autonomous multi-agent platform for Salesforce automation",
        version="1.0.0",
    )
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Add routes from the original app
    from salesforce_ai_engineer.api.routes import health, metrics, workflows
    app.include_router(workflows.router)
    app.include_router(health.router)
    app.include_router(metrics.router)
    
    # Initialize API container with mock
    api_container = APIContainer()
    api_container.initialize(mock_container)
    
    # Override the dependency in the app
    from salesforce_ai_engineer.api.dependencies import get_api_container as original_get_api_container
    app.dependency_overrides[original_get_api_container] = lambda: api_container
    
    # Add root endpoint
    @app.get("/")
    async def root():
        """API root endpoint."""
        return {
            "name": "Salesforce AI Engineer",
            "version": "1.0.0",
            "status": "running",
            "endpoints": {
                "workflows": "/workflows",
                "health": "/health",
                "live": "/health/live",
                "ready": "/health/ready",
                "agents": "/health/agents",
                "metrics": "/metrics",
            },
        }
    
    return TestClient(app)


class TestWorkflowEndpoints:
    """Test workflow management endpoints."""
    
    def test_submit_workflow(self, client: TestClient):
        """Test workflow submission."""
        request_data = {
            "request": "Create a new Apex class",
            "priority": "high",
            "tags": ["test"],
        }
        
        response = client.post("/workflows", json=request_data)
        
        if response.status_code != 202:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
        assert response.status_code == 202
        data = response.json()
        assert "workflow_id" in data
        assert data["status"] == WorkflowStatus.PENDING
        assert data["request"] == request_data["request"]
    
    def test_get_workflow_status(self, client: TestClient):
        """Test getting workflow status."""
        workflow_id = "test-workflow-123"
        
        response = client.get(f"/workflows/{workflow_id}")
        
        # Endpoint should handle missing workflows gracefully
        assert response.status_code in [200, 404]
    
    def test_workflow_not_found(self, client: TestClient):
        """Test 404 for non-existent workflow."""
        response = client.get("/workflows/non-existent-workflow")
        assert response.status_code == 404
    
    def test_pause_workflow(self, client: TestClient):
        """Test pausing a workflow."""
        workflow_id = "test-workflow-123"
        
        response = client.post(f"/workflows/{workflow_id}/pause")
        
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == workflow_id
        assert data["operation"] == "pause"
        assert data["status"] == "success"
    
    def test_resume_workflow(self, client: TestClient):
        """Test resuming a workflow."""
        workflow_id = "test-workflow-123"
        
        response = client.post(f"/workflows/{workflow_id}/resume")
        
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == workflow_id
        assert data["operation"] == "resume"
        assert data["status"] == "success"
    
    def test_cancel_workflow(self, client: TestClient):
        """Test cancelling a workflow."""
        workflow_id = "test-workflow-123"
        
        response = client.post(f"/workflows/{workflow_id}/cancel")
        
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == workflow_id
        assert data["operation"] == "cancel"
        assert data["status"] == "success"


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_health_check(self, client: TestClient):
        """Test system health check."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert "components" in data
        assert isinstance(data["components"], list)
    
    def test_agents_health(self, client: TestClient):
        """Test agents health check."""
        response = client.get("/health/agents")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestMetricsEndpoints:
    """Test metrics endpoints."""
    
    def test_get_metrics(self, client: TestClient):
        """Test getting system metrics."""
        response = client.get("/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_workflows" in data
        assert "completed_workflows" in data
        assert "failed_workflows" in data
        assert "agents_available" in data
        assert "agents_total" in data
        assert "success_rate" in data


class TestRootEndpoint:
    """Test root endpoint."""
    
    def test_root_endpoint(self, client: TestClient):
        """Test API root endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Salesforce AI Engineer"
        assert "endpoints" in data
        assert "workflows" in data["endpoints"]
        assert "health" in data["endpoints"]
        assert "metrics" in data["endpoints"]


class TestErrorHandling:
    """Test error handling."""
    
    def test_invalid_request_schema(self, client: TestClient):
        """Test invalid request schema."""
        response = client.post("/workflows", json={})
        
        assert response.status_code == 422  # Validation error
    
    def test_missing_required_field(self, client: TestClient):
        """Test missing required field."""
        response = client.post("/workflows", json={"priority": "high"})
        
        assert response.status_code == 422  # Validation error
