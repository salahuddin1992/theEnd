"""
نظام الحوسبة الموزّعة - Distributed Cluster Computing System
=============================================================

A distributed computing framework implementing Master/Worker architecture.

Features:
- Resource-aware job scheduling (CPU/GPU/RAM)
- Container-based job isolation (Docker)
- Multi-master support with leader election
- Real-time monitoring and health checks
- Fault tolerance with automatic job retry
- Integration with all AI providers (Claude, Gemini, Groq, etc.)
- Continuous synchronization between computers
- Full resource utilization (CPU, GPU, RAM)

Architecture:
    Master (Control Plane)
    ├── API Server (REST + WebSocket)
    ├── Scheduler (Resource matching + Bin-packing)
    ├── State Store (Jobs, Workers, Leases)
    ├── Health Monitor
    ├── AI Router (Multi-provider LLM)
    └── Sync Manager (Real-time sync)

    Worker Agent (on each node)
    ├── Resource Reporter (CPU/GPU/RAM)
    ├── Job Executor (Container sandbox)
    ├── Heartbeat Sender
    ├── Result Uploader
    └── Sync Client

Supported AI Providers:
    - Ollama (local)
    - OpenAI (GPT-4)
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

__version__ = "0.2.0"
__author__ = "theEnd Team"

# Core exports
# AI exports
from distributed_cluster.ai import (
    ClaudeProvider,
    GeminiProvider,
    GroqProvider,
    # Inference
    InferenceRouter,
    # Providers
    LLMProvider,
    MistralProvider,
    MultiProviderManager,
    # Specific providers
    OllamaProvider,
    OpenAIProvider,
    create_all_provider,
    create_provider,
)
from distributed_cluster.models import (
    GPUInfo,
    # Jobs
    Job,
    JobStatus,
    JobSubmission,
    ResourceManager,
    # Resources
    ResourceSpec,
    ResourceUsage,
    # Workers
    WorkerInfo,
    WorkerStatus,
    get_resource_manager,
    optimize_system_for_ai,
)

# Sync exports
from distributed_cluster.sync import (
    ConflictResolver,
    RealtimeSync,
    StateSync,
    SyncConfig,
    SyncManager,
    SyncMode,
)

__all__ = [
    # Version
    "__version__",
    "__author__",

    # Resources
    "ResourceSpec",
    "ResourceUsage",
    "GPUInfo",
    "ResourceManager",
    "get_resource_manager",
    "optimize_system_for_ai",

    # Jobs
    "Job",
    "JobStatus",
    "JobSubmission",

    # Workers
    "WorkerInfo",
    "WorkerStatus",

    # AI
    "LLMProvider",
    "create_provider",
    "create_all_provider",
    "MultiProviderManager",
    "OllamaProvider",
    "OpenAIProvider",
    "ClaudeProvider",
    "GeminiProvider",
    "GroqProvider",
    "MistralProvider",
    "InferenceRouter",

    # Sync
    "SyncManager",
    "SyncConfig",
    "SyncMode",
    "StateSync",
    "RealtimeSync",
    "ConflictResolver",
]
