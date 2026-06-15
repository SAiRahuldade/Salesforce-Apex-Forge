from __future__ import annotations
import json
import logging
from typing import Any
from openai import AsyncOpenAI
from salesforce_ai_engineer.agent.models import ExecutionTask, RecoveryDecision, RecoveryAction

logger = logging.getLogger(__name__)

class RuleBasedRecoveryAgent:
    """Standard recovery agent that uses predefined rules for transitions."""
    async def recover(self, task: ExecutionTask, error: str) -> RecoveryDecision:
        if task.attempts >= 3:
            return RecoveryDecision(action=RecoveryAction.ESCALATE, reason="Max attempts")
        return RecoveryDecision(action=RecoveryAction.RETRY, reason="Rule-based retry")

class OllamaRecoveryAgent:
    """
    Phase 11: Responsible for recovering from failed tasks using LLM reasoning.
    Diagnoses failures and suggests retry strategies.
    """

    def __init__(self, client: AsyncOpenAI, model: str):
        self.client = client
        self.model = model

    async def recover(self, task: ExecutionTask, error: str) -> RecoveryDecision:
        """
        Diagnose failure and decide on a recovery path.
        Records successful strategies into the Memory Agent (via Orchestrator callback).
        """
        logger.info(f"Recovery agent diagnosing failure for task {task.id}: {error}")

        system_prompt = (
            "You are a DevOps and Salesforce System Recovery Specialist. "
            "Analyze the following task failure and determine the best recovery strategy.\n"
            "Strategies:\n"
            "- RETRY: Use when the error is transient or requires slight prompt adjustment.\n"
            "- ESCALATE: Use for authentication issues, security violations, or repeated failures.\n\n"
            "Return JSON: {'action': 'RETRY'|'ESCALATE', 'reason': str, 'updated_input': dict|None}"
        )

        user_prompt = (
            f"Task: {task.title}\n"
            f"Attempts: {task.attempts}\n"
            f"Error: {error}\n"
            f"Previous Input: {json.dumps(task.input)}"
        )

        try:
            # Escalation policy for too many retries
            if task.attempts >= 3:
                return RecoveryDecision(
                    action=RecoveryAction.ESCALATE,
                    reason=f"Max retries reached. Original error: {error}"
                )

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )

            decision_data = json.loads(response.choices[0].message.content)
            action_str = decision_data.get("action", "ESCALATE")
            
            return RecoveryDecision(
                action=RecoveryAction.RETRY if action_str == "RETRY" else RecoveryAction.ESCALATE,
                reason=decision_data.get("reason", "Unknown recovery diagnosis"),
                updated_input=decision_data.get("updated_input")
            )

        except Exception as e:
            logger.exception("Recovery diagnosis failed")
            return RecoveryDecision(
                action=RecoveryAction.ESCALATE,
                reason=f"Recovery agent encountered an error: {e}"
            )