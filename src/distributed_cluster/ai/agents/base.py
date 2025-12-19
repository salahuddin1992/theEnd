"""
Agent Base - الوكيل الأساسي
============================

Framework for building AI agents that can:
- Execute tasks autonomously
- Use tools to interact with systems
- Plan and reason about complex tasks
- Collaborate with other agents
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from distributed_cluster.ai.llm.provider import (
    GenerationConfig,
    LLMProvider,
)

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """حالات الوكيل."""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ToolResultType(str, Enum):
    """نوع نتيجة الأداة."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class ToolResult:
    """نتيجة تنفيذ أداة."""
    tool_name: str
    result_type: ToolResultType
    output: Any
    error: Optional[str] = None
    execution_time_ms: float = 0

    @property
    def is_success(self) -> bool:
        return self.result_type == ToolResultType.SUCCESS

    def to_string(self) -> str:
        """تحويل لنص."""
        if self.is_success:
            if isinstance(self.output, str):
                return self.output
            return json.dumps(self.output, ensure_ascii=False, indent=2)
        return f"Error: {self.error}"


class Tool(ABC):
    """
    أداة يمكن للوكيل استخدامها.

    Tools allow agents to interact with external systems.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """اسم الأداة."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """وصف الأداة."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """معاملات الأداة (JSON Schema)."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """تنفيذ الأداة."""
        pass

    def to_schema(self) -> Dict[str, Any]:
        """تحويل لـ JSON Schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class AgentTask:
    """مهمة للوكيل."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    priority: int = 50
    timeout_seconds: float = 300
    max_iterations: int = 10
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Constraints
    allowed_tools: Optional[List[str]] = None
    forbidden_tools: Optional[List[str]] = None


@dataclass
class AgentStep:
    """خطوة في تنفيذ المهمة."""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    thought: str = ""
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentResult:
    """نتيجة تنفيذ المهمة."""
    task_id: str
    status: AgentStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    steps: List[AgentStep] = field(default_factory=list)
    total_tokens: int = 0
    total_time_ms: float = 0
    iterations: int = 0

    @property
    def is_success(self) -> bool:
        return self.status == AgentStatus.COMPLETED


@dataclass
class AgentMemory:
    """ذاكرة الوكيل."""
    short_term: List[Dict[str, Any]] = field(default_factory=list)
    long_term: Dict[str, Any] = field(default_factory=dict)
    working: Dict[str, Any] = field(default_factory=dict)

    def add_observation(self, observation: str, source: str = "system") -> None:
        """إضافة ملاحظة."""
        self.short_term.append({
            "type": "observation",
            "content": observation,
            "source": source,
            "timestamp": datetime.utcnow().isoformat(),
        })
        # Keep last 50 observations
        self.short_term = self.short_term[-50:]

    def add_action(self, action: str, result: Any) -> None:
        """إضافة فعل."""
        self.short_term.append({
            "type": "action",
            "action": action,
            "result": str(result)[:500],
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_context(self, max_items: int = 10) -> str:
        """الحصول على السياق."""
        recent = self.short_term[-max_items:]
        lines = []
        for item in recent:
            if item["type"] == "observation":
                lines.append(f"[{item['source']}] {item['content']}")
            else:
                lines.append(f"[Action: {item['action']}] {item['result'][:100]}")
        return "\n".join(lines)


class Agent:
    """
    وكيل ذكي يمكنه تنفيذ المهام.

    An intelligent agent that can:
    - Understand and plan tasks
    - Use tools to accomplish goals
    - Learn from feedback
    - Collaborate with other agents
    """

    # ReAct prompt template
    REACT_PROMPT = """You are an intelligent AI assistant that helps users accomplish tasks.

Available Tools:
{tools}

Use the following format:

Thought: Think about what to do next
Action: tool_name
Action Input: {{"param1": "value1", "param2": "value2"}}

After receiving the observation, continue with:
Thought: Analyze the result
... (repeat Thought/Action/Action Input as needed)

