"""SQLite tool wrapper."""

from __future__ import annotations

from typing import Any, Literal

import aiosqlite
from pydantic import BaseModel, Field

from salesforce_ai_engineer.models.domain import ToolRequest
from salesforce_ai_engineer.tools.base import BaseTool
from salesforce_ai_engineer.tools.errors import ToolDatabaseError, ToolValidationError


class SQLiteInput(BaseModel):
    """Input model for SQLite statements."""

    database_path: str
    statement: str
    parameters: list[Any] | dict[str, Any] = Field(default_factory=list)
    operation: Literal["query", "execute"] = "query"


class SQLiteTool(BaseTool):
    """Execute parameterized SQLite queries or statements."""

    name = "sqlite"
    description = "Run SQLite queries and statements."
    input_model = SQLiteInput

    async def _run(self, payload: SQLiteInput, request: ToolRequest) -> dict[str, Any]:
        statement = payload.statement.strip()
        if not statement:
            raise ToolValidationError("SQLite statement must not be empty")
        try:
            async with aiosqlite.connect(payload.database_path) as connection:
                connection.row_factory = aiosqlite.Row
                cursor = await connection.execute(statement, payload.parameters)
                if payload.operation == "query":
                    rows = await cursor.fetchall()
                    return {"rows": [dict(row) for row in rows], "row_count": len(rows)}
                await connection.commit()
                return {"row_count": cursor.rowcount, "lastrowid": cursor.lastrowid}
        except Exception as exc:
            raise ToolDatabaseError(str(exc)) from exc

