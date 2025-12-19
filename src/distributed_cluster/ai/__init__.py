"""
AI Module - نظام الذكاء الاصطناعي الشخصي الموزّع
================================================

This module provides distributed AI capabilities:

Supported AI Providers:
- Ollama (local models)
- vLLM (high-performance serving)
- OpenAI (GPT-4, GPT-3.5)
- Claude (Anthropic)
- Gemini (Google)
- Mistral AI
- Cohere
- Groq (fastest!)
- Together AI
- DeepSeek
- Perplexity
- HuggingFace
- Fireworks AI
- xAI (Grok)
- Azure OpenAI

Features:
- Agent framework for autonomous tasks
- Chat interface and conversation management
- Distributed inference across workers
- Model registry and management
- Multi-provider failover
- Load balancing
"""

from distributed_cluster.ai.agents.base import Agent, AgentResult, AgentTask
from distributed_cluster.ai.chat.conversation import Conversation, Message
from distributed_cluster.ai.inference.router import InferenceRouter
from distributed_cluster.ai.llm.all_providers import (
    AzureOpenAIProvider,
    ClaudeProvider,
    CohereProvider,
    DeepSeekProvider,
    ExtendedProviderType,
    FireworksProvider,
    GeminiProvider,
    GroqProvider,
    HuggingFaceProvider,
    MistralProvider,
    MultiProviderManager,
    PerplexityProvider,
    TogetherProvider,
    XAIProvider,
    create_all_provider,
)
from distributed_cluster.ai.llm.provider import (
    GenerationConfig,
    LLMProvider,
    LLMResponse,
    ModelInfo,
    OllamaProvider,
    OpenAIProvider,
    ProviderType,
    VLLMProvider,
    create_provider,
)
from distributed_cluster.ai.models.registry import ModelRegistry

__all__ = [
    # Base Classes
    "LLMProvider",
    "LLMResponse",
    "GenerationConfig",
    "ModelInfo",
    "ProviderType",
    "ExtendedProviderType",
    # Original Providers
    "OllamaProvider",
    "VLLMProvider",
    "OpenAIProvider",
    # New AI Providers
    "ClaudeProvider",
    "GeminiProvider",
    "MistralProvider",
    "CohereProvider",
    "GroqProvider",
    "TogetherProvider",
    "DeepSeekProvider",
    "PerplexityProvider",
    "HuggingFaceProvider",
    "FireworksProvider",
    "XAIProvider",
    "AzureOpenAIProvider",
    # Factory Functions
    "create_provider",
    "create_all_provider",
    # Multi-Provider Manager
    "MultiProviderManager",
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
