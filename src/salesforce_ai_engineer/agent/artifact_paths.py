"""Map generated artifact filenames to Salesforce DX source paths."""

from __future__ import annotations

import json
from typing import Any

DEFAULT_APEX_CLASS_META = """<?xml version="1.0" encoding="UTF-8"?>
<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>58.0</apiVersion>
    <status>Active</status>
</ApexClass>
"""

DEFAULT_APEX_TRIGGER_META = """<?xml version="1.0" encoding="UTF-8"?>
<ApexTrigger xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>58.0</apiVersion>
    <status>Active</status>
</ApexTrigger>
"""


def resolve_salesforce_path(filename: str) -> str:
    """Return a project-relative path under force-app for a Salesforce artifact."""

    normalized = filename.replace("\\", "/").strip()
    basename = normalized.split("/")[-1]

    if basename.endswith(".cls-meta.xml") or (
        basename.endswith(".cls") and not basename.endswith("-meta.xml")
    ):
        return f"force-app/main/default/classes/{basename}"

    if basename.endswith(".trigger-meta.xml") or (
        basename.endswith(".trigger") and not basename.endswith("-meta.xml")
    ):
        return f"force-app/main/default/triggers/{basename}"

    if basename.endswith(".flow-meta.xml"):
        return f"force-app/main/default/flows/{basename}"

    if basename.endswith(".object-meta.xml"):
        return f"force-app/main/default/objects/{basename}"

    if "/" in normalized and "lwc" in normalized.lower():
        return f"force-app/main/default/{normalized.lstrip('/')}"

    if basename.endswith((".js", ".html", ".css", ".js-meta.xml")):
        component = basename.split(".")[0]
        return f"force-app/main/default/lwc/{component}/{basename}"

    return f"force-app/main/default/{basename}"


def iter_artifact_files(artifacts: dict[str, Any]) -> list[tuple[str, str]]:
    """Normalize planner/engineer artifact payloads into (filename, content) pairs."""

    files: list[tuple[str, str]] = []
    for key, value in artifacts.items():
        if isinstance(value, str):
            files.append((key, value))
            continue
        if not isinstance(value, dict):
            continue

        content = value.get("code") or value.get("xml") or value.get("content")
        if content is None and value.get("definition") is not None:
            content = json.dumps(value["definition"], indent=2)
        if content is None:
            continue

        filename = (
            value.get("filename")
            or value.get("name")
            or key
        )
        artifact_type = str(value.get("type", "")).lower()
        if artifact_type == "apex" and not str(filename).endswith(".cls"):
            filename = f"{filename}.cls"
        elif artifact_type == "trigger" and not str(filename).endswith(".trigger"):
            filename = f"{filename}.trigger"

        files.append((str(filename), str(content)))

    return files


def ensure_meta_files(files: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Add default -meta.xml files for Apex classes and triggers when missing."""

    present = {name for name, _ in files}
    expanded = list(files)

    for name, _content in files:
        if name.endswith(".cls") and not name.endswith("-meta.xml"):
            meta_name = f"{name}-meta.xml"
            if meta_name not in present:
                expanded.append((meta_name, DEFAULT_APEX_CLASS_META))
                present.add(meta_name)
        elif name.endswith(".trigger") and not name.endswith("-meta.xml"):
            meta_name = f"{name}-meta.xml"
            if meta_name not in present:
                expanded.append((meta_name, DEFAULT_APEX_TRIGGER_META))
                present.add(meta_name)

    return expanded
