from __future__ import annotations
import json
from typing import Any, Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from salesforce_ai_engineer.agent.models import ExecutionPlan, ExecutionTask

class PlannerAgentError(Exception):
    """Exception raised for errors in the planner agent."""
    pass

class PlanningRequest(BaseModel):
    """Model for a planning request."""
    request: str
    context: dict[str, Any] = Field(default_factory=dict)

class OllamaPlannerAgent:
    """Agent responsible for decomposing requests into execution plans using Ollama."""

    def __init__(self, client: AsyncOpenAI = None, model: str = None, config: Any = None):
        self.client = client
        self.model = model if model else (config.model if config else "llama3.1")

    async def create_plan(self, request: str) -> ExecutionPlan:
        """Generates a dynamic ExecutionPlan using the LLM based on user request."""
        system_prompt = (
            "You are a Salesforce Project Planner. Decompose the user request into a "
            "Directed Acyclic Graph (DAG) of tasks.\n"
            "Available Agents: 'salesforce_engineer', 'verifier', 'deployment'.\n"
            "Return ONLY a valid JSON object with this structure:\n"
            "{\n"
            '  "id": "plan_id",\n'
            '  "project": "project_name",\n'
            '  "objective": "overall_objective",\n'
            '  "summary": "brief_summary",\n'
            '  "missing_information": [],\n'
            '  "tasks": [\n'
            "    {\n"
            '      "id": "task_1",\n'
            '      "title": "Task Title",\n'
            '      "description": "Detailed task description",\n'
            '      "agent": "salesforce_engineer" | "verifier" | "deployment",\n'
            '      "work_type": "apex" | "lwc" | "flow" | "security" | "deployment" | '
            '"analysis" | "testing" | "documentation" | "metadata_generation" | "salesforce_project",\n'
            "Use lowercase snake_case values only (never SALESFORCE_PROJECT or APEX).\n"
            '      "priority": 3,\n'
            '      "dependencies": [],\n'
            '      "input": {},\n'
            '      "deliverables": [],\n'
            '      "acceptance_criteria": [],\n'
            '      "missing_information": []\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        if self.client is None:
            raise PlannerAgentError("No LLM client configured")

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request}
            ],
            response_format={"type": "json_object"}
        )

        plan_data = json.loads(response.choices[0].message.content)
        
        tasks = []
        plan_missing_info = list(plan_data.get("missing_information", []))
        
        for t_data in plan_data.get("tasks", []):
            try:
                tasks.append(ExecutionTask.model_validate(t_data))
            except Exception as e:
                raise PlannerAgentError(f"Invalid task definition: {e}") from e
        
        request_lower = request.lower()
        has_org_context = any(
            term in request_lower for term in ["sandbox", "production", "org", "environment", "dev org", "uat"]
        )
        if not has_org_context:
            plan_missing_info.append("Target Salesforce org or environment is not specified")
        
        try:
            return ExecutionPlan(
                id=plan_data.get("id", "dynamic_plan"),
                project=plan_data.get("project", "Unspecified Project"),
                objective=plan_data.get("objective", request),
                summary=plan_data.get("summary", ""),
                missing_information=plan_missing_info,
                tasks=tasks
            )
        except Exception as e:
            raise PlannerAgentError(f"Invalid plan structure: {e}") from e