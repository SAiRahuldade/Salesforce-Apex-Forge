"""Async external process execution used by command-line tools."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from salesforce_ai_engineer.tools.errors import ExternalProcessError


async def run_process(
    command: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run a subprocess without invoking a shell."""

    # Resolve executable path (crucial for Windows .cmd/.bat files)
    executable = command[0]
    resolved_path = shutil.which(executable)
    if not resolved_path:
        raise ExternalProcessError(f"Executable '{executable}' not found in PATH.")
    
    command[0] = resolved_path

    # Ensure we pass the current environment, which is critical on Windows
    # for resolving system libraries and command interpreters.
    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd) if cwd is not None else None,
        env=process_env,
        stdin=asyncio.subprocess.PIPE if input_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate(
        input_text.encode("utf-8") if input_text is not None else None
    )
    result = {
        "command": command,
        "cwd": str(cwd) if cwd is not None else None,
        "return_code": process.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }
    if process.returncode != 0:
        raise ExternalProcessError(
            f"Command failed with exit code {process.returncode}: {' '.join(command)}"
        )
    return result
