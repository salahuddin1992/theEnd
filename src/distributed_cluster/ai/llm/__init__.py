"""
LLM Providers - موفرو نماذج اللغة الكبيرة
==========================================

Complete integration with all major AI providers:
- Ollama (local)
- vLLM (high-performance)
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
"""

from distributed_cluster.ai.llm.provider import (
    LLMProvider,
    OllamaProvider,
    VLLMProvider,
    OpenAIProvider,
    LLMResponse,
    GenerationConfig,
    ModelInfo,
    ProviderType,
    create_provider,
)

from distributed_cluster.ai.llm.all_providers import (
    # Extended Provider Types
    ExtendedProviderType,

    # All Providers
    ClaudeProvider,
    GeminiProvider,
    MistralProvider,
    CohereProvider,
    GroqProvider,
    TogetherProvider,
    DeepSeekProvider,
    PerplexityProvider,
    HuggingFaceProvider,
    FireworksProvider,
    XAIProvider,
    AzureOpenAIProvider,

    # Universal Factory
    create_all_provider,

    # Multi-Provider Manager
    MultiProviderManager,
)

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

    # New Providers
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

    # Factories
    "create_provider",
    "create_all_provider",

    # Manager
    "MultiProviderManager",
]
