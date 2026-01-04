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

from distributed_cluster.ai.llm.all_providers import (
    AzureOpenAIProvider,
    # All Providers
    ClaudeProvider,
    CohereProvider,
    DeepSeekProvider,
    # Extended Provider Types
    ExtendedProviderType,
    FireworksProvider,
    GeminiProvider,
    GroqProvider,
    HuggingFaceProvider,
    MistralProvider,
    # Multi-Provider Manager
    MultiProviderManager,
    PerplexityProvider,
    TogetherProvider,
    XAIProvider,
    # Universal Factory
    create_all_provider,
)

# Cache support
from distributed_cluster.ai.llm.cache import (
    CacheConfig,
    CacheEntry,
    CacheStats,
    LLMCache,
    SemanticCache,
    create_cache,
)

# Cost optimization
from distributed_cluster.ai.llm.cost_optimizer import (
    CostForecast,
    CostOptimizer,
    ModelRecommendation,
    OptimizationStrategy,
    ProviderMetrics,
    SavingsOpportunity,
    TaskComplexity,
    create_cost_optimizer,
)

# Cost tracking
from distributed_cluster.ai.llm.cost_tracker import (
    DEFAULT_PRICING,
    BudgetConfig,
    CostCurrency,
    CostSummary,
    CostTracker,
    ModelPricing,
    UsageRecord,
    create_cost_tracker,
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

# Vision & Embeddings
from distributed_cluster.ai.llm.vision import (
    BatchEmbeddingResult,
    CohereEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingResult,
    ImageInput,
    ImageSource,
    MediaType,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    SearchResult,
    SemanticSearchIndex,
    VisionMessage,
    VoyageEmbeddingProvider,
    cosine_similarity,
    create_embedding_provider,
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
    # Cache
    "CacheConfig",
    "CacheEntry",
    "CacheStats",
    "LLMCache",
    "SemanticCache",
    "create_cache",
    # Cost Tracking
    "BudgetConfig",
    "CostCurrency",
    "CostSummary",
    "CostTracker",
    "ModelPricing",
    "UsageRecord",
    "create_cost_tracker",
    "DEFAULT_PRICING",
    # Cost Optimization
    "CostOptimizer",
    "OptimizationStrategy",
    "TaskComplexity",
    "ProviderMetrics",
    "ModelRecommendation",
    "SavingsOpportunity",
    "CostForecast",
    "create_cost_optimizer",
    # Vision
    "ImageInput",
    "ImageSource",
    "MediaType",
    "VisionMessage",
    # Embeddings
    "EmbeddingResult",
    "BatchEmbeddingResult",
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "CohereEmbeddingProvider",
    "VoyageEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "SemanticSearchIndex",
    "SearchResult",
    "cosine_similarity",
    "create_embedding_provider",
]
