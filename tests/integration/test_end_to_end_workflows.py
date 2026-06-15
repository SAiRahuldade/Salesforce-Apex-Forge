"""End-to-end integration tests for complete workflows.

This test suite validates the entire workflow from request to completion,
including planning, execution, verification, and deployment phases.
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import UTC, datetime
from pytest_asyncio import fixture

from salesforce_ai_engineer.agent.models import (
    ExecutionPlan,
    ExecutionTask,
    TaskResult,
    TaskStatus,
    WorkflowStatus,
    SalesforceWorkType,
)
from salesforce_ai_engineer.agent.orchestrator import OrchestratorAgent
from salesforce_ai_engineer.agent.planner import OllamaPlannerAgent
from salesforce_ai_engineer.agent.recovery import RuleBasedRecoveryAgent
from salesforce_ai_engineer.agent.registry import AgentRegistry
from salesforce_ai_engineer.core.bootstrap import build_container
from salesforce_ai_engineer.core.events import EventBus
from salesforce_ai_engineer.core.state import StateManager
from salesforce_ai_engineer.memory import MemoryManager, SQLiteMemoryStore
from salesforce_ai_engineer.workflow import WorkflowExecutionEngine
from salesforce_ai_engineer.verifier.agent import VerifierAgent
from salesforce_ai_engineer.deployment.agent import DeploymentAgent
from salesforce_ai_engineer.salesforce_engineer.agent import SalesforceEngineerAgent
from salesforce_ai_engineer.tools.executor import ToolExecutor
from salesforce_ai_engineer.tools.registry import ToolRegistry
from salesforce_ai_engineer.tools.factory import build_tool_registry
from pathlib import Path
import tempfile


class MockSalesforceEngineerAgent:
    """Mock Salesforce Engineer Agent for testing."""

    async def execute(self, task: ExecutionTask) -> TaskResult:
        """Mock execution that generates artifacts."""
        # Check if task should fail (for testing rollback)
        if task.input.get("should_fail", False):
            return TaskResult(
                task_id=task.id,
                success=False,
                output={"error": "Task failed as configured for testing"}
            )
        
        artifacts = {}
        for t in [task]:
            artifacts[f"artifact-{t.id}"] = {
                "type": "apex",
                "code": f"public class {t.title.replace(' ', '')} {{ }}",
                "metadata": t.input,
            }
        
        return TaskResult(
            task_id=task.id,
            success=True,
            output={"artifacts": artifacts, "workflow_id": task.input.get("workflow_id", "unknown")}
        )


class MockVerifierAgent:
    """Mock Verifier Agent for testing."""

    async def verify_plan(self, plan: ExecutionPlan, artifacts: dict, workflow_id: str):
        """Mock verification that always passes."""
        from salesforce_ai_engineer.verifier.models import VerificationReport, QualityScore

        return VerificationReport(
            workflow_id=workflow_id,
            plan_id=plan.id,
            artifacts_analyzed=len(artifacts),
            total_issues=0,
            critical_issues=0,
            high_issues=0,
            medium_issues=0,
            low_issues=0,
            info_issues=0,
            issues=[],
            quality_score=QualityScore(
                project_id="test",
                overall_score=95.0,
                security_score=95.0,
                performance_score=95.0,
                maintainability_score=95.0,
                best_practices_score=95.0
            ),
            approved_for_deployment=True,
            approval_notes="All checks passed",
            rejection_reason="",
            recovery_recommendations=[],
            verification_duration_seconds=1.0,
        )


class MockDeploymentAgent:
    """Mock Deployment Agent for testing."""

    async def deploy(self, request):
        """Mock deployment that always succeeds."""
        from salesforce_ai_engineer.deployment.models import DeploymentReport, DeploymentStatus, DeploymentStrategy

        return DeploymentReport(
            deployment_id=str(uuid4()),
            workflow_id=request.workflow_id,
            request_id=request.id,
            strategy=request.strategy,
            status=DeploymentStatus.SUCCEEDED,
            environment=request.environment,
            deployment_duration_seconds=5.0,
            components_deployed=len(request.artifacts),
            failed_components=0,
        )


@fixture
async def integration_container():
    """Create a fully integrated container for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal container
        from salesforce_ai_engineer.core.container import Container
        from salesforce_ai_engineer.config.settings import Settings
        from salesforce_ai_engineer.config import ConfigurationManager
        from salesforce_ai_engineer.core.logging import configure_logging

        manager = ConfigurationManager()
        manager.ensure_runtime_directories()
        settings = manager.settings

        container = Container()
        container.register_instance("settings", settings)
        container.register_instance("logger", configure_logging(settings.logging, "test"))
        container.register_instance("event_bus", EventBus())

        # Memory
        db_path = Path(tmpdir) / "test_memory.db"
        memory_store = SQLiteMemoryStore(db_path)
        await memory_store.open()
        container.register_instance("memory_store", memory_store)
        container.register_factory(
            "memory_manager",
            lambda s: MemoryManager(
                store=s.resolve("memory_store"),
                event_bus=s.resolve("event_bus"),
                logger_instance=s.resolve("logger"),
            ),
            singleton=True,
        )

        # State
        state_path = Path(tmpdir) / "test_state.json"
        container.register_instance("state_manager", StateManager(state_path))

        # Tools
        tool_registry = build_tool_registry(settings, Path.cwd())
        container.register_instance("tool_registry", tool_registry)
        container.register_factory(
            "tool_executor",
            lambda s: ToolExecutor(
                registry=s.resolve("tool_registry"),
                event_bus=s.resolve("event_bus"),
                logger_instance=s.resolve("logger"),
            ),
            singleton=True,
        )

        # Agents
        container.register_instance("salesforce_engineer", MockSalesforceEngineerAgent())
        container.register_instance("verifier", MockVerifierAgent())
        container.register_instance("deployment", MockDeploymentAgent())

        # Agent Registry
        from salesforce_ai_engineer.agent.adapters import (
            SalesforceEngineerTaskAdapter,
            VerifierTaskAdapter,
            DeploymentTaskAdapter,
        )

        agent_registry = AgentRegistry()
        agent_registry.register(
            "salesforce_engineer",
            SalesforceEngineerTaskAdapter(
                container.resolve("salesforce_engineer"),
                container.resolve("tool_executor"),
            ),
        )
        agent_registry.register(
            "verifier",
            VerifierTaskAdapter(container.resolve("verifier")),
        )
        agent_registry.register(
            "deployment",
            DeploymentTaskAdapter(container.resolve("deployment"), None),
        )
        container.register_instance("agent_registry", agent_registry)

        # Recovery
        container.register_instance(
            "recovery_agent", RuleBasedRecoveryAgent()
        )

        # Workflow Engine
        container.register_factory(
            "workflow_engine",
            lambda s: WorkflowExecutionEngine(
                agent_registry=s.resolve("agent_registry"),
                recovery_agent=s.resolve("recovery_agent"),
                event_bus=s.resolve("event_bus"),
                memory_manager=s.resolve("memory_manager"),
                state_manager=s.resolve("state_manager"),
            ),
            singleton=True,
        )

        yield container

        # Cleanup
        await memory_store.close()


