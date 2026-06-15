"""Tool Layer Usage Examples

This module demonstrates how to use the Tool Layer for common scenarios.
"""

# ============================================================================
# Example 1: Basic Tool Invocation
# ============================================================================

async def example_basic_tool_usage():
    """Example: Basic tool execution from an agent."""
    
    from salesforce_ai_engineer.core.bootstrap import container
    from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus
    
    # Get the tool executor from DI container
    executor = container.resolve("tool_executor")
    
    # Create a request to execute a tool
    request = ToolRequest(
        workflow_id="wf-001",
        task_id="task-001",
        tool_name="json",
        input={
            "operation": "parse",
            "content": '{"user": "Alice", "role": "admin"}'
        },
        correlation_id="corr-001"
    )
    
    # Execute the tool
    response = await executor.execute(request)
    
    # Handle response
    if response.status == ToolStatus.SUCCESS:
        print(f"Parsed: {response.output}")
        print(f"Duration: {response.metrics['duration_seconds']}s")
    else:
        print(f"Error: {response.error_type} - {response.error}")


# ============================================================================
# Example 2: Salesforce CLI Operations
# ============================================================================

async def example_salesforce_operations():
    """Example: Using Salesforce CLI tool for org management."""
    
    from salesforce_ai_engineer.core.bootstrap import container
    from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus
    
    executor = container.resolve("tool_executor")
    
    # List available orgs
    list_request = ToolRequest(
        workflow_id="wf-sf-001",
        tool_name="sf",
        input={
            "operation": "org_list",
            "json_output": True
        }
    )
    
    response = await executor.execute(list_request)
    if response.status == ToolStatus.SUCCESS:
        orgs = response.output.get("result", [])
        print(f"Available orgs: {[org.get('username') for org in orgs]}")
    
    # Deploy metadata
    deploy_request = ToolRequest(
        workflow_id="wf-sf-001",
        tool_name="sf",
        input={
            "operation": "project_deploy",
            "target_org": "production",
            "flags": {
                "manifest": "package.xml",
                "wait": 30,
                "test_level": "RunSpecifiedTests"
            }
        }
    )
    
    response = await executor.execute(deploy_request)
    if response.status == ToolStatus.SUCCESS:
        result = response.output.get("result", {})
        print(f"Deployment status: {result.get('status')}")
    
    # Query data
    query_request = ToolRequest(
        workflow_id="wf-sf-001",
        tool_name="sf",
        input={
            "operation": "data_query",
            "target_org": "production",
            "flags": {
                "query": "SELECT Id, Name FROM Account LIMIT 10"
            }
        }
    )
    
    response = await executor.execute(query_request)
    if response.status == ToolStatus.SUCCESS:
        records = response.output.get("result", {}).get("records", [])
        print(f"Found {len(records)} accounts")


# ============================================================================
# Example 3: Filesystem Operations
# ============================================================================

async def example_filesystem_operations():
    """Example: Safe file system operations."""
    
    from salesforce_ai_engineer.core.bootstrap import container
    from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus
    
    executor = container.resolve("tool_executor")
    
    # Read a configuration file
    read_request = ToolRequest(
        workflow_id="wf-fs-001",
        tool_name="fs",
        input={
            "operation": "read",
            "path": "config/settings.yaml"
        }
    )
    
    response = await executor.execute(read_request)
    if response.status == ToolStatus.SUCCESS:
        content = response.output.get("content")
        print(f"Config:\n{content}")
    
    # Write a report file
    write_request = ToolRequest(
        workflow_id="wf-fs-001",
        tool_name="fs",
        input={
            "operation": "write",
            "path": "reports/execution_report.txt",
            "content": "Execution completed successfully",
            "create_dirs": True
        }
    )
    
    response = await executor.execute(write_request)
    if response.status == ToolStatus.SUCCESS:
        print("Report written successfully")
    
    # List directory contents
    list_request = ToolRequest(
        workflow_id="wf-fs-001",
        tool_name="fs",
        input={
            "operation": "list",
            "path": "src/",
            "recursive": True
        }
    )
    
    response = await executor.execute(list_request)
    if response.status == ToolStatus.SUCCESS:
        files = response.output.get("files", [])
        print(f"Found {len(files)} files")


# ============================================================================
# Example 4: Git Operations
# ============================================================================