When you have the final answer:
Thought: I now have the final answer
Final Answer: [your final response to the user]

Previous Context:
{context}

Current Task: {task}

Begin!

Thought:"""

    def __init__(
        self,
        name: str,
        llm_provider: LLMProvider,
        model: str,
        tools: Optional[List[Tool]] = None,
        system_prompt: Optional[str] = None,
        generation_config: Optional[GenerationConfig] = None,
    ):
        self.name = name
        self.llm = llm_provider
        self.model = model
        self.tools: Dict[str, Tool] = {}
        self.system_prompt = system_prompt
        self.generation_config = generation_config or GenerationConfig(
            temperature=0.3,
            max_tokens=2048,
        )

        # Register tools
        if tools:
            for tool in tools:
                self.register_tool(tool)

        # Memory
        self.memory = AgentMemory()

        # State
        self.status = AgentStatus.IDLE
        self._current_task: Optional[AgentTask] = None

    def register_tool(self, tool: Tool) -> None:
        """تسجيل أداة."""
        self.tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def unregister_tool(self, tool_name: str) -> None:
        """إلغاء تسجيل أداة."""
        if tool_name in self.tools:
            del self.tools[tool_name]

    def _get_tools_description(self, task: AgentTask) -> str:
        """وصف الأدوات المتاحة."""
        available_tools = self.tools.copy()

        # Filter by allowed tools
        if task.allowed_tools:
            available_tools = {
                k: v for k, v in available_tools.items()
                if k in task.allowed_tools
            }

        # Filter by forbidden tools
        if task.forbidden_tools:
            available_tools = {
                k: v for k, v in available_tools.items()
                if k not in task.forbidden_tools
            }

        descriptions = []
        for name, tool in available_tools.items():
            params = json.dumps(tool.parameters, indent=2)
            descriptions.append(f"- {name}: {tool.description}\n  Parameters: {params}")

        return "\n".join(descriptions)

    def _parse_action(self, text: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """تحليل الفعل من النص."""
        # Try to extract action and input
        action_match = re.search(r"Action:\s*(\w+)", text)
        input_match = re.search(r"Action Input:\s*({.*?})", text, re.DOTALL)

        action = action_match.group(1) if action_match else None
        action_input = None

        if input_match:
            try:
                action_input = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                # Try to fix common JSON issues
                input_str = input_match.group(1)
                input_str = re.sub(r"'", '"', input_str)
                try:
                    action_input = json.loads(input_str)
                except json.JSONDecodeError:
                    action_input = {"input": input_str}

        return action, action_input

    def _extract_final_answer(self, text: str) -> Optional[str]:
        """استخراج الإجابة النهائية."""
        match = re.search(r"Final Answer:\s*(.+)", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    async def execute_task(self, task: AgentTask) -> AgentResult:
        """تنفيذ مهمة."""
        self.status = AgentStatus.THINKING
        self._current_task = task
        steps: List[AgentStep] = []
        total_tokens = 0
        start_time = datetime.utcnow()

        try:
            # Build initial prompt
            tools_desc = self._get_tools_description(task)
            context = self.memory.get_context()

            prompt = self.REACT_PROMPT.format(
                tools=tools_desc,
                context=context or "No previous context",
                task=task.description,
            )

            for iteration in range(task.max_iterations):
                # Generate response
                response = await self.llm.generate(
                    prompt=prompt,
                    model=self.model,
                    config=self.generation_config,
                    system_prompt=self.system_prompt,
                )

                total_tokens += response.total_tokens
                text = response.text

                # Create step
                step = AgentStep()

                # Extract thought
                thought_match = re.search(r"Thought:\s*(.+?)(?=Action:|Final Answer:|$)", text, re.DOTALL)
                if thought_match:
                    step.thought = thought_match.group(1).strip()

                # Check for final answer
                final_answer = self._extract_final_answer(text)
                if final_answer:
                    step.observation = f"Final Answer: {final_answer}"
                    steps.append(step)

                    self.memory.add_observation(final_answer, "agent")

                    elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000

                    self.status = AgentStatus.COMPLETED
                    return AgentResult(
                        task_id=task.task_id,
                        status=AgentStatus.COMPLETED,
                        result=final_answer,
                        steps=steps,
                        total_tokens=total_tokens,
                        total_time_ms=elapsed,
                        iterations=iteration + 1,
                    )

                # Parse action
                action, action_input = self._parse_action(text)

                if action:
                    step.action = action
                    step.action_input = action_input

                    # Execute tool
                    self.status = AgentStatus.EXECUTING

                    if action in self.tools:
                        try:
                            tool = self.tools[action]
                            result = await asyncio.wait_for(
                                tool.execute(**(action_input or {})),
                                timeout=60,
                            )
                            observation = result.to_string()
                        except asyncio.TimeoutError:
                            observation = f"Error: Tool {action} timed out"
                        except Exception as e:
                            observation = f"Error: {str(e)}"
                    else:
                        observation = f"Error: Unknown tool '{action}'. Available tools: {list(self.tools.keys())}"

                    step.observation = observation
                    self.memory.add_action(action, observation)

                    # Update prompt with observation
                    prompt = f"{prompt}{text}\nObservation: {observation}\n\nThought:"

                    self.status = AgentStatus.THINKING

                steps.append(step)

            # Max iterations reached
            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000

            self.status = AgentStatus.FAILED
            return AgentResult(
                task_id=task.task_id,
                status=AgentStatus.FAILED,
                error="Max iterations reached without final answer",
                steps=steps,
                total_tokens=total_tokens,
                total_time_ms=elapsed,
                iterations=task.max_iterations,
            )

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000

            self.status = AgentStatus.FAILED
            return AgentResult(
                task_id=task.task_id,
                status=AgentStatus.FAILED,
                error=str(e),
                steps=steps,
                total_tokens=total_tokens,
                total_time_ms=elapsed,
            )

        finally:
            self._current_task = None

    async def run(self, task_description: str, **kwargs) -> AgentResult:
        """تشغيل مهمة بسيطة."""
        task = AgentTask(
            description=task_description,
            **kwargs,
        )
        return await self.execute_task(task)

    def cancel(self) -> None:
        """إلغاء المهمة الحالية."""
        self.status = AgentStatus.CANCELLED


class SpecializedAgent(Agent):
    """
    وكيل متخصص - قاعدة للوكلاء المتخصصة.

    Extend this class to create specialized agents for specific domains.
    """

    @property
    @abstractmethod
    def specialization(self) -> str:
        """تخصص الوكيل."""
        pass

    @property
    def default_system_prompt(self) -> str:
        """برومبت النظام الافتراضي."""
        return f"You are a specialized AI assistant focused on {self.specialization}."


class CodeAgent(SpecializedAgent):
    """وكيل متخصص في البرمجة."""

    @property
    def specialization(self) -> str:
        return "software development and coding"

    @property
    def default_system_prompt(self) -> str:
        return """You are an expert software developer assistant.
You can write, review, and debug code in multiple languages.
Always write clean, well-documented, and efficient code.
Follow best practices and security guidelines."""


class ResearchAgent(SpecializedAgent):
    """وكيل متخصص في البحث."""

    @property
    def specialization(self) -> str:
        return "research and information gathering"

    @property
    def default_system_prompt(self) -> str:
        return """You are a research assistant specialized in gathering and analyzing information.
You can search for information, summarize findings, and provide well-sourced answers.
Always cite your sources and distinguish between facts and opinions."""


class DataAgent(SpecializedAgent):
    """وكيل متخصص في البيانات."""

    @property
    def specialization(self) -> str:
        return "data analysis and processing"

    @property
    def default_system_prompt(self) -> str:
        return """You are a data analyst assistant.
You can process, analyze, and visualize data.
You understand statistics, data structures, and can work with various data formats."""
