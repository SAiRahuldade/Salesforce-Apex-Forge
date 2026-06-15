"""Salesforce CLI tool for executing sf commands.

This tool provides access to Salesforce CLI (sf) functionality including:
- Organization connection management
- Metadata deployment and retrieval
- Org information querying
- Apex execution
- Data operations

The tool wraps sf CLI commands and parses output into structured results.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Literal

from pydantic import BaseModel, Field

from salesforce_ai_engineer.models.domain import ToolRequest
from salesforce_ai_engineer.tools.base import BaseTool
from salesforce_ai_engineer.tools.errors import ToolExternalProcessError, ToolSerializationError, ToolValidationError


class SalesforceCliInput(BaseModel):
    """Input model for Salesforce CLI operations."""

    operation: Literal[
        "org_list",
        "org_info",
        "org_open",
        "org_create",
        "project_deploy",
        "project_retrieve",
        "apex_execute",
        "data_query",
        "data_upsert",
        "custom_command",
    ]
    """Type of Salesforce operation to perform"""

    target_org: str | None = Field(default=None)
    """Target organization username or alias"""

    flags: dict[str, Any] = Field(default_factory=dict)
    """Additional sf CLI flags (e.g., {'manifest': 'package.xml', 'wait': 10})"""

    json_output: bool = Field(default=True)
    """Request JSON output from sf CLI when possible"""

    command: str | None = Field(default=None)
    """Custom sf command for generic execution (e.g., 'apex run --file test.apex')"""

    timeout: int = Field(default=300, ge=1, le=3600)
    """Timeout for sf command execution in seconds"""


class SalesforceCliTool(BaseTool):
    """Execute Salesforce CLI commands with structured output.
    
    Supported operations:
    - org_list: List available orgs
    - org_info: Get org details
    - org_open: Open org in browser
    - org_create: Create scratch/demo org
    - project_deploy: Deploy metadata
    - project_retrieve: Retrieve metadata
    - apex_execute: Execute Apex code
    - data_query: Run SOQL query
    - data_upsert: Upsert records
    - custom_command: Execute arbitrary sf command
    
    Example:
        request = ToolRequest(
            tool_name="salesforce_cli",
            input={
                "operation": "org_list",
                "json_output": True
            }
        )
        response = await executor.execute(request)
    """

    name = "salesforce_cli"
    description = "Execute Salesforce CLI (sf) commands"
    input_model = SalesforceCliInput

    async def _run(self, payload: SalesforceCliInput, request: ToolRequest) -> dict[str, Any]:
        """Execute Salesforce CLI command and return structured result.
        
        Args:
            payload: Validated SalesforceCliInput
            request: Original ToolRequest for correlation
            
        Returns:
            Dictionary with command output and result metadata
            
        Raises:
            ToolExternalProcessError: If sf command fails
            ToolSerializationError: If output parsing fails
        """

        if payload.operation == "custom_command":
            if not payload.command:
                raise ToolValidationError("custom_command operation requires 'command' field")
            return await self._execute_custom(payload)

        command_map = {
            "org_list": self._org_list_command,
            "org_info": self._org_info_command,
            "org_open": self._org_open_command,
            "org_create": self._org_create_command,
            "project_deploy": self._project_deploy_command,
            "project_retrieve": self._project_retrieve_command,
            "apex_execute": self._apex_execute_command,
            "data_query": self._data_query_command,
            "data_upsert": self._data_upsert_command,
        }

        if payload.operation not in command_map:
            raise ToolValidationError(f"Unknown operation: {payload.operation}")

        command_builder = command_map[payload.operation]
        command = command_builder(payload)

        return await self._execute_command(command, payload)

    def _org_list_command(self, payload: SalesforceCliInput) -> list[str]:
        """Build 'sf org list' command."""

        cmd = ["sf", "org", "list"]
        if payload.json_output:
            cmd.append("--json")
        return cmd

    def _org_info_command(self, payload: SalesforceCliInput) -> list[str]:
        """Build 'sf org display' command."""

        if not payload.target_org:
            raise ToolValidationError("org_info requires target_org")

        cmd = ["sf", "org", "display", "--target-org", payload.target_org]
        if payload.json_output:
            cmd.append("--json")
        return cmd

    def _org_open_command(self, payload: SalesforceCliInput) -> list[str]:
        """Build 'sf org open' command."""

        if not payload.target_org:
            raise ToolValidationError("org_open requires target_org")

        cmd = ["sf", "org", "open", "--target-org", payload.target_org]
        for key, value in payload.flags.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.extend([f"--{key}", str(value)])
        return cmd

    def _org_create_command(self, payload: SalesforceCliInput) -> list[str]:
        """Build 'sf org create' command."""

        org_type = payload.flags.get("type", "scratch")
        cmd = ["sf", "org", "create", org_type]

        for key, value in payload.flags.items():
            if key == "type":
                continue
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.extend([f"--{key}", str(value)])

        if payload.json_output:
            cmd.append("--json")
        return cmd

    def _project_deploy_command(self, payload: SalesforceCliInput) -> list[str]:
        """Build 'sf project deploy' command."""

        if not payload.target_org:
            raise ToolValidationError("project_deploy requires target_org")

        cmd = ["sf", "project", "deploy", "start", "--target-org", payload.target_org]

        for key, value in payload.flags.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.extend([f"--{key}", str(value)])

        if payload.json_output:
            cmd.append("--json")
        return cmd

    def _project_retrieve_command(self, payload: SalesforceCliInput) -> list[str]:
        """Build 'sf project retrieve' command."""

        if not payload.target_org:
            raise ToolValidationError("project_retrieve requires target_org")

        cmd = ["sf", "project", "retrieve", "start", "--target-org", payload.target_org]

        for key, value in payload.flags.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.extend([f"--{key}", str(value)])

        if payload.json_output:
            cmd.append("--json")
        return cmd

    def _apex_execute_command(self, payload: SalesforceCliInput) -> list[str]:
        """Build 'sf apex run' command."""

        if not payload.target_org:
            raise ToolValidationError("apex_execute requires target_org")

        cmd = ["sf", "apex", "run", "--target-org", payload.target_org]

        for key, value in payload.flags.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.extend([f"--{key}", str(value)])

        if payload.json_output:
            cmd.append("--json")
        return cmd

    def _data_query_command(self, payload: SalesforceCliInput) -> list[str]:
        """Build 'sf data query' command."""

        if not payload.target_org:
            raise ToolValidationError("data_query requires target_org")

        query = payload.flags.get("query")
        if not query:
            raise ToolValidationError("data_query requires 'query' in flags")

        cmd = ["sf", "data", "query", "--query", query, "--target-org", payload.target_org]

        for key, value in payload.flags.items():
            if key == "query":
                continue
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.extend([f"--{key}", str(value)])

        if payload.json_output:
            cmd.append("--json")
        return cmd

    def _data_upsert_command(self, payload: SalesforceCliInput) -> list[str]:
        """Build 'sf data upsert' command."""

        if not payload.target_org:
            raise ToolValidationError("data_upsert requires target_org")

        required = ["sobject", "values_file", "external_id_field"]
        for field in required:
            if field not in payload.flags:
                raise ToolValidationError(f"data_upsert requires '{field}' in flags")

        cmd = [
            "sf",
            "data",
            "upsert",
            "--sobject",
            payload.flags["sobject"],
            "--file",
            payload.flags["values_file"],
            "--external-id",
            payload.flags["external_id_field"],
            "--target-org",
            payload.target_org,
        ]

        for key, value in payload.flags.items():
            if key in ("sobject", "values_file", "external_id_field"):
                continue
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            else:
                cmd.extend([f"--{key}", str(value)])

        if payload.json_output:
            cmd.append("--json")
        return cmd

    async def _execute_custom(self, payload: SalesforceCliInput) -> dict[str, Any]:
        """Execute custom sf command."""

        parts = payload.command.split()
        cmd = ["sf"] + parts

        if payload.json_output and "--json" not in cmd:
            cmd.append("--json")

        return await self._execute_command(cmd, payload)

    async def _execute_command(self, cmd: list[str], payload: SalesforceCliInput) -> dict[str, Any]:
        """Execute sf command and parse output.
        
        Args:
            cmd: Command and arguments list
            payload: Input with timeout and options
            
        Returns:
            Parsed command output
            
        Raises:
            ToolExternalProcessError: If command fails
            ToolSerializationError: If output parsing fails
        """

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=payload.timeout,
                shell=os.name == 'nt',
            )

            if result.returncode != 0:
                raise ToolExternalProcessError(
                    f"Salesforce CLI command failed: {result.stderr or result.stdout}"
                )

            # Parse JSON output if available
            if payload.json_output and result.stdout.strip():
                try:
                    output = json.loads(result.stdout)
                    return {
                        "success": True,
                        "status": "completed",
                        "result": output,
                        "command": " ".join(cmd),
                    }
                except json.JSONDecodeError as exc:
                    raise ToolSerializationError(f"Failed to parse JSON output: {exc}") from exc

            return {
                "success": True,
                "status": "completed",
                "result": result.stdout,
                "command": " ".join(cmd),
            }

        except subprocess.TimeoutExpired as exc:
            raise ToolExternalProcessError(
                f"Salesforce CLI command timed out after {payload.timeout} seconds"
            ) from exc
        except Exception as exc:
            raise ToolExternalProcessError(f"Salesforce CLI error: {exc}") from exc
