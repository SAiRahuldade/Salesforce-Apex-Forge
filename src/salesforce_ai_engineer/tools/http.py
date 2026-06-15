"""HTTP/REST request tool."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, HttpUrl

from salesforce_ai_engineer.models.domain import ToolRequest
from salesforce_ai_engineer.tools.base import BaseTool
from salesforce_ai_engineer.tools.errors import ToolNetworkError


class HttpInput(BaseModel):
    """Input model for outbound HTTP requests."""

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    json_body: Any | None = None
    text_body: str | None = None


class HttpTool(BaseTool):
    """Perform asynchronous HTTP/REST requests."""

    name = "http"
    description = "Execute HTTP requests with structured responses."
    input_model = HttpInput

    async def _run(self, payload: HttpInput, request: ToolRequest) -> dict[str, Any]:
        timeout = request.timeout_seconds or self.config.default_timeout_seconds
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    payload.method,
                    str(payload.url),
                    headers=payload.headers,
                    params=payload.query,
                    json=payload.json_body,
                    content=payload.text_body,
                )
                response.raise_for_status()
                return {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "text": response.text,
                    "json": self._maybe_json(response),
                }
        except httpx.HTTPError as exc:
            raise ToolNetworkError(str(exc)) from exc

    def _maybe_json(self, response: httpx.Response) -> Any | None:
        try:
            return response.json()
        except ValueError:
            return None

