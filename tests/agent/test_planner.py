from __future__ import annotations

import json

import pytest

from salesforce_ai_engineer.agent import (
    OllamaPlannerAgent,
    PlannerAgentError,
    SalesforceWorkType,
)
from salesforce_ai_engineer.config.settings import OllamaConfig


class FakeOllamaClient:
    def __init__(self, payload: dict | str) -> None:
        self.payload = payload
        self.last_messages: list[dict[str, str]] = []

    @property
    def chat(self):
        return self._Chat(self)

    class _Chat:
        def __init__(self, outer):
            self.outer = outer

        @property
        def completions(self):
            return self._Completions(self.outer)

        class _Completions:
            def __init__(self, outer):
                self.outer = outer

            async def create(self, **kwargs):
                self.outer.last_messages = kwargs["messages"]
                content = self.outer.payload if isinstance(self.outer.payload, str) else json.dumps(self.outer.payload)
                return type('Response', (), {
                    'choices': [type('Choice', (), {
                        'message': type('Message', (), {'content': content})()
                    })()]
                })()


def planner_with(payload: dict | str) -> OllamaPlannerAgent:
    return OllamaPlannerAgent(
        config=OllamaConfig(base_url="http://localhost:11434", model="llama3.1"),
        client=FakeOllamaClient(payload),
    )


async def test_planner_returns_strong_salesforce_plan() -> None:
    planner = planner_with(
        {
            "project": "Hospital Management",
            "objective": "Plan a Salesforce hospital management implementation",
            "summary": "Plan metadata, security, automation, and deployment.",
            "missing_information": [],
            "tasks": [
                {
                    "id": "analyze-requirements",
                    "title": "Analyze requirements",
                    "description": "Identify Salesforce objects, personas, and automation boundaries.",
                    "agent": "analysis-agent",
                    "work_type": "analysis",
                    "priority": 1,
                    "dependencies": [],
                    "input": {"scope": "hospital management"},
                    "deliverables": ["Requirement map"],
                    "acceptance_criteria": ["Objects and personas are listed"],
                    "missing_information": [],
                    "max_attempts": 2,
                },
                {
                    "id": "plan-security",
                    "title": "Plan security",
                    "description": "Define permission set and sharing model planning tasks.",
                    "agent": "security-agent",
                    "work_type": "security",
                    "priority": 2,
                    "dependencies": ["analyze-requirements"],
                    "input": {"domain": "patient and staff access"},
                    "deliverables": ["Security plan"],
                    "acceptance_criteria": ["Access model is reviewable"],
                    "missing_information": [],
                    "max_attempts": 2,
                },
            ],
        }
    )

    plan = await planner.create_plan("Plan Salesforce hospital management in a sandbox org")

    assert plan.project == "Hospital Management"
    assert plan.tasks[0].work_type == SalesforceWorkType.ANALYSIS
    assert plan.tasks[0].priority == 1
    assert plan.tasks[1].dependencies == ["analyze-requirements"]
    assert plan.is_ready is True


async def test_planner_detects_missing_salesforce_environment() -> None:
    planner = planner_with(
        {
            "project": "Hospital Management",
            "objective": "Plan Salesforce work",
            "summary": "Plan work.",
            "missing_information": [],
            "tasks": [
                {
                    "id": "metadata-plan",
                    "title": "Plan metadata",
                    "description": "Plan object and field metadata.",
                    "agent": "metadata-agent",
                    "work_type": "metadata_generation",
                    "priority": 1,
                    "dependencies": [],
                    "input": {},
                    "deliverables": ["Metadata plan"],
                    "acceptance_criteria": ["Metadata scope is clear"],
                    "missing_information": [],
                }
            ],
        }
    )

    plan = await planner.create_plan("Plan Salesforce metadata for hospital management")

    assert "Target Salesforce org or environment is not specified" in plan.missing_information
    assert plan.is_ready is False


async def test_planner_rejects_executable_code() -> None:
    planner = planner_with(
        {
            "project": "Apex",
            "objective": "Plan Apex",
            "tasks": [
                {
                    "id": "write-apex",
                    "title": "Write Apex",
                    "description": "public class HospitalController {}",
                    "agent": "apex-agent",
                    "work_type": "apex",
                    "priority": 1,
                    "dependencies": [],
                    "input": {},
                }
            ],
        }
    )

    with pytest.raises(PlannerAgentError):
        await planner.create_plan("Plan Apex for Salesforce")


async def test_planner_rejects_invalid_dependency_graph() -> None:
    planner = planner_with(
        {
            "project": "Deployment",
            "objective": "Plan deployment",
            "tasks": [
                {
                    "id": "deploy",
                    "title": "Plan deployment",
                    "description": "Plan deployment validation.",
                    "agent": "deployment-agent",
                    "work_type": "deployment",
                    "priority": 1,
                    "dependencies": ["missing-task"],
                    "input": {},
                }
            ],
        }
    )

    with pytest.raises(PlannerAgentError):
        await planner.create_plan("Plan Salesforce deployment")


async def test_planner_accepts_uppercase_work_type_enum_names() -> None:
    planner = planner_with(
        {
            "project": "Form Validation",
            "objective": "Create Apex form validation and trigger",
            "summary": "Generate validation class and Contact trigger.",
            "missing_information": [],
            "tasks": [
                {
                    "id": "create-apex",
                    "title": "Create FormValidation Apex class",
                    "description": "Create an Apex class with name, email, and phone validation logic.",
                    "agent": "salesforce_engineer",
                    "work_type": "SALESFORCE_PROJECT",
                    "priority": 1,
                    "dependencies": [],
                    "input": {"object": "Contact"},
                    "deliverables": ["FormValidation.cls"],
                    "acceptance_criteria": ["Validation rules are implemented"],
                    "missing_information": [],
                },
                {
                    "id": "create-trigger",
                    "title": "Create Contact validation trigger",
                    "description": "Create a before insert and update trigger on Contact.",
                    "agent": "salesforce_engineer",
                    "work_type": "APEX",
                    "priority": 2,
                    "dependencies": ["create-apex"],
                    "input": {"object": "Contact"},
                    "deliverables": ["ContactFormValidationTrigger.trigger"],
                    "acceptance_criteria": ["Trigger calls FormValidation on save"],
                    "missing_information": [],
                },
            ],
        }
    )

    plan = await planner.create_plan(
        "Create an Apex class for form validation and a trigger in my sandbox org"
    )

    assert plan.tasks[0].work_type == SalesforceWorkType.SALESFORCE_PROJECT
    assert plan.tasks[1].work_type == SalesforceWorkType.APEX
