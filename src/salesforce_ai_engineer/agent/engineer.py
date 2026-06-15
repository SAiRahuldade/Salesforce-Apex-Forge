from __future__ import annotations
import json
import logging
from typing import Any, Dict
from openai import AsyncOpenAI
from salesforce_ai_engineer.tools.executor import ToolExecutor
from salesforce_ai_engineer.agent.models import ExecutionTask, TaskResult, TaskStatus

logger = logging.getLogger(__name__)

class SalesforceEngineerAgent:
    """
    Phase 9: Specialized agent for Salesforce development tasks.
    Handles Apex, Triggers, LWC, Flows, and Metadata with security-aware generation.
    """
    
    def __init__(
        self,
        client: AsyncOpenAI,
        tool_executor: ToolExecutor,
        model: str | None = None,
    ):
        self.client = client
        self.tool_executor = tool_executor
        self.model = model or "qwen2.5-coder:7b"

    async def execute(self, task: ExecutionTask) -> TaskResult:
        """Execute engineering tasks using LLM reasoning and the Tool Layer."""
        logger.info(f"Engineer executing task: {task.title}")
        
        system_prompt = (
            "You are an expert Salesforce AI Engineer. Generate production-ready Salesforce metadata.\n"
            "Follow best practices: bulkified triggers, handler classes, with sharing, no SOQL/DML in loops.\n"
            "Return ONLY valid JSON with this shape:\n"
            "{\n"
            '  "description": "summary of generated artifacts",\n'
            '  "artifacts": {\n'
            '    "FormValidation.cls": "public class FormValidation { ... }",\n'
            '    "FormValidation.cls-meta.xml": "<?xml version=\\"1.0\\" ...>",\n'
            '    "ContactFormValidationTrigger.trigger": "trigger ContactFormValidationTrigger on Contact ..."\n'
            "  }\n"
            "}\n"
            "Use exact Salesforce filenames as artifact keys (.cls, .trigger, and matching -meta.xml files)."
        )

        user_prompt = f"Objective: {task.description}\nInput Context: {json.dumps(task.input)}"
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            content = json.loads(response.choices[0].message.content)
            artifacts = content.get("artifacts", {})
            
            # Optional: Use Tool Layer to inspect environment if required by task input
            if task.input.get("check_existing"):
                # Example tool usage
                pass

            return TaskResult(
                task_id=task.id,
                success=True,
                output={
                    "artifacts": artifacts,
                    "summary": content.get("description", "Generation successful"),
                    "agent": "SalesforceEngineer"
                }
            )

        except Exception as e:
            logger.exception("Salesforce Engineer failed to generate code")
            return TaskResult(
                task_id=task.id,
                success=False,
                error=str(e)
            )

    async def run(self, task: Any) -> Any:
        """Legacy compatibility wrapper for Orchestrator/Engine."""
        if isinstance(task, ExecutionTask):
            result = await self.execute(task)
            return {"status": "success" if result.success else "failed", "output": result.output, "error": result.error}
        return {"status": "success", "message": f"Task {task.id} processed."}