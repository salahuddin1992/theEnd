"""
Agent Tools - أدوات الوكلاء
============================

Built-in tools for agents to interact with systems.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from distributed_cluster.ai.agents.base import Tool, ToolResult, ToolResultType

logger = logging.getLogger(__name__)


class ShellTool(Tool):
    """أداة تنفيذ أوامر Shell."""

    def __init__(
        self,
        allowed_commands: Optional[List[str]] = None,
        working_dir: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.allowed_commands = allowed_commands
        self.working_dir = working_dir or os.getcwd()
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Execute shell commands. Use for file operations, system commands, etc."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str) -> ToolResult:
        """تنفيذ أمر Shell."""
        start_time = time.time()

        # Security check
        if self.allowed_commands:
            cmd_name = command.split()[0]
            if cmd_name not in self.allowed_commands:
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.ERROR,
                    output=None,
                    error=f"Command '{cmd_name}' is not allowed",
                )

        try:
            # Run command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            elapsed = (time.time() - start_time) * 1000

            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")

            if process.returncode == 0:
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=output or "Command executed successfully",
                    execution_time_ms=elapsed,
                )
            else:
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.ERROR,
                    output=output,
                    error=error_output or f"Exit code: {process.returncode}",
                    execution_time_ms=elapsed,
                )

        except asyncio.TimeoutError:
            return ToolResult(
                tool_name=self.name,
                result_type=ToolResultType.TIMEOUT,
                output=None,
                error=f"Command timed out after {self.timeout}s",
                execution_time_ms=self.timeout * 1000,
            )

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return ToolResult(
                tool_name=self.name,
                result_type=ToolResultType.ERROR,
                output=None,
                error=str(e),
                execution_time_ms=elapsed,
            )


class FileTool(Tool):
    """أداة التعامل مع الملفات."""

    def __init__(
        self,
        base_dir: Optional[str] = None,
        allowed_extensions: Optional[List[str]] = None,
    ):
        self.base_dir = base_dir or os.getcwd()
        self.allowed_extensions = allowed_extensions

    @property
    def name(self) -> str:
        return "file"

    @property
    def description(self) -> str:
        return "Read, write, or list files. Supports text files."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "list", "exists", "delete"],
                    "description": "The file operation to perform",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory path (relative to base_dir)",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write action)",
                },
            },
            "required": ["action", "path"],
        }

    def _resolve_path(self, path: str) -> Path:
        """تحليل المسار بشكل آمن."""
        resolved = Path(self.base_dir) / path
        resolved = resolved.resolve()

        # Security: ensure path is within base_dir
        base = Path(self.base_dir).resolve()
        if not str(resolved).startswith(str(base)):
            raise ValueError("Path escapes base directory")

        return resolved

    async def execute(
        self,
        action: str,
        path: str,
        content: Optional[str] = None,
    ) -> ToolResult:
        """تنفيذ عملية الملف."""
        start_time = time.time()

        try:
            resolved_path = self._resolve_path(path)

            # Check extension
            if self.allowed_extensions and resolved_path.suffix:
                if resolved_path.suffix.lower() not in self.allowed_extensions:
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.ERROR,
                        output=None,
                        error=f"Extension '{resolved_path.suffix}' is not allowed",
                    )

            if action == "read":
                if not resolved_path.exists():
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.ERROR,
                        output=None,
                        error=f"File not found: {path}",
                    )

                content = resolved_path.read_text(encoding="utf-8")
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=content,
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            elif action == "write":
                if content is None:
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.ERROR,
                        output=None,
                        error="Content is required for write action",
                    )

                resolved_path.parent.mkdir(parents=True, exist_ok=True)
                resolved_path.write_text(content, encoding="utf-8")

                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=f"Written {len(content)} characters to {path}",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            elif action == "list":
                if not resolved_path.exists():
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.ERROR,
                        output=None,
                        error=f"Directory not found: {path}",
                    )

                if resolved_path.is_file():
                    files = [resolved_path.name]
                else:
                    files = [f.name for f in resolved_path.iterdir()]

                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=files,
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            elif action == "exists":
                exists = resolved_path.exists()
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=exists,
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            elif action == "delete":
                if not resolved_path.exists():
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.ERROR,
                        output=None,
                        error=f"File not found: {path}",
                    )

                if resolved_path.is_file():
                    resolved_path.unlink()
                else:
                    import shutil
                    shutil.rmtree(resolved_path)

                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=f"Deleted: {path}",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            else:
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.ERROR,
                    output=None,
                    error=f"Unknown action: {action}",
                )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                result_type=ToolResultType.ERROR,
                output=None,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


class WebSearchTool(Tool):
    """أداة البحث على الويب."""

    def __init__(
        self,
        search_engine: str = "duckduckgo",
        max_results: int = 5,
    ):
        self.search_engine = search_engine
        self.max_results = max_results

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for information. Returns relevant results."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (max 10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        num_results: int = 5,
    ) -> ToolResult:
        """تنفيذ البحث."""
        start_time = time.time()
        num_results = min(num_results, self.max_results, 10)

        try:
            # Use DuckDuckGo HTML search (no API key needed)
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; AI-Agent/1.0)"
                    },
                    timeout=15.0,
                )
                response.raise_for_status()

                # Parse results (simple extraction)
                html = response.text
                results = []

                # Extract result snippets
                import re
                result_pattern = r'class="result__snippet"[^>]*>([^<]+)'
                title_pattern = r'class="result__a"[^>]*>([^<]+)'
                url_pattern = r'class="result__url"[^>]*>([^<]+)'

                snippets = re.findall(result_pattern, html)
                titles = re.findall(title_pattern, html)
                urls = re.findall(url_pattern, html)

                for i in range(min(num_results, len(snippets))):
                    results.append({
                        "title": titles[i] if i < len(titles) else "N/A",
                        "snippet": snippets[i].strip(),
                        "url": urls[i].strip() if i < len(urls) else "N/A",
                    })

                if not results:
                    results = [{"message": "No results found"}]

                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=results,
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                result_type=ToolResultType.ERROR,
                output=None,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


class WebFetchTool(Tool):
    """أداة جلب صفحات الويب."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch content from a URL. Returns the page content."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
                "extract_text": {
                    "type": "boolean",
                    "description": "Extract text only (remove HTML tags)",
                    "default": True,
                },
            },
            "required": ["url"],
        }

    async def execute(
        self,
        url: str,
        extract_text: bool = True,
    ) -> ToolResult:
        """جلب محتوى URL."""
        start_time = time.time()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    follow_redirects=True,
                    timeout=self.timeout,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; AI-Agent/1.0)"
                    },
                )
                response.raise_for_status()

                content = response.text

                if extract_text:
                    # Simple HTML tag removal
                    import re
                    content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
                    content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL)
                    content = re.sub(r"<[^>]+>", " ", content)
                    content = re.sub(r"\s+", " ", content).strip()
                    # Limit content length
                    content = content[:10000]

                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=content,
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                result_type=ToolResultType.ERROR,
                output=None,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


