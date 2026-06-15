"""Registry for executable task agents."""

from __future__ import annotations

from salesforce_ai_engineer.agent.contracts import TaskAgent


class AgentNotRegisteredError(KeyError):
    """Raised when no task agent is registered for a plan task."""


class AgentRegistry:
    """Maps plan agent names to executable agent implementations."""

    def __init__(self) -> None:
        self._agents: dict[str, TaskAgent] = {}

    def register(self, name: str, agent: TaskAgent) -> None:
        normalized = self._normalize(name)
        self._agents[normalized] = agent

    def register_aliases(self, name: str, agent: TaskAgent, *aliases: str) -> None:
        """Register an agent under its primary name and optional aliases."""

        self.register(name, agent)
        for alias in aliases:
            self.register(alias, agent)

    def resolve(self, name: str) -> TaskAgent:
        normalized = self._normalize(name)
        try:
            return self._agents[normalized]
        except KeyError as exc:
            raise AgentNotRegisteredError(f"No task agent registered for {name!r}") from exc

    def registered_names(self) -> list[str]:
        return sorted(self._agents)

    def _normalize(self, name: str) -> str:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("Agent name cannot be empty")
        return normalized

