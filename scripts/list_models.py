"""List every class defined under src/salesforce_ai_engineer.

Used for a one-off inventory. Not part of the runtime.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path("src/salesforce_ai_engineer")


def classify(node: ast.ClassDef, src: str) -> str:
    base_names: list[str] = []
    for b in node.bases:
        if isinstance(b, ast.Name):
            base_names.append(b.id)
        elif isinstance(b, ast.Attribute):
            base_names.append(b.attr)
    joined = ",".join(base_names)
    if "BaseModel" in joined:
        return "pydantic"
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "dataclass":
            return "dataclass"
        if isinstance(dec, ast.Attribute) and dec.attr == "dataclass":
            return "dataclass"
    return "class"


def main() -> int:
    files = sorted(ROOT.rglob("*.py"))
    found_any = False
    for path in files:
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            print(f"!! SYNTAX ERROR: {path}: {exc}")
            continue
        classes = [
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
        ]
        if not classes:
            continue
        found_any = True
        rel = path.as_posix()
        print(f"\n=== {rel} ===")
        for node in classes:
            kind = classify(node, source)
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(b.attr)
            bases_s = f"({', '.join(bases)})" if bases else ""
            print(f"  - [{kind}] {node.name}{bases_s}")
    if not found_any:
        print("(no classes found)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())