"""JSON, YAML, and XML structured data tools."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from salesforce_ai_engineer.models.domain import ToolRequest
from salesforce_ai_engineer.tools.base import BaseTool
from salesforce_ai_engineer.tools.errors import ToolSerializationError, ToolValidationError


class StructuredDataInput(BaseModel):
    """Input model for structured data parsing and formatting."""

    operation: Literal["parse", "format"]
    content: str | None = None
    data: Any | None = None


class JSONTool(BaseTool):
    """Parse and format JSON documents."""

    name = "json"
    description = "Parse and format JSON."
    input_model = StructuredDataInput

    async def _run(self, payload: StructuredDataInput, request: ToolRequest) -> dict[str, Any]:
        try:
            if payload.operation == "parse":
                if payload.content is None:
                    raise ToolValidationError("JSON parse requires content")
                return {"data": json.loads(payload.content)}
            if payload.data is None:
                raise ToolValidationError("JSON format requires data")
            return {"content": json.dumps(payload.data, ensure_ascii=False, indent=2, sort_keys=True)}
        except json.JSONDecodeError as exc:
            raise ToolSerializationError(str(exc)) from exc


class YAMLTool(BaseTool):
    """Parse and format YAML documents."""

    name = "yaml"
    description = "Parse and format YAML."
    input_model = StructuredDataInput

    async def _run(self, payload: StructuredDataInput, request: ToolRequest) -> dict[str, Any]:
        try:
            if payload.operation == "parse":
                if payload.content is None:
                    raise ToolValidationError("YAML parse requires content")
                return {"data": yaml.safe_load(payload.content)}
            if payload.data is None:
                raise ToolValidationError("YAML format requires data")
            return {"content": yaml.safe_dump(payload.data, sort_keys=True, allow_unicode=True)}
        except yaml.YAMLError as exc:
            raise ToolSerializationError(str(exc)) from exc


class XMLTool(BaseTool):
    """Parse and format simple XML documents."""

    name = "xml"
    description = "Parse XML into dictionaries and format dictionaries as XML."
    input_model = StructuredDataInput

    async def _run(self, payload: StructuredDataInput, request: ToolRequest) -> dict[str, Any]:
        try:
            if payload.operation == "parse":
                if payload.content is None:
                    raise ToolValidationError("XML parse requires content")
                root = ET.fromstring(payload.content)
                return {"data": self._element_to_dict(root)}
            if not isinstance(payload.data, dict) or len(payload.data) != 1:
                raise ToolValidationError("XML format requires a single-root dictionary")
            root_name, value = next(iter(payload.data.items()))
            root = self._dict_to_element(root_name, value)
            return {"content": ET.tostring(root, encoding="unicode")}
        except ET.ParseError as exc:
            raise ToolSerializationError(str(exc)) from exc

    def _element_to_dict(self, element: ET.Element) -> dict[str, Any]:
        children = list(element)
        value: dict[str, Any] = {
            "tag": element.tag,
            "attributes": dict(element.attrib),
            "text": (element.text or "").strip(),
            "children": [self._element_to_dict(child) for child in children],
        }
        return value

    def _dict_to_element(self, name: str, value: Any) -> ET.Element:
        element = ET.Element(name)
        if isinstance(value, dict):
            attributes = value.get("attributes", {})
            if isinstance(attributes, dict):
                element.attrib.update({str(key): str(item) for key, item in attributes.items()})
            text = value.get("text")
            if text is not None:
                element.text = str(text)
            children = value.get("children", {})
            if isinstance(children, dict):
                for child_name, child_value in children.items():
                    element.append(self._dict_to_element(str(child_name), child_value))
            elif isinstance(children, list):
                for child in children:
                    if not isinstance(child, dict) or len(child) != 1:
                        raise ToolValidationError("XML children list entries must be single-root dictionaries")
                    child_name, child_value = next(iter(child.items()))
                    element.append(self._dict_to_element(str(child_name), child_value))
        else:
            element.text = str(value)
        return element