async def example_git_operations():
    """Example: Version control operations."""
    
    from salesforce_ai_engineer.core.bootstrap import container
    from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus
    
    executor = container.resolve("tool_executor")
    
    # Clone a repository
    clone_request = ToolRequest(
        workflow_id="wf-git-001",
        tool_name="git",
        input={
            "args": ["clone", "https://github.com/my-org/my-repo.git", "repo"],
            "cwd": "/workspace"
        }
    )
    
    response = await executor.execute(clone_request)
    if response.status == ToolStatus.SUCCESS:
        print("Repository cloned successfully")
    
    # Commit and push changes
    commit_request = ToolRequest(
        workflow_id="wf-git-001",
        tool_name="git",
        input={
            "args": ["commit", "-m", "Update configuration"],
            "cwd": "/workspace/repo"
        }
    )
    
    response = await executor.execute(commit_request)
    
    push_request = ToolRequest(
        workflow_id="wf-git-001",
        tool_name="git",
        input={
            "args": ["push", "origin", "main"],
            "cwd": "/workspace/repo"
        }
    )
    
    response = await executor.execute(push_request)
    if response.status == ToolStatus.SUCCESS:
        print("Changes pushed successfully")


# ============================================================================
# Example 5: HTTP API Calls
# ============================================================================

async def example_http_operations():
    """Example: Making API requests."""
    
    from salesforce_ai_engineer.core.bootstrap import container
    from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus
    
    executor = container.resolve("tool_executor")
    
    # GET request
    get_request = ToolRequest(
        workflow_id="wf-api-001",
        tool_name="http",
        input={
            "method": "GET",
            "url": "https://api.github.com/repos/my-org/my-repo",
            "headers": {
                "Authorization": "token github-token",
                "Accept": "application/vnd.github.v3+json"
            }
        }
    )
    
    response = await executor.execute(get_request)
    if response.status == ToolStatus.SUCCESS:
        repo_info = response.output.get("body")
        print(f"Repository: {repo_info.get('name')}")
    
    # POST request
    post_request = ToolRequest(
        workflow_id="wf-api-001",
        tool_name="http",
        input={
            "method": "POST",
            "url": "https://api.example.com/events",
            "headers": {"Content-Type": "application/json"},
            "body": {
                "event_type": "deployment",
                "status": "completed",
                "duration_seconds": 123
            }
        }
    )
    
    response = await executor.execute(post_request)


# ============================================================================
# Example 6: Tool Discovery
# ============================================================================

async def example_tool_discovery():
    """Example: Discovering available tools dynamically."""
    
    from salesforce_ai_engineer.core.bootstrap import container
    
    registry = container.resolve("tool_registry")
    
    # List all available tools
    tool_names = registry.names()
    print(f"Available tools: {tool_names}")
    
    # Get schemas for all tools
    schemas = registry.all_schemas()
    for schema in schemas:
        print(f"\n{schema.name}: {schema.description}")
        print(f"  Input schema: {schema.input_schema}")
        print(f"  Example: {schema.input_example}")
    
    # Get specific tool schema
    git_schema = registry.schema_for("git")
    print(f"\nGit tool input requirements: {git_schema.input_schema}")


# ============================================================================
# Example 7: Error Handling and Retry
# ============================================================================

async def example_error_handling():
    """Example: Handling errors and retry scenarios."""
    
    from salesforce_ai_engineer.core.bootstrap import container
    from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus, ToolErrorType
    
    executor = container.resolve("tool_executor")
    
    # Request with custom timeout and retries
    request = ToolRequest(
        workflow_id="wf-err-001",
        tool_name="http",
        input={
            "method": "GET",
            "url": "https://unreliable-api.example.com/data",
            "retries": 3,  # Retry up to 3 times on transient errors
        },
        timeout_seconds=10  # Override default timeout
    )
    
    response = await executor.execute(request)
    
    if response.status == ToolStatus.SUCCESS:
        print(f"Success after {response.attempts} attempts")
    elif response.status == ToolStatus.TIMEOUT:
        print(f"Timeout error after {response.attempts} attempts")
    elif response.status == ToolStatus.FAILED:
        if response.error_type == ToolErrorType.VALIDATION:
            print(f"Validation error (not retryable): {response.error}")
        elif response.error_type == ToolErrorType.NETWORK:
            print(f"Network error after {response.attempts} retries")
        else:
            print(f"Error ({response.error_type}): {response.error}")


# ============================================================================
# Example 8: Shell Command Execution
# ============================================================================

async def example_shell_operations():
    """Example: Executing shell commands safely."""
    
    from salesforce_ai_engineer.core.bootstrap import container
    from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus
    
    executor = container.resolve("tool_executor")
    
    # Structured command (safer - no shell injection risk)
    cmd_request = ToolRequest(
        workflow_id="wf-cmd-001",
        tool_name="command",
        input={
            "command_name": "docker",
            "args": ["ps", "--format", "json"],
            "timeout": 30
        }
    )
    
    response = await executor.execute(cmd_request)
    if response.status == ToolStatus.SUCCESS:
        print(f"Docker containers:\n{response.output.get('stdout')}")
    
    # Shell command (use with caution)
    shell_request = ToolRequest(
        workflow_id="wf-shell-001",
        tool_name="shell",
        input={
            "command": "ps aux | grep python",
            "shell": "bash",
            "timeout": 10
        }
    )
    
    response = await executor.execute(shell_request)
    if response.status == ToolStatus.SUCCESS:
        print(f"Processes:\n{response.output.get('stdout')}")


