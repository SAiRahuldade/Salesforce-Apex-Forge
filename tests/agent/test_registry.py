from __future__ import annotations

from salesforce_ai_engineer.agent.registry import AgentRegistry


class DummyAgent:
    async def execute(self, task):  # noqa: ANN001, ANN201
        return task


def test_register_aliases_resolve_all_names() -> None:
    registry = AgentRegistry()
    agent = DummyAgent()

    registry.register_aliases("deployment", agent, "deployment_agent")

    assert registry.resolve("deployment") is agent
    assert registry.resolve("DEPLOYMENT_AGENT") is agent
