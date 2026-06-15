import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch
from pytest_asyncio import fixture
from project_agent import init_orchestrator
from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus

@fixture
async def system_context(tmp_path):
    """Initializes the orchestrator and tool layer for testing with a temp state."""
    with patch("project_agent.PROJECT_DIR", tmp_path):
        orchestrator = await init_orchestrator()
        from project_agent import tool_executor
        yield orchestrator, tool_executor

@pytest.mark.asyncio
async def test_salesforce_cli_authentication(system_context):
    """
    Verify that 'sf' is not only found, but authenticated.
    This tests the Tool Layer -> OS -> Salesforce connection.
    """
    _, executor = system_context
    
    # We attempt to list orgs to verify authentication state
    request = ToolRequest(
        workflow_id="test-auth",
        tool_name="sf",
        input={
            "args": ["org", "list", "--json"]
        }
    )
    
    response = await executor.execute(request)
    
    assert response.status == ToolStatus.SUCCESS, f"SF CLI failed: {response.error}"
    assert "result" in response.output, "SF CLI did not return expected JSON structure"
    
    # Check if there is at least one authenticated org
    orgs = response.output.get("result", {}).get("nonScratchOrgs", []) + \
           response.output.get("result", {}).get("scratchOrgs", [])
    
    authenticated = any(org.get("connectedStatus") == "Connected" for org in orgs)
    assert authenticated, "No authenticated Salesforce orgs found. Run 'sf org login web' first."

@pytest.mark.asyncio
async def test_orchestrator_planning_flow(system_context):
    """
    Verifies that the Orchestrator can trigger the Planner to create a 
    Salesforce-specific execution plan.
    """
    orchestrator, _ = system_context
    
    request_text = "Create an Apex class named LeadCleaner that deletes leads older than 90 days."
    
    # We only run the planning phase for this integration test to avoid 
    # side effects on the actual Salesforce org.
    plan = await orchestrator.planner.create_plan(request_text)
    
    assert plan is not None
    assert len(plan.tasks) > 0
    
    # Verify the planner assigned tasks to appropriate agents
    agent_names = [task.agent for task in plan.tasks]
    assert "salesforce_engineer" in agent_names or "engineer" in agent_names
    
    # Verify dependencies exist (e.g., Engineer depends on Analysis)
    if len(plan.tasks) > 1:
        has_dependencies = any(len(task.dependencies) > 0 for task in plan.tasks)
        assert has_dependencies, "Planner should have created a DAG with dependencies."

@pytest.mark.asyncio
async def test_metadata_hallucination_prevention(system_context):
    """
    Verify the tool layer's XML processing doesn't inject garbage tags.
    """
    _, executor = system_context
    # This would test the XML tool specifically if used by the engineer
    # to ensure it follows the rules set in our SYSTEM_PROMPT_BASE
    pass