# ============================================================================
# Example 9: Agent with Tool Integration
# ============================================================================

class ExampleAgent:
    """Example agent that uses the Tool Layer."""
    
    def __init__(self, executor):
        self.executor = executor
        self.workflow_id = "wf-agent-001"
    
    async def deploy_salesforce_changes(self, org_alias: str) -> bool:
        """Deploy Salesforce metadata to target org."""
        
        from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus
        
        request = ToolRequest(
            workflow_id=self.workflow_id,
            tool_name="sf",
            input={
                "operation": "project_deploy",
                "target_org": org_alias,
                "flags": {
                    "wait": 60,
                    "ignore_warnings": False
                }
            }
        )
        
        response = await self.executor.execute(request)
        return response.status == ToolStatus.SUCCESS
    
    async def validate_deployment(self) -> dict:
        """Validate deployment with tests."""
        
        from salesforce_ai_engineer.models.domain import ToolRequest
        
        request = ToolRequest(
            workflow_id=self.workflow_id,
            tool_name="http",
            input={
                "method": "GET",
                "url": "https://api.salesforce.com/deployment/status",
                "headers": {"Authorization": "Bearer token"}
            }
        )
        
        response = await self.executor.execute(request)
        return response.output if response.status.value == "success" else {}


# ============================================================================
# Example 10: Batch Tool Operations
# ============================================================================

async def example_batch_operations():
    """Example: Executing multiple tools in sequence."""
    
    from salesforce_ai_engineer.core.bootstrap import container
    from salesforce_ai_engineer.models.domain import ToolRequest, ToolStatus
    
    executor = container.resolve("tool_executor")
    
    # Workflow: Clone repo -> read config -> validate -> report
    
    # Step 1: Clone repository
    clone_request = ToolRequest(
        workflow_id="wf-batch-001",
        tool_name="git",
        input={
            "args": ["clone", "https://github.com/repo.git", "work"],
            "cwd": "/tmp"
        }
    )
    
    response = await executor.execute(clone_request)
    if response.status != ToolStatus.SUCCESS:
        print("Clone failed")
        return
    
    # Step 2: Read configuration
    config_request = ToolRequest(
        workflow_id="wf-batch-001",
        tool_name="fs",
        input={
            "operation": "read",
            "path": "/tmp/work/config.yaml"
        }
    )
    
    response = await executor.execute(config_request)
    if response.status != ToolStatus.SUCCESS:
        print("Config read failed")
        return
    
    config_content = response.output.get("content")
    
    # Step 3: Parse configuration
    parse_request = ToolRequest(
        workflow_id="wf-batch-001",
        tool_name="yaml",
        input={
            "operation": "parse",
            "content": config_content
        }
    )
    
    response = await executor.execute(parse_request)
    if response.status != ToolStatus.SUCCESS:
        print("Config parse failed")
        return
    
    config = response.output.get("data")
    
    # Step 4: Generate report
    report = f"Batch operation completed. Config: {config}"
    write_request = ToolRequest(
        workflow_id="wf-batch-001",
        tool_name="fs",
        input={
            "operation": "write",
            "path": "report.txt",
            "content": report
        }
    )
    
    response = await executor.execute(write_request)
    print("Batch operation completed successfully")


# ============================================================================
# Usage Instructions
# ============================================================================

if __name__ == "__main__":
    """
    To run these examples:
    
    1. Basic usage:
        python -c "import asyncio; from tool_examples import example_basic_tool_usage; asyncio.run(example_basic_tool_usage())"
    
    2. In your code:
        import asyncio
        from tool_examples import example_salesforce_operations
        asyncio.run(example_salesforce_operations())
    
    3. In an async context (FastAPI, etc.):
        from tool_examples import example_tool_discovery
        await example_tool_discovery()
    """
    
    print("Tool Layer Examples")
    print("===================")
    print("\nAvailable examples:")
    print("  - example_basic_tool_usage()")
    print("  - example_salesforce_operations()")
    print("  - example_filesystem_operations()")
    print("  - example_git_operations()")
    print("  - example_http_operations()")
    print("  - example_tool_discovery()")
    print("  - example_error_handling()")
    print("  - example_shell_operations()")
    print("  - example_batch_operations()")
    print("\nSee docstrings for details.")
