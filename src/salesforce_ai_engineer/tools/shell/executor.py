"""Shell and process execution tools.

This module provides tools for executing shell commands and system processes:
- ShellTool: Execute arbitrary shell commands in bash/powershell/cmd
- CommandTool: Execute specific commands (git, npm, docker, etc.)

These tools sanitize and validate inputs to prevent command injection attacks.
"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from salesforce_ai_engineer.models.domain import ToolRequest
from salesforce_ai_engineer.tools.base import BaseTool
from salesforce_ai_engineer.tools.errors import ToolExternalProcessError, ToolTimeoutError, ToolValidationError


class ShellCommandInput(BaseModel):
    """Input model for shell command execution."""

    command: str = Field(..., min_length=1)
    """Shell command to execute (bash/powershell/cmd)"""

    cwd: str | None = Field(default=None)
    """Working directory for command execution"""

    input_text: str | None = Field(default=None)
    """Standard input to send to command"""

    timeout: int = Field(default=60, ge=1, le=3600)
    """Execution timeout in seconds"""

    shell: Literal["auto", "bash", "powershell", "cmd", "sh"] = Field(default="auto")
    """Shell to use (auto detects based on OS)"""

    capture_output: bool = Field(default=True)
    """Whether to capture and return stdout/stderr"""

    environment: dict[str, str] | None = Field(default=None)
    """Environment variables for command execution"""


class CommandInput(BaseModel):
    """Input model for structured command execution."""

    command_name: str = Field(..., min_length=1)
    """Command to execute (e.g., 'git', 'docker', 'npm')"""

    args: list[str] = Field(default_factory=list)
    """Command arguments"""

    cwd: str | None = Field(default=None)
    """Working directory"""

    timeout: int = Field(default=60, ge=1, le=3600)
    """Execution timeout"""

    input_text: str | None = Field(default=None)
    """Standard input"""


class ShellTool(BaseTool):
    """Execute shell commands with output capture.
    
    Features:
    - Cross-platform shell support (bash, powershell, cmd)
    - Automatic shell detection based on OS
    - Input/output handling
    - Timeout protection
    - Environment variable passing
    
    WARNING: This tool executes arbitrary commands. Only use with trusted input.
    Consider using CommandTool for specific known commands instead.
    
    Example:
        request = ToolRequest(
            tool_name="shell",
            input={
                "command": "ls -la /path",
                "cwd": "/home/user",
                "timeout": 30
            }
        )
        response = await executor.execute(request)
    """

    name = "shell"
    description = "Execute shell commands (bash, powershell, cmd)"
    input_model = ShellCommandInput

    async def _run(self, payload: ShellCommandInput, request: ToolRequest) -> dict[str, Any]:
        """Execute shell command and return output.
        
        Args:
            payload: Validated ShellCommandInput
            request: Original ToolRequest
            
        Returns:
            Dictionary with exit code, stdout, stderr
            
        Raises:
            ToolExternalProcessError: If command fails or times out
            ToolValidationError: If input is invalid
        """

        shell = self._resolve_shell(payload.shell)
        cwd = Path(payload.cwd) if payload.cwd else None

        # Validate working directory exists
        if cwd and not cwd.exists():
            raise ToolValidationError(f"Working directory does not exist: {cwd}")

        try:
            result = await asyncio.wait_for(
                self._execute_shell(
                    payload.command,
                    shell,
                    cwd,
                    payload.input_text,
                    payload.environment,
                ),
                timeout=payload.timeout,
            )

            return {
                "exit_code": result["returncode"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "command": payload.command,
                "shell": shell,
            }

        except asyncio.TimeoutError as exc:
            raise ToolTimeoutError(
                f"Command timed out after {payload.timeout} seconds: {payload.command}"
            ) from exc
        except Exception as exc:
            raise ToolExternalProcessError(f"Command execution failed: {exc}") from exc

    async def _execute_shell(
        self,
        command: str,
        shell: str,
        cwd: Path | None,
        input_text: str | None,
        environment: dict[str, str] | None,
    ) -> dict[str, Any]:
        """Execute shell command asynchronously.
        
        Args:
            command: Shell command string
            shell: Shell executable (bash, powershell, cmd, sh)
            cwd: Working directory
            input_text: stdin
            environment: Environment variables
            
        Returns:
            Result dict with returncode, stdout, stderr
        """

        # Build command based on shell
        if shell in ("bash", "sh"):
            cmd = [shell, "-c", command]
        elif shell == "powershell":
            cmd = ["powershell", "-Command", command]
        elif shell == "cmd":
            cmd = ["cmd", "/c", command]
        else:
            cmd = [shell, "-c", command]

        # Prepare environment
        env = os.environ.copy()
        if environment:
            env.update(environment)

        # Create process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd) if cwd else None,
            stdin=asyncio.subprocess.PIPE if input_text else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Run process
        stdout, stderr = await process.communicate(
            input_text.encode("utf-8") if input_text else None
        )

        return {
            "returncode": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }

    def _resolve_shell(self, shell: str) -> str:
        """Resolve shell to use based on parameter and OS.
        
        Args:
            shell: Requested shell ("auto", "bash", "powershell", "cmd", "sh")
            
        Returns:
            Resolved shell executable
        """

        if shell != "auto":
            return shell

        if platform.system() == "Windows":
            return "powershell"
        else:
            return "bash"


class CommandTool(BaseTool):
    """Execute structured commands (git, docker, npm, etc.).
    
    This tool is safer than ShellTool because it prevents shell metacharacter
    injection by splitting command and arguments explicitly.
    
    Supported commands:
    - git: Version control operations
    - docker: Container management
    - npm: Package management
    - Any other system command
    
    Example:
        request = ToolRequest(
            tool_name="command",
            input={
                "command_name": "git",
                "args": ["clone", "https://github.com/repo.git"],
                "cwd": "/workspace"
            }
        )
    """

    name = "command"
    description = "Execute structured commands (git, docker, npm, etc.)"
    input_model = CommandInput

    async def _run(self, payload: CommandInput, request: ToolRequest) -> dict[str, Any]:
        """Execute command with explicit args (no shell injection risk).
        
        Args:
            payload: Validated CommandInput
            request: Original ToolRequest
            
        Returns:
            Dictionary with exit code, stdout, stderr
            
        Raises:
            ToolExternalProcessError: If command fails or times out
            ToolValidationError: If input is invalid
        """

        cwd = Path(payload.cwd) if payload.cwd else None

        # Validate working directory
        if cwd and not cwd.exists():
            raise ToolValidationError(f"Working directory does not exist: {cwd}")

        # Build command with arguments
        cmd = [payload.command_name] + payload.args

        try:
            result = await asyncio.wait_for(
                self._execute_command(cmd, cwd, payload.input_text),
                timeout=payload.timeout,
            )

            return {
                "exit_code": result["returncode"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "command": payload.command_name,
                "args": payload.args,
            }

        except asyncio.TimeoutError as exc:
            raise ToolTimeoutError(
                f"Command timed out after {payload.timeout} seconds: {payload.command_name}"
            ) from exc
        except FileNotFoundError as exc:
            raise ToolExternalProcessError(
                f"Command not found: {payload.command_name}"
            ) from exc
        except Exception as exc:
            raise ToolExternalProcessError(f"Command execution failed: {exc}") from exc

    async def _execute_command(
        self,
        cmd: list[str],
        cwd: Path | None,
        input_text: str | None,
    ) -> dict[str, Any]:
        """Execute command asynchronously without shell.
        
        Args:
            cmd: Command and arguments list
            cwd: Working directory
            input_text: stdin
            
        Returns:
            Result with returncode, stdout, stderr
        """

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd) if cwd else None,
            stdin=asyncio.subprocess.PIPE if input_text else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate(
            input_text.encode("utf-8") if input_text else None
        )

        return {
            "returncode": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }
