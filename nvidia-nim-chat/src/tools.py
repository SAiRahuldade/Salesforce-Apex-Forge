"""Tools for the AI agent to interact with the file system and execute commands."""

import os
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Any


class AgentTools:
    """Tools that the AI agent can use."""
    
    def __init__(self, workspace_path: str = None):
        """Initialize tools with workspace path."""
        self.workspace_path = workspace_path or os.getcwd()
    
    def list_files(self, path: str = ".", recursive: bool = False) -> Dict[str, Any]:
        """
        List files in a directory.
        
        Args:
            path: Directory path (relative to workspace)
            recursive: Whether to list recursively
            
        Returns:
            Dictionary with files and directories
        """
        try:
            full_path = os.path.join(self.workspace_path, path)
            
            if not os.path.exists(full_path):
                return {"error": f"Path does not exist: {path}"}
            
            if recursive:
                files = []
                dirs = []
                for root, dirnames, filenames in os.walk(full_path):
                    rel_root = os.path.relpath(root, full_path)
                    for d in dirnames:
                        dirs.append(os.path.join(rel_root, d) if rel_root != "." else d)
                    for f in filenames:
                        files.append(os.path.join(rel_root, f) if rel_root != "." else f)
                return {"files": files, "directories": dirs, "path": path}
            else:
                items = os.listdir(full_path)
                files = [f for f in items if os.path.isfile(os.path.join(full_path, f))]
                dirs = [d for d in items if os.path.isdir(os.path.join(full_path, d))]
                return {"files": files, "directories": dirs, "path": path}
                
        except Exception as e:
            return {"error": str(e)}
    
    def read_file(self, filepath: str, start_line: int = None, end_line: int = None) -> Dict[str, Any]:
        """
        Read contents of a file.
        
        Args:
            filepath: Path to file (relative to workspace)
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (1-indexed)
            
        Returns:
            Dictionary with file content
        """
        try:
            full_path = os.path.join(self.workspace_path, filepath)
            
            if not os.path.exists(full_path):
                return {"error": f"File does not exist: {filepath}"}
            
            if not os.path.isfile(full_path):
                return {"error": f"Not a file: {filepath}"}
            
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            if start_line is not None or end_line is not None:
                start = (start_line - 1) if start_line else 0
                end = end_line if end_line else len(lines)
                lines = lines[start:end]
            
            content = ''.join(lines)
            return {
                "filepath": filepath,
                "content": content,
                "lines": len(lines),
                "total_lines": len(lines)
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def write_file(self, filepath: str, content: str) -> Dict[str, Any]:
        """
        Write content to a file.
        
        Args:
            filepath: Path to file (relative to workspace)
            content: Content to write
            
        Returns:
            Dictionary with result
        """
        try:
            full_path = os.path.join(self.workspace_path, filepath)
            
            # Create directories if they don't exist
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "filepath": filepath,
                "bytes_written": len(content.encode('utf-8'))
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def execute_command(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Execute a shell command.
        
        Args:
            command: Command to execute
            timeout: Timeout in seconds
            
        Returns:
            Dictionary with command output
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.workspace_path
            )
            
            return {
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0
            }
            
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout} seconds"}
        except Exception as e:
            return {"error": str(e)}
    
    def search_files(self, pattern: str, path: str = ".", file_pattern: str = "*") -> Dict[str, Any]:
        """
        Search for text pattern in files.
        
        Args:
            pattern: Text pattern to search for
            path: Directory to search in
            file_pattern: File pattern to match (e.g., "*.py")
            
        Returns:
            Dictionary with search results
        """
        try:
            import re
            from pathlib import Path
            
            full_path = Path(self.workspace_path) / path
            matches = []
            
            for file_path in full_path.rglob(file_pattern):
                if file_path.is_file():
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for line_num, line in enumerate(f, 1):
                                if re.search(pattern, line):
                                    matches.append({
                                        "file": str(file_path.relative_to(self.workspace_path)),
                                        "line": line_num,
                                        "content": line.strip()
                                    })
                    except:
                        continue
            
            return {
                "pattern": pattern,
                "matches": matches,
                "count": len(matches)
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_file_info(self, filepath: str) -> Dict[str, Any]:
        """
        Get information about a file.
        
        Args:
            filepath: Path to file
            
        Returns:
            Dictionary with file information
        """
        try:
            full_path = os.path.join(self.workspace_path, filepath)
            
            if not os.path.exists(full_path):
                return {"error": f"Path does not exist: {filepath}"}
            
            stat = os.stat(full_path)
            
            return {
                "filepath": filepath,
                "size": stat.st_size,
                "is_file": os.path.isfile(full_path),
                "is_directory": os.path.isdir(full_path),
                "modified": stat.st_mtime,
                "created": stat.st_ctime
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_available_tools(self) -> List[Dict[str, str]]:
        """Get list of available tools with descriptions."""
        return [
            {
                "name": "list_files",
                "description": "List files and directories in a path",
                "usage": "list_files(path='.', recursive=False)"
            },
            {
                "name": "read_file",
                "description": "Read contents of a file",
                "usage": "read_file(filepath='path/to/file.txt')"
            },
            {
                "name": "write_file",
                "description": "Write content to a file",
                "usage": "write_file(filepath='path/to/file.txt', content='...')"
            },
            {
                "name": "execute_command",
                "description": "Execute a shell command",
                "usage": "execute_command(command='ls -la')"
            },
            {
                "name": "search_files",
                "description": "Search for text pattern in files",
                "usage": "search_files(pattern='TODO', path='.', file_pattern='*.py')"
            },
            {
                "name": "get_file_info",
                "description": "Get information about a file",
                "usage": "get_file_info(filepath='path/to/file.txt')"
            }
        ]