@pytest.mark.asyncio
async def test_complete_apex_workflow(integration_container):
    """Test complete workflow for Apex class generation and deployment."""
    # Create execution plan
    plan = ExecutionPlan(
        objective="Create a simple Apex class for data validation",
        tasks=[
            ExecutionTask(
                id="task-1",
                title="Generate Apex Class",
                description="Create validation class",
                agent="salesforce_engineer",
                work_type=SalesforceWorkType.APEX,
                input={"class_name": "DataValidator", "methods": ["validate"]},
            ),
            ExecutionTask(
                id="task-2",
                title="Verify Code",
                description="Verify generated code",
                agent="verifier",
                work_type=SalesforceWorkType.SECURITY,
                input={},
                dependencies=["task-1"],
            ),
            ExecutionTask(
                id="task-3",
                title="Deploy to Org",
                description="Deploy to Salesforce",
                agent="deployment",
                work_type=SalesforceWorkType.DEPLOYMENT,
                input={"environment": "sandbox"},
                dependencies=["task-2"],
            ),
        ],
    )

    # Execute via workflow engine
    workflow_engine = integration_container.resolve("workflow_engine")
    result = await workflow_engine.execute_plan(plan, request="Create validation class")

    # Verify results
    assert result.status == WorkflowStatus.SUCCESS
    assert result.successful_tasks == 3
    assert result.failed_tasks == 0
    assert len(result.tasks) == 3

    # Verify task order (dependencies respected)
    task_order = [task.title for task in result.tasks]
    assert task_order.index("Generate Apex Class") < task_order.index("Verify Code")
    assert task_order.index("Verify Code") < task_order.index("Deploy to Org")


