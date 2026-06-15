"""Local filesystem management utilities."""

from __future__ import annotations

from pathlib import Path

from salesforce_ai_engineer.core.json import read_json, write_json


class FileManager:
    """Constrained file operations rooted at a workspace path."""

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, path: str | Path) -> Path:
        resolved = (self.root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if self.root not in (resolved, *resolved.parents):
            raise ValueError(f"Path escapes file manager root: {path}")
        return resolved

    def exists(self, path: str | Path) -> bool:
        return self.resolve(path).exists()

    def read_text(self, path: str | Path) -> str:
        return self.resolve(path).read_text(encoding="utf-8")

    def write_text(self, path: str | Path, content: str) -> Path:
        resolved = self.resolve(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return resolved

    def read_json(self, path: str | Path, default: object | None = None) -> object:
        return read_json(self.resolve(path), default=default)

    def write_json(self, path: str | Path, value: object) -> Path:
        resolved = self.resolve(path)
        write_json(resolved, value)
        return resolved

    def list_files(self, path: str | Path = ".", pattern: str = "*") -> list[Path]:
        directory = self.resolve(path)
        return sorted(item for item in directory.glob(pattern) if item.is_file())

    def ensure_dir(self, path: str | Path) -> Path:
        resolved = self.resolve(path)
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