class CodeTool(Tool):
    """أداة تنفيذ كود Python."""

    def __init__(
        self,
        timeout: float = 30.0,
        safe_mode: bool = True,
    ):
        self.timeout = timeout
        self.safe_mode = safe_mode

    @property
    def name(self) -> str:
        return "python"

    @property
    def description(self) -> str:
        return "Execute Python code. Returns the output or result."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                },
            },
            "required": ["code"],
        }

    async def execute(self, code: str) -> ToolResult:
        """تنفيذ كود Python."""
        start_time = time.time()

        if self.safe_mode:
            # Block dangerous operations
            dangerous_patterns = [
                "import os", "import sys", "import subprocess",
                "open(", "__import__", "eval(", "exec(",
                "os.system", "subprocess.",
            ]
            for pattern in dangerous_patterns:
                if pattern in code:
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.ERROR,
                        output=None,
                        error=f"Unsafe code pattern detected: {pattern}",
                    )

        try:
            # Run in subprocess for isolation
            process = await asyncio.create_subprocess_exec(
                "python", "-c", code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            elapsed = (time.time() - start_time) * 1000

            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")

            if process.returncode == 0:
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=output or "Code executed successfully (no output)",
                    execution_time_ms=elapsed,
                )
            else:
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.ERROR,
                    output=output,
                    error=error_output,
                    execution_time_ms=elapsed,
                )

        except asyncio.TimeoutError:
            return ToolResult(
                tool_name=self.name,
                result_type=ToolResultType.TIMEOUT,
                output=None,
                error=f"Code execution timed out after {self.timeout}s",
                execution_time_ms=self.timeout * 1000,
            )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                result_type=ToolResultType.ERROR,
                output=None,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


