"""Command-line tool wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from salesforce_ai_engineer.models.domain import ToolRequest
from salesforce_ai_engineer.tools.base import BaseTool
from salesforce_ai_engineer.tools.errors import ToolValidationError
from salesforce_ai_engineer.tools.process import run_process


class CommandInput(BaseModel):
    """Input for command tools that execute an argv list."""

    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    stdin: str | None = None


class ShellCommandInput(CommandInput):
    """Input for shell command execution without invoking a shell interpreter."""

    command: list[str]


class ShellCommandTool(BaseTool):
    """Execute an explicit command argv list through asyncio subprocesses."""

    name = "shell"
    description = "Execute a local command without shell expansion."
    input_model = ShellCommandInput

    async def _run(self, payload: ShellCommandInput, request: ToolRequest) -> dict[str, Any]:
        if not payload.command:
            raise ToolValidationError("Shell command must not be empty")
        return await run_process(
            payload.command,
            cwd=Path(payload.cwd).resolve() if payload.cwd else None,
            input_text=payload.stdin,
        )


class GitTool(BaseTool):
    """Run Git commands through a constrained argv interface."""

    name = "git"
    description = "Execute git commands using argv input."
    input_model = CommandInput

    async def _run(self, payload: CommandInput, request: ToolRequest) -> dict[str, Any]:
        return await run_process(
            ["git", *payload.args],
            cwd=Path(payload.cwd).resolve() if payload.cwd else None,
            input_text=payload.stdin,
        )


class SalesforceCliTool(BaseTool):
    """Run Salesforce CLI commands through a constrained argv interface."""

    name = "salesforce_cli"
    description = "Execute Salesforce CLI commands using the local sf executable."
    input_model = CommandInput

    async def _run(self, payload: CommandInput, request: ToolRequest) -> dict[str, Any]:
        executable = request.input.get("executable", "sf")
        if executable not in {"sf", "sfdx"}:
            raise ToolValidationError("Salesforce CLI executable must be 'sf' or 'sfdx'")
        return await run_process(
            [executable, *payload.args],
            cwd=Path(payload.cwd).resolve() if payload.cwd else None,
            input_text=payload.stdin,
        )

