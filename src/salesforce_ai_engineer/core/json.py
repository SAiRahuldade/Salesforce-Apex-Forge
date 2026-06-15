"""JSON serialization helpers."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel

_MISSING = object()


class EnhancedJSONEncoder(json.JSONEncoder):
    """JSON encoder aware of common application value objects."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")
        if isinstance(obj, datetime | date):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, set):
            return sorted(obj)
        return super().default(obj)


def dumps_json(value: Any, *, pretty: bool = False) -> str:
    return json.dumps(
        value,
        cls=EnhancedJSONEncoder,
        ensure_ascii=False,
        indent=2 if pretty else None,
        sort_keys=pretty,
    )


def loads_json(value: str | bytes) -> Any:
    return json.loads(value)


def read_json(path: str | Path, default: Any = _MISSING) -> Any:
    json_path = Path(path)
    if not json_path.exists():
        if default is not _MISSING:
            return default
        raise FileNotFoundError(json_path)
    return loads_json(json_path.read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any, *, pretty: bool = True) -> None:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(dumps_json(value, pretty=pretty), encoding="utf-8")