@pytest.mark.asyncio
async def test_workflow_with_recovery(integration_container):
    """Test workflow with automatic recovery from transient failures."""
    from salesforce_ai_engineer.agent.models import RecoveryAction, RecoveryDecision

    class FlakyAgent:
        def __init__(self):
            self.attempts = 0

        async def execute(self, task):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("Transient error")
            from salesforce_ai_engineer.agent.models import TaskResult
            return TaskResult(task_id=task.id, success=True, output={"result": "ok"})

    # Register flaky agent
    agent_registry = integration_container.resolve("agent_registry")
    from salesforce_ai_engineer.agent.contracts import TaskAgent

    class FlakyAdapter(TaskAgent):
        def __init__(self, agent):
            self.agent = agent

        async def execute(self, task):
            return await self.agent.execute(task)

    agent_registry.register("flaky", FlakyAdapter(FlakyAgent()))

    # Create plan with flaky task
    plan = ExecutionPlan(
        objective="Test recovery",
        tasks=[
            ExecutionTask(
                id="flaky-1",
                title="Flaky Task",
                description="Task that fails once",
                agent="flaky",
                input={},
            ),
        ],
    )

    # Execute with recovery
    workflow_engine = integration_container.resolve("workflow_engine")
    result = await workflow_engine.execute_plan(plan, request="Test recovery")

    # Verify recovery worked
    assert result.status == WorkflowStatus.SUCCESS
    assert result.successful_tasks == 1


@pytest.mark.asyncio
async def test_parallel_workflow_execution(integration_container):
    """Test parallel execution of independent tasks."""
    plan = ExecutionPlan(
        objective="Generate multiple components in parallel",
        tasks=[
            ExecutionTask(
                title="Class A",
                description="Generate class A",
                agent="salesforce_engineer",
                work_type=SalesforceWorkType.APEX,
                input={"class_name": "ClassA"},
            ),
            ExecutionTask(
                title="Class B",
                description="Generate class B",
                agent="salesforce_engineer",
                work_type=SalesforceWorkType.APEX,
                input={"class_name": "ClassB"},
            ),
            ExecutionTask(
                title="Class C",
                description="Generate class C",
                agent="salesforce_engineer",
                work_type=SalesforceWorkType.APEX,
                input={"class_name": "ClassC"},
            ),
        ],
    )

    # Execute with parallel policy
    from salesforce_ai_engineer.workflow.models import WorkflowExecutionPolicy

    policy = WorkflowExecutionPolicy(max_parallel_tasks=3)
    workflow_engine = integration_container.resolve("workflow_engine")
    workflow_engine.default_policy = policy

    result = await workflow_engine.execute_plan(plan, request="Generate parallel classes")

    # Verify all tasks completed
    assert result.status == WorkflowStatus.SUCCESS
    assert result.successful_tasks == 3