class CalculatorTool(Tool):
    """أداة حسابية."""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Perform mathematical calculations. Supports basic operations and math functions."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)', 'sin(3.14)')",
                },
            },
            "required": ["expression"],
        }

    async def execute(self, expression: str) -> ToolResult:
        """تنفيذ العملية الحسابية."""
        import math

        start_time = time.time()

        # Safe math namespace
        safe_dict = {
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            "pi": math.pi,
            "e": math.e,
        }

        try:
            # Sanitize expression
            expression = expression.replace("^", "**")

            result = eval(expression, {"__builtins__": {}}, safe_dict)

            return ToolResult(
                tool_name=self.name,
                result_type=ToolResultType.SUCCESS,
                output=result,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                result_type=ToolResultType.ERROR,
                output=None,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


class MemoryTool(Tool):
    """أداة الذاكرة - لتخزين واسترجاع المعلومات."""

    def __init__(self):
        self._memory: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "Store and retrieve information. Use to remember important data."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["store", "retrieve", "list", "delete"],
                    "description": "Memory operation",
                },
                "key": {
                    "type": "string",
                    "description": "Key to store/retrieve",
                },
                "value": {
                    "type": "string",
                    "description": "Value to store (for store action)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        key: Optional[str] = None,
        value: Optional[str] = None,
    ) -> ToolResult:
        """تنفيذ عملية الذاكرة."""
        start_time = time.time()

        try:
            if action == "store":
                if not key or value is None:
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.ERROR,
                        output=None,
                        error="Key and value are required for store action",
                    )

                self._memory[key] = value
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=f"Stored '{key}'",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            elif action == "retrieve":
                if not key:
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.ERROR,
                        output=None,
                        error="Key is required for retrieve action",
                    )

                if key not in self._memory:
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.SUCCESS,
                        output=f"Key '{key}' not found",
                        execution_time_ms=(time.time() - start_time) * 1000,
                    )

                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=self._memory[key],
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            elif action == "list":
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.SUCCESS,
                    output=list(self._memory.keys()),
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            elif action == "delete":
                if not key:
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.ERROR,
                        output=None,
                        error="Key is required for delete action",
                    )

                if key in self._memory:
                    del self._memory[key]
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.SUCCESS,
                        output=f"Deleted '{key}'",
                        execution_time_ms=(time.time() - start_time) * 1000,
                    )
                else:
                    return ToolResult(
                        tool_name=self.name,
                        result_type=ToolResultType.SUCCESS,
                        output=f"Key '{key}' not found",
                        execution_time_ms=(time.time() - start_time) * 1000,
                    )

            else:
                return ToolResult(
                    tool_name=self.name,
                    result_type=ToolResultType.ERROR,
                    output=None,
                    error=f"Unknown action: {action}",
                )

        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                result_type=ToolResultType.ERROR,
                output=None,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )


# Export all tools
def get_default_tools() -> List[Tool]:
    """الحصول على الأدوات الافتراضية."""
    return [
        ShellTool(),
        FileTool(),
        WebSearchTool(),
        WebFetchTool(),
        CodeTool(),
        CalculatorTool(),
        MemoryTool(),
    ]
