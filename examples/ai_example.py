#!/usr/bin/env python3
"""
مثال استخدام نظام الذكاء الاصطناعي الموزع
Distributed AI System Usage Example
=====================================

This example demonstrates:
1. Using LLM providers (Ollama)
2. Creating and using agents
3. Managing conversations
4. Distributed inference routing
"""

import asyncio
from pathlib import Path

# =============================================================================
# Example 1: Basic LLM Usage
# =============================================================================

async def basic_llm_example():
    """مثال أساسي لاستخدام LLM."""
    print("\n" + "="*60)
    print("Example 1: Basic LLM Usage")
    print("="*60)

    from distributed_cluster.ai.llm import OllamaProvider, GenerationConfig

    # Create provider
    provider = OllamaProvider(base_url="http://localhost:11434")

    # Check if Ollama is running
    healthy = await provider.health_check()
    if not healthy:
        print("⚠️  Ollama is not running. Start it with: ollama serve")
        return

    # List available models
    print("\n📦 Available models:")
    models = await provider.list_models()
    for m in models[:5]:
        print(f"  - {m.name}")

    # Generate text
    print("\n💬 Generating response...")

    config = GenerationConfig(
        temperature=0.7,
        max_tokens=100,
    )

    response = await provider.generate(
        prompt="What is Python in one sentence?",
        model="llama3.2",  # Change if you have a different model
        config=config,
    )

    print(f"\nResponse: {response.text}")
    print(f"Tokens: {response.total_tokens}")
    print(f"Time: {response.generation_time_ms:.0f}ms")

    await provider.close()


# =============================================================================
# Example 2: Agent Usage
# =============================================================================

async def agent_example():
    """مثال استخدام الوكلاء."""
    print("\n" + "="*60)
    print("Example 2: Agent Usage")
    print("="*60)

    from distributed_cluster.ai.llm import OllamaProvider
    from distributed_cluster.ai.agents import Agent, AgentTask
    from distributed_cluster.ai.agents.tools import (
        CalculatorTool,
        MemoryTool,
        FileTool,
    )

    provider = OllamaProvider()

    healthy = await provider.health_check()
    if not healthy:
        print("⚠️  Ollama is not running")
        return

    # Create agent with specific tools
    agent = Agent(
        name="calculator_agent",
        llm_provider=provider,
        model="llama3.2",
        tools=[
            CalculatorTool(),
            MemoryTool(),
        ],
        system_prompt="You are a helpful math assistant.",
    )

    # Execute a task
    print("\n🤖 Running agent...")

    result = await agent.run(
        "Calculate the square root of 144 and store it in memory as 'sqrt_result'",
        max_iterations=5,
    )

    print(f"\nResult: {result.result}")
    print(f"Status: {result.status.value}")
    print(f"Iterations: {result.iterations}")

    # Show steps
    print("\nSteps:")
    for i, step in enumerate(result.steps, 1):
        print(f"  {i}. {step.thought[:50]}...")
        if step.action:
            print(f"     Action: {step.action}")

    await provider.close()


# =============================================================================
# Example 3: Conversation Management
# =============================================================================

async def conversation_example():
    """مثال إدارة المحادثات."""
    print("\n" + "="*60)
    print("Example 3: Conversation Management")
    print("="*60)

    from distributed_cluster.ai.llm import OllamaProvider
    from distributed_cluster.ai.chat import ConversationManager

    provider = OllamaProvider()

    healthy = await provider.health_check()
    if not healthy:
        print("⚠️  Ollama is not running")
        return

    # Create conversation manager
    manager = ConversationManager(
        llm_provider=provider,
        default_model="llama3.2",
        default_system_prompt="You are a friendly assistant. Keep responses brief.",
    )

    # Create a new conversation
    conv = manager.create_conversation(title="Test Conversation")

    print(f"\n📝 Conversation ID: {conv.conversation_id}")

    # Chat
    messages = [
        "Hello! My name is Ahmed.",
        "What's my name?",
    ]

    for msg in messages:
        print(f"\n👤 User: {msg}")

        response = await manager.chat(conv, msg)

        print(f"🤖 Assistant: {response.content}")

    # Show conversation stats
    print(f"\n📊 Stats:")
    print(f"  Messages: {conv.message_count}")
    print(f"  Total tokens: {conv.total_tokens}")

    await provider.close()