@pytest.mark.asyncio
async def test_workflow_checkpoint_and_resume(integration_container):
    """Test workflow checkpointing and resume capability."""
    plan = ExecutionPlan(
        objective="Test checkpointing",
        tasks=[
            ExecutionTask(
                id="task-1",
                title="Task 1",
                description="First task",
                agent="salesforce_engineer",
                input={},
            ),
            ExecutionTask(
                id="task-2",
                title="Task 2",
                description="Second task",
                agent="salesforce_engineer",
                input={},
                dependencies=["task-1"],
            ),
        ],
    )

    workflow_id = str(uuid4())
    workflow_engine = integration_container.resolve("workflow_engine")

    # Execute first time
    result1 = await workflow_engine.execute_plan(
        plan, request="Test checkpointing", workflow_id=workflow_id
    )

    # Verify checkpoint was saved
    snapshot = await workflow_engine.load_snapshot(workflow_id)
    assert snapshot is not None
    assert snapshot.workflow_id == workflow_id

    # Resume from checkpoint
    result2 = await workflow_engine.resume(workflow_id)

    # Verify resume worked
    assert result2.status == WorkflowStatus.SUCCESS


@pytest.mark.asyncio
async def test_memory_persistence_across_workflow(integration_container):
    """Test that workflow execution persists to memory correctly."""
    memory_manager = integration_container.resolve("memory_manager")

    # Execute a workflow
    plan = ExecutionPlan(
        objective="Test memory persistence",
        tasks=[
            ExecutionTask(
                title="Memory Test Task",
                description="Task that stores to memory",
                agent="salesforce_engineer",
                input={},
            ),
        ],
    )

    workflow_engine = integration_container.resolve("workflow_engine")
    result = await workflow_engine.execute_plan(plan, request="Test memory")

    # Verify memory has records
    stats = await memory_manager.get_system_stats()
    assert stats["total_records"] > 0

    # Verify we can search for the workflow
    records = await memory_manager.search_memory(keywords=["Test"])
    assert len(records) > 0


@pytest.mark.asyncio
async def test_event_propagation_through_workflow(integration_container):
    """Test that events are properly propagated during workflow execution."""
    event_bus = integration_container.resolve("event_bus")
    events_received = []

    # Subscribe to workflow events
    async def event_handler(event):
        events_received.append(event)

    await event_bus.subscribe("workflow.*", event_handler)

    # Execute workflow
    plan = ExecutionPlan(
        objective="Test events",
        tasks=[
            ExecutionTask(
                title="Event Test Task",
                description="Task that emits events",
                agent="salesforce_engineer",
                input={},
            ),
        ],
    )

    workflow_engine = integration_container.resolve("workflow_engine")
    result = await workflow_engine.execute_plan(plan, request="Test events")

    # Verify events were received
    assert len(events_received) > 0


@pytest.mark.asyncio
async def test_workflow_with_rollback(integration_container):
    """Test workflow rollback on failure."""
    from salesforce_ai_engineer.workflow.models import WorkflowExecutionPolicy

    # Create a plan that will fail
    plan = ExecutionPlan(
        objective="Test rollback",
        tasks=[
            ExecutionTask(
                id="task-1",
                title="Task 1",
                description="First task",
                agent="salesforce_engineer",
                input={},
            ),
            ExecutionTask(
                id="task-2",
                title="Failing Task",
                description="This task will fail",
                agent="salesforce_engineer",
                input={"should_fail": True},
                dependencies=["task-1"],
            ),
        ],
    )

    # Configure rollback policy
    policy = WorkflowExecutionPolicy(
        fail_fast=True,
        rollback_on_failure=True,
    )

    workflow_engine = integration_container.resolve("workflow_engine")
    workflow_engine.default_policy = policy

    # Execute - should fail and rollback
    result = await workflow_engine.execute_plan(plan, request="Test rollback")

    # Verify failure and rollback
    assert result.status in [WorkflowStatus.ESCALATED, WorkflowStatus.FAILED]
    assert result.failed_tasks > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
