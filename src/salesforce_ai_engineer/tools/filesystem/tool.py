"""Filesystem tool constrained to a configured root."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from salesforce_ai_engineer.models.domain import ToolRequest
from salesforce_ai_engineer.tools.base import BaseTool
from salesforce_ai_engineer.tools.errors import ToolPermissionError, ToolValidationError


class FilesystemInput(BaseModel):
    """Input model for filesystem operations."""

    operation: Literal["read_text", "write_text", "exists", "list", "mkdir"]
    path: str
    content: str | None = None
    pattern: str = "*"


class FilesystemTool(BaseTool):
    """Perform local filesystem operations inside a configured root directory."""

    name = "filesystem"
    description = "Read, write, list, and create files within a safe root."
    input_model = FilesystemInput

    def __init__(self, root: str | Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def _run(self, payload: FilesystemInput, request: ToolRequest) -> dict[str, Any]:
        path = self._resolve(payload.path)
        if payload.operation == "read_text":
            return {"path": str(path), "content": path.read_text(encoding="utf-8")}
        if payload.operation == "write_text":
            if payload.content is None:
                raise ToolValidationError("write_text requires content")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload.content, encoding="utf-8")
            return {"path": str(path), "bytes_written": len(payload.content.encode("utf-8"))}
        if payload.operation == "exists":
            return {"path": str(path), "exists": path.exists()}
        if payload.operation == "list":
            if not path.exists():
                return {"path": str(path), "files": []}
            files = sorted(str(item.relative_to(self.root)) for item in path.glob(payload.pattern))
            return {"path": str(path), "files": files}
        if payload.operation == "mkdir":
            path.mkdir(parents=True, exist_ok=True)
            return {"path": str(path), "created": True}
        raise ToolValidationError(f"Unsupported filesystem operation: {payload.operation}")

    def _resolve(self, path: str) -> Path:
        resolved = (self.root / path).resolve()
        if self.root not in (resolved, *resolved.parents):
            raise ToolPermissionError(f"Path escapes filesystem tool root: {path}")
        return resolved

