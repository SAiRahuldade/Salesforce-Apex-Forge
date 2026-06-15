"""AI Agent with full tool-calling capabilities and project integration."""

import sys
import argparse
import json
import re
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
from .client import NVIDIANIMClient
from .prompts import format_user_message, format_assistant_message
from .tools import AgentTools


def get_project_structure_summary(workspace_path: str) -> str:
    """Analyze and summarize project structure."""
    summary = []
    
    try:
        # Check for key directories
        key_dirs = {
            'salesforce_ai_engineer': 'Main Salesforce AI agent platform',
            'nvidia-nim-chat': 'NVIDIA NIM chatbot interface',
            'tests': 'Test suite',
            'src/salesforce_ai_engineer/tools': 'Tool layer (10 tools)',
            'src/salesforce_ai_engineer/workflow': 'Workflow engine',
            'src/salesforce_ai_engineer/memory': 'Memory system',
            'src/salesforce_ai_engineer/agent': 'Multi-agent orchestration',
        }
        
        for dir_path, description in key_dirs.items():
            full_path = os.path.join(workspace_path, dir_path)
            if os.path.exists(full_path):
                summary.append(f"✅ {description}: {dir_path}")
        
        # Count Python files
        py_files = sum(1 for _ in Path(workspace_path).rglob('*.py'))
        tests = sum(1 for _ in Path(workspace_path).rglob('test_*.py'))
        summary.append(f"\n📊 Project Stats:")
        summary.append(f"  - Python files: {py_files}")
        summary.append(f"  - Test files: {tests}")
        
    except Exception as e:
        summary.append(f"⚠️ Error analyzing project: {e}")
    
    return "\n".join(summary)


def generate_agent_system_prompt(workspace_path: str) -> str:
    """Generate comprehensive system prompt with project context."""
    
    project_info = get_project_structure_summary(workspace_path)
    
    prompt = f"""You are an advanced AI development agent specialized in building the Salesforce AI Engineer platform.

PROJECT CONTEXT:
{project_info}

ROLE & CAPABILITIES:
You are building a sophisticated 60-agent Salesforce automation platform with:
- Workflow engine (DAG-based orchestration with checkpointing)
- Multi-agent system (Orchestrator → Planner → Engineers)
- Tool layer (10 integrated tools: Salesforce CLI, filesystem, shell, HTTP, SQLite, Ollama, JSON, YAML, XML, Git)
- Memory system (persistent knowledge with versioning)
- Reward learning engine (workflow optimization)
- FastAPI REST API for external integration

CORE RESPONSIBILITIES:
1. CODE GENERATION: Write production-ready Python code following the existing patterns
2. TESTING: Create comprehensive test suites with pytest
3. DOCUMENTATION: Generate clear, actionable documentation
4. ANALYSIS: Understand and explain the codebase
5. DEBUGGING: Diagnose and fix issues
6. ARCHITECTURE: Design new modules and components
7. INTEGRATION: Connect components together seamlessly

TOOL USAGE:
When you need to accomplish a task, use tools in this JSON format:
```json
{{
  "tool": "tool_name",
  "parameters": {{
    "param1": "value1",
    "param2": "value2"
  }}
}}
```

AVAILABLE TOOLS (Enhanced Tool Layer):
FILESYSTEM TOOLS:
- list_files(path=".", recursive=False) - List directory contents
- read_file(filepath="path/to/file", start_line=None, end_line=None) - Read file with optional line range
- write_file(filepath="path/to/file", content="...") - Create/write files
- get_file_info(filepath="path/to/file") - Get metadata

CODE GENERATION TOOLS:
- search_files(pattern="text", path=".", file_pattern="*") - Search across codebase
- execute_command(command="...") - Run shell/python commands

SALESFORCE TOOLS:
- salesforce_cli(command="org list") - Execute Salesforce CLI commands
- salesforce_deploy(package="...", target_org="...") - Deploy packages

INTEGRATION TOOLS:
- http_request(method="GET", url="...", headers={{}}, body=None) - Make HTTP requests
- sqlite_query(db_path="...", query="...") - Execute SQL queries

DEVELOPMENT TOOLS:
- ollama_generate(prompt="...", model="...", stream=False) - Generate with Ollama
- json_process(operation="parse|validate|format", data="...") - Process JSON
- yaml_process(operation="parse|validate|format", data="...") - Process YAML

BEST PRACTICES:
✅ Always validate before executing
✅ Read related files to understand context
✅ Follow the existing code patterns and style
✅ Add tests for new code
✅ Handle errors gracefully
✅ Document your changes
✅ Think step-by-step for complex tasks
✅ Use tools iteratively - analyze, plan, execute, verify

WORKSPACE PATH: {workspace_path}

IMPORTANT: You are building toward a complete, production-grade system. Every code you write should be:
1. Type-safe (use Pydantic models, type hints)
2. Well-tested (unit + integration tests)
3. Well-documented (docstrings, README sections)
4. Production-ready (error handling, logging, monitoring)
5. Integrated with existing patterns (follow the established architecture)

Start by asking what you should help with, or respond to tasks directly using tools as needed."""
    
    return prompt


