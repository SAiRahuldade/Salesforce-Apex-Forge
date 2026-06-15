from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from salesforce_ai_engineer.models.domain import (
    AgentRequest,
    DeploymentReport,
    DeploymentStatus,
    ErrorReport,
    ExecutionPlan,
    ExecutionTask,
    MemoryRecord,
    RewardRecord,
    SalesforceWorkType,
    Severity,
    ToolRequest,
    VerificationReport,
    VerificationStatus,
)


def test_execution_plan_validates_dependency_graph() -> None:
    plan = ExecutionPlan(
        project="Hospital Management",
        objective="Plan hospital Salesforce implementation",
        tasks=[
            ExecutionTask(
                id="requirements",
                title="Requirements",
                description="Map hospital requirements.",
                agent="analysis-agent",
                work_type=SalesforceWorkType.ANALYSIS,
            ),
            ExecutionTask(
                id="security",
                title="Security",
                description="Plan access model.",
                agent="security-agent",
                work_type=SalesforceWorkType.SECURITY,
                dependencies=["requirements"],
            ),
        ],
    )

    assert plan.task_map()["security"].dependencies == ["requirements"]
    assert plan.model_dump(mode="json")["tasks"][0]["work_type"] == "analysis"


def test_execution_plan_rejects_cycles() -> None:
    with pytest.raises(ValidationError):
        ExecutionPlan(
            project="Cycle",
            objective="Invalid graph",
            tasks=[
                ExecutionTask(
                    id="a",
                    title="A",
                    description="Task A",
                    agent="agent",
                    dependencies=["b"],
                ),
                ExecutionTask(
                    id="b",
                    title="B",
                    description="Task B",
                    agent="agent",
                    dependencies=["a"],
                ),
            ],
        )


def test_immutable_records_are_json_serializable_and_frozen() -> None:
    request = AgentRequest(workflow_id="workflow-1", agent="planner", payload={"request": "Plan"})
    with pytest.raises(ValidationError):
        request.agent = "other"

    payload = request.model_dump(mode="json")

    assert payload["workflow_id"] == "workflow-1"
    assert isinstance(payload["created_at"], str)


def test_shared_reports_records_and_tool_envelopes() -> None:
    error = ErrorReport(
        workflow_id="workflow-1",
        severity=Severity.ERROR,
        message="Validation failed",
    )
    verification = VerificationReport(
        workflow_id="workflow-1",
        status=VerificationStatus.WARNING,
        checks=["Apex tests planned"],
        findings=["Coverage target missing"],
    )
    deployment = DeploymentReport(
        workflow_id="workflow-1",
        environment="sandbox",
        status=DeploymentStatus.VALIDATED,
        components=["CustomObject:Patient__c"],
        errors=[error],
    )
    reward = RewardRecord(
        workflow_id="workflow-1",
        agent="planner",
        score=0.8,
        reason="Plan was complete",
    )
    memory = MemoryRecord(
        namespace="project",
        key="hospital",
        value={"domain": "healthcare"},
    )
    tool_request = ToolRequest(
        workflow_id="workflow-1",
        tool_name="salesforce-metadata-reader",
        input={"component": "Patient__c"},
    )

    assert deployment.errors[0].message == "Validation failed"
    assert verification.model_dump(mode="json")["status"] == "warning"
    assert reward.score == 0.8
    assert memory.value["domain"] == "healthcare"
    assert tool_request.model_dump(mode="json")["tool_name"] == "salesforce-metadata-reader"
    assert datetime.fromisoformat(error.model_dump(mode="json")["created_at"]).tzinfo == UTC
