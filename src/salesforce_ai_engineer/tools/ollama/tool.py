"""Ollama tool wrapper."""

from __future__ import annotations

from typing import Any

from ollama import AsyncClient
from pydantic import BaseModel, Field

from salesforce_ai_engineer.config.settings import OllamaConfig
from salesforce_ai_engineer.models.domain import ToolRequest
from salesforce_ai_engineer.tools.base import BaseTool
from salesforce_ai_engineer.tools.errors import ToolNetworkError


class OllamaInput(BaseModel):
    """Input model for local Ollama chat completion."""

    messages: list[dict[str, str]]
    model: str | None = None
    format: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class OllamaTool(BaseTool):
    """Invoke a local Ollama model through the official async client."""

    name = "ollama"
    description = "Call local Ollama chat models."
    input_model = OllamaInput

    def __init__(self, config: OllamaConfig, client: AsyncClient | None = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.config = config
        self.client = client or AsyncClient(host=str(config.base_url))

    async def _run(self, payload: OllamaInput, request: ToolRequest) -> dict[str, Any]:
        try:
            response = await self.client.chat(
                model=payload.model or self.config.model,
                messages=payload.messages,
                format=payload.format,
                options=payload.options,
            )
            return {"response": response}
        except Exception as exc:
            raise ToolNetworkError(str(exc)) from exc