class AIAgent:
    """Advanced AI Agent with full tool integration and project awareness."""
    
    def __init__(self, workspace_path: str = None, stream: bool = False):
        """
        Initialize the advanced AI agent.
        
        Args:
            workspace_path: Path to workspace (defaults to parent of nvidia-nim-chat)
            stream: Whether to use streaming mode
        """
        self.stream = stream
        self.client = None
        
        # Determine workspace path
        if workspace_path is None:
            current_dir = Path(__file__).parent.parent.parent
            workspace_path = str(current_dir)
        
        self.workspace_path = workspace_path
        self.tools = AgentTools(workspace_path)
        self.conversation_history: List[Dict[str, str]] = []
        self.system_prompt = generate_agent_system_prompt(workspace_path)
        
        # Track task context
        self.current_task: Optional[str] = None
        self.task_context: Dict[str, Any] = {}
        
    def initialize(self):
        """Initialize the API client."""
        try:
            self.client = NVIDIANIMClient()
            return True
        except ValueError as e:
            print(f"❌ Error: {e}")
            return False
    
    def print_welcome(self):
        """Print welcome message."""
        print(f"\n🤖 Advanced AI Development Agent (NVIDIA NIM - {self.client.model})")
        print(f"📂 Workspace: {self.workspace_path}")
        print(f"📊 Project: Salesforce AI Engineer Platform (60-agent system)")
        print("\n📋 Commands:")
        print("  'exit' or 'quit'      - Exit agent")
        print("  'tools'               - Show available tools")
        print("  'status'              - Show current status")
        print("  'context'             - Show task context")
        print("  'clear'               - Clear conversation history")
        print("\n💬 Start chatting or ask me to help build the Salesforce platform!\n")
    
    def get_user_input(self) -> str:
        """Get input from the user."""
        try:
            return input("You: ").strip()
        except EOFError:
            return "exit"
    
    def handle_special_commands(self, command: str) -> bool:
        """Handle special agent commands. Returns True if command was handled."""
        cmd = command.lower().strip()
        
        if cmd in ['exit', 'quit', 'bye']:
            print("\n👋 Goodbye!\n")
            return True
        
        elif cmd == 'tools':
            self.show_available_tools()
            return True
        
        elif cmd == 'status':
            self.show_status()
            return True
        
        elif cmd == 'context':
            self.show_task_context()
            return True
        
        elif cmd == 'clear':
            self.conversation_history = []
            print("✅ Conversation history cleared\n")
            return True
        
        return False
    
    def show_available_tools(self):
        """Show available tools."""
        tools_info = """
📚 AVAILABLE TOOLS:

FILESYSTEM:
  - list_files(path=".", recursive=False)
  - read_file(filepath="...", start_line=None, end_line=None)
  - write_file(filepath="...", content="...")
  - get_file_info(filepath="...")

SEARCH & ANALYSIS:
  - search_files(pattern="...", path=".", file_pattern="*")
  - execute_command(command="...")

Use these tools by responding with JSON in this format:
```json
{{
  "tool": "tool_name",
  "parameters": {{"key": "value"}}
}}
```
"""
        print(tools_info)
    
    def show_status(self):
        """Show current agent status."""
        print(f"""
📊 AGENT STATUS:
  Model: {self.client.model if self.client else 'Not initialized'}
  Workspace: {self.workspace_path}
  Current Task: {self.current_task or 'None'}
  Message History: {len(self.conversation_history)} messages
  API Status: {'✅ Connected' if self.client else '❌ Not connected'}
""")
    
    def show_task_context(self):
        """Show current task context."""
        if not self.task_context:
            print("📋 No current task context\n")
        else:
            print("\n📋 TASK CONTEXT:")
            for key, value in self.task_context.items():
                print(f"  {key}: {value}")
            print()
    
    def set_task(self, task: str, context: Dict[str, Any] = None):
        """Set current task and context."""
        self.current_task = task
        self.task_context = context or {}
        print(f"✅ Task set: {task}\n")
    
    def extract_tool_call(self, text: str) -> Dict:
        """Extract tool call from AI response."""
        # Look for JSON code block
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass
        
        # Look for plain JSON
        json_match = re.search(r'\{[^{}]*"tool"[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except:
                pass
        
        return None
    
    def execute_tool(self, tool_call: Dict) -> Dict:
        """Execute a tool call with error handling."""
        tool_name = tool_call.get("tool")
        parameters = tool_call.get("parameters", {})
        
        if not hasattr(self.tools, tool_name):
            available = [m for m in dir(self.tools) if not m.startswith('_')]
            return {
                "error": f"Unknown tool: {tool_name}",
                "available_tools": available
            }
        
        try:
            tool_func = getattr(self.tools, tool_name)
            result = tool_func(**parameters)
            
            # Limit result size to prevent token overflow
            result_json = json.dumps(result, indent=2)
            if len(result_json) > 5000:
                result_json = result_json[:5000] + f"\n... (truncated, {len(result_json)} total chars)"
                result["_truncated"] = True
            
            return result
        except TypeError as e:
            return {
                "error": f"Invalid parameters for {tool_name}: {str(e)}",
                "hint": f"Check tool documentation or use 'tools' command"
            }
        except Exception as e:
            return {
                "error": f"Tool execution failed: {str(e)}",
                "error_type": type(e).__name__
            }
    
    def send_message(self, user_message: str, use_tools: bool = True):
        """
        Send a message and get response with optional tool execution.
        
        Args:
            user_message: The user's message
            use_tools: Whether to allow tool execution
        """
        # Add user message to history
        self.conversation_history.append(format_user_message(user_message))
        
        # Add system prompt if this is the first message
        if len(self.conversation_history) == 1:
            messages = [
                {"role": "system", "content": self.system_prompt},
                *self.conversation_history
            ]
        else:
            messages = self.conversation_history
        
        try:
            # Get AI response
            response = self.client.chat_completion(
                messages=messages,
                stream=False,
                max_tokens=2048
            )
            
            assistant_message = response["content"]
            
            # Check if AI wants to use a tool
            tool_call = self.extract_tool_call(assistant_message) if use_tools else None
            
            if tool_call:
                # Extract the text before tool call
                text_before = re.sub(r'```json.*?```', '', assistant_message, flags=re.DOTALL).strip()
                if text_before:
                    print(f"🤖 Agent: {text_before}\n")
                
                # Execute tool
                tool_name = tool_call.get('tool')
                parameters = tool_call.get('parameters', {})
                
                print(f"🔧 Using tool: {tool_name}")
                if parameters:
                    params_str = json.dumps(parameters, indent=2)
                    if len(params_str) > 500:
                        params_str = params_str[:500] + "..."
                    print(f"   Parameters: {params_str}")
                print()
                
                tool_result = self.execute_tool(tool_call)
                
                print(f"📊 Tool Result:")
                result_str = json.dumps(tool_result, indent=2)
                if len(result_str) > 2000:
                    result_str = result_str[:2000] + f"\n   ... (truncated)"
                print(result_str)
                print()
                
                # Add tool result to conversation
                tool_message = f"Tool '{tool_name}' executed successfully.\n\nResult (first 1000 chars):\n{json.dumps(tool_result, indent=2)[:1000]}"
                self.conversation_history.append(format_assistant_message(assistant_message))
                self.conversation_history.append(format_user_message(tool_message))
                
                # Get AI's response after seeing tool result
                if len(self.conversation_history) <= 2:
                    messages = [
                        {"role": "system", "content": self.system_prompt},
                        *self.conversation_history
                    ]
                else:
                    messages = self.conversation_history
                
                response2 = self.client.chat_completion(
                    messages=messages,
                    stream=False,
                    max_tokens=2048
                )
                
                final_message = response2["content"]
                print(f"🤖 Agent: {final_message}\n")
                self.conversation_history.append(format_assistant_message(final_message))
            else:
                # No tool call, just print response
                print(f"🤖 Agent: {assistant_message}\n")
                self.conversation_history.append(format_assistant_message(assistant_message))
                
        except ValueError as e:
            print(f"\n❌ Error: {e}\n")
            if self.conversation_history:
                self.conversation_history.pop()
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}\n")
            if self.conversation_history:
                self.conversation_history.pop()
    
    def run(self):
        """Run the agent loop."""
        if not self.initialize():
            return
        
        self.print_welcome()
        
        try:
            while True:
                user_input = self.get_user_input()
                
                # Skip empty input
                if not user_input:
                    continue
                
                # Check for special commands
                if self.handle_special_commands(user_input):
                    if user_input.lower() in ['exit', 'quit', 'bye']:
                        break
                    continue
                
                # Send message and get response with tool support
                self.send_message(user_input)
                
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
        except Exception as e:
            print(f"\n❌ Fatal error: {e}")
            sys.exit(1)


def main():
    """Main entry point for the AI agent."""
    parser = argparse.ArgumentParser(
        description="AI Agent with Tools - NVIDIA NIM powered"
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Workspace directory path (default: current directory)"
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Enable streaming mode for responses (not yet supported with tools)"
    )
    
    args = parser.parse_args()
    
    agent = AIAgent(workspace_path=args.workspace, stream=args.stream)
    agent.run()


if __name__ == "__main__":
    main()
