"""
AI Module - نظام الذكاء الاصطناعي الشخصي الموزّع
================================================

This module provides distributed AI capabilities:
- LLM integration (Ollama, vLLM, OpenAI-compatible)
- Agent framework for autonomous tasks
- Chat interface and conversation management
- Distributed inference across workers
- Model registry and management
"""

from distributed_cluster.ai.llm.provider import (
    LLMProvider,
    OllamaProvider,
    VLLMProvider,
    OpenAIProvider,
)
from distributed_cluster.ai.agents.base import Agent, AgentTask, AgentResult
from distributed_cluster.ai.chat.conversation import Conversation, Message
from distributed_cluster.ai.inference.router import InferenceRouter
from distributed_cluster.ai.models.registry import ModelRegistry

__all__ = [
    # LLM Providers
    "LLMProvider",
    "OllamaProvider",
    "VLLMProvider",
    "OpenAIProvider",
    # Agents
    "Agent",
    "AgentTask",
    "AgentResult",
    # Chat
    "Conversation",
    "Message",
    # Inference
    "InferenceRouter",
    # Models
    "ModelRegistry",
]