# =============================================================================
# Example 4: Streaming Response
# =============================================================================

async def streaming_example():
    """مثال الاستجابة المتدفقة."""
    print("\n" + "="*60)
    print("Example 4: Streaming Response")
    print("="*60)

    from distributed_cluster.ai.llm import OllamaProvider

    provider = OllamaProvider()

    healthy = await provider.health_check()
    if not healthy:
        print("⚠️  Ollama is not running")
        return

    print("\n💬 Streaming response...")
    print("-" * 40)

    async for chunk in provider.generate_stream(
        prompt="Count from 1 to 5 with a brief description for each number.",
        model="llama3.2",
    ):
        print(chunk, end="", flush=True)

    print("\n" + "-" * 40)

    await provider.close()


# =============================================================================
# Example 5: Inference Router (Multi-node)
# =============================================================================

async def inference_router_example():
    """مثال موجه الاستنتاج."""
    print("\n" + "="*60)
    print("Example 5: Inference Router (Load Balancing)")
    print("="*60)

    from distributed_cluster.ai.inference import InferenceRouter, RoutingStrategy

    # Create router with round-robin strategy
    router = InferenceRouter(strategy=RoutingStrategy.ROUND_ROBIN)

    # Add a single node (in production, add multiple nodes)
    print("\n🔗 Adding inference node...")

    try:
        node = await router.add_node(
            url="http://localhost:11434",
            provider_type="ollama",
            name="local-ollama",
        )

        if not node.healthy:
            print("⚠️  Node is not healthy")
            return

        print(f"✓ Node added: {node.name}")
        print(f"  Models: {node.models[:3]}...")

        # Start router
        await router.start()

        # Generate through router (would load balance with multiple nodes)
        print("\n💬 Generating through router...")

        response = await router.generate(
            prompt="What is 2+2?",
            model="llama3.2",
        )

        print(f"Response: {response.text}")

        # Show node stats
        print("\n📊 Node stats:")
        for node_info in router.list_nodes():
            print(f"  {node_info['name']}: {node_info['metrics']['requests_total']} requests")

    finally:
        await router.stop()


# =============================================================================
# Example 6: Model Registry
# =============================================================================

async def model_registry_example():
    """مثال سجل النماذج."""
    print("\n" + "="*60)
    print("Example 6: Model Registry")
    print("="*60)

    from distributed_cluster.ai.models import ModelRegistry

    # Create registry
    registry = ModelRegistry()

    # Sync models from Ollama
    print("\n📦 Syncing models from Ollama...")

    try:
        synced = await registry.sync_from_ollama()
        print(f"✓ Synced {len(synced)} models")

        # List models
        print("\nAvailable models:")
        for model in registry.list_models()[:5]:
            print(f"  - {model.model_id}")
            print(f"    Name: {model.name}")
            print(f"    Source: {model.source.value}")

        # Get registry stats
        stats = registry.get_stats()
        print(f"\n📊 Registry stats:")
        print(f"  Total models: {stats['total_models']}")
        print(f"  By source: {stats['by_source']}")

    except Exception as e:
        print(f"⚠️  Could not sync: {e}")


# =============================================================================
# Main
# =============================================================================

async def main():
    """Run all examples."""
    print("🤖 Distributed AI System Examples")
    print("="*60)

    examples = [
        ("Basic LLM", basic_llm_example),
        ("Agent", agent_example),
        ("Conversation", conversation_example),
        ("Streaming", streaming_example),
        ("Inference Router", inference_router_example),
        ("Model Registry", model_registry_example),
    ]

    print("\nSelect an example to run:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    print(f"  0. Run all")

    try:
        choice = input("\nEnter choice (0-6): ").strip()

        if choice == "0":
            for name, func in examples:
                await func()
        elif choice.isdigit() and 1 <= int(choice) <= len(examples):
            _, func = examples[int(choice) - 1]
            await func()
        else:
            print("Invalid choice")

    except KeyboardInterrupt:
        print("\n\nExiting...")


if __name__ == "__main__":
    asyncio.run(main())
