"""
AI CLI - واجهة سطر الأوامر للذكاء الاصطناعي
============================================

Command-line interface for AI features:
- Chat with models
- Manage agents
- Run distributed inference
- Model management
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

app = typer.Typer(
    name="dc-ai",
    help="🤖 واجهة الذكاء الاصطناعي الموزع - Distributed AI Interface",
    no_args_is_help=True,
)

console = Console()

# Sub-apps
chat_app = typer.Typer(help="💬 المحادثة - Chat commands")
model_app = typer.Typer(help="📦 النماذج - Model management")
agent_app = typer.Typer(help="🤖 الوكلاء - Agent commands")
inference_app = typer.Typer(help="⚡ الاستنتاج - Inference commands")

app.add_typer(chat_app, name="chat")
app.add_typer(model_app, name="model")
app.add_typer(agent_app, name="agent")
app.add_typer(inference_app, name="inference")


# =============================================================================
# Chat Commands
# =============================================================================


@chat_app.command("start")
def chat_start(
    model: str = typer.Option("llama3.2", "--model", "-m", help="Model to use"),
    system_prompt: Optional[str] = typer.Option(None, "--system", "-s", help="System prompt"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
):
    """
    بدء محادثة تفاعلية - Start interactive chat
    """
    console.print(
        Panel.fit(
            f"[bold green]🤖 بدء المحادثة مع {model}[/bold green]\n" f"[dim]اكتب 'exit' أو 'خروج' للخروج[/dim]",
            title="AI Chat",
        )
    )

    async def run_chat():
        from distributed_cluster.ai.chat.conversation import ConversationManager
        from distributed_cluster.ai.llm.provider import OllamaProvider

        # Create provider
        provider = OllamaProvider(base_url=ollama_url)

        # Check health
        healthy = await provider.health_check()
        if not healthy:
            console.print(f"[red]❌ Cannot connect to Ollama at {ollama_url}[/red]")
            return

        # Create conversation
        manager = ConversationManager(llm_provider=provider, default_model=model)
        conv = manager.create_conversation(
            system_prompt=system_prompt or "You are a helpful AI assistant. Respond concisely.",
        )

        console.print(f"[green]✓ Connected to {model}[/green]\n")

        while True:
            try:
                # Get user input
                user_input = Prompt.ask("\n[bold blue]أنت[/bold blue]")

                if user_input.lower() in ["exit", "quit", "خروج", "q"]:
                    console.print("[yellow]👋 مع السلامة![/yellow]")
                    break

                if not user_input.strip():
                    continue

                # Stream response
                console.print("\n[bold green]المساعد[/bold green]: ", end="")

                full_response = []
                async for chunk in manager.chat_stream(conv, user_input):
                    console.print(chunk, end="")
                    full_response.append(chunk)

                console.print()

            except KeyboardInterrupt:
                console.print("\n[yellow]👋 مع السلامة![/yellow]")
                break
            except Exception as e:
                console.print(f"\n[red]Error: {e}[/red]")

        await provider.close()

    asyncio.run(run_chat())


@chat_app.command("send")
def chat_send(
    message: str = typer.Argument(..., help="Message to send"),
    model: str = typer.Option("llama3.2", "--model", "-m", help="Model to use"),
    system_prompt: Optional[str] = typer.Option(None, "--system", "-s", help="System prompt"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    إرسال رسالة واحدة - Send a single message
    """

    async def run():
        from distributed_cluster.ai.llm.provider import OllamaProvider

        provider = OllamaProvider(base_url=ollama_url)

        try:
            response = await provider.generate(
                prompt=message,
                model=model,
                system_prompt=system_prompt,
            )

            if json_output:
                console.print_json(
                    json.dumps(
                        {
                            "text": response.text,
                            "model": response.model,
                            "tokens": response.total_tokens,
                            "time_ms": response.generation_time_ms,
                        }
                    )
                )
            else:
                console.print(Markdown(response.text))

        finally:
            await provider.close()

    asyncio.run(run())


# =============================================================================
# Model Commands
# =============================================================================


@model_app.command("list")
def model_list(
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    عرض النماذج المتاحة - List available models
    """

    async def run():
        from distributed_cluster.ai.llm.provider import OllamaProvider

        provider = OllamaProvider(base_url=ollama_url)

        try:
            models = await provider.list_models()

            if json_output:
                console.print_json(
                    json.dumps(
                        [
                            {
                                "name": m.name,
                                "size_gb": round(m.size_bytes / 1e9, 2),
                                "parameter_size": m.parameter_size,
                                "quantization": m.quantization,
                            }
                            for m in models
                        ]
                    )
                )
            else:
                table = Table(title="📦 النماذج المتاحة - Available Models")
                table.add_column("Name", style="cyan")
                table.add_column("Size", style="green")
                table.add_column("Parameters", style="yellow")
                table.add_column("Quantization", style="magenta")

                for m in models:
                    size_gb = f"{m.size_bytes / 1e9:.1f} GB" if m.size_bytes else "N/A"
                    table.add_row(
                        m.name,
                        size_gb,
                        m.parameter_size or "N/A",
                        m.quantization or "N/A",
                    )

                console.print(table)

        finally:
            await provider.close()

    asyncio.run(run())


@model_app.command("pull")
def model_pull(
    model_name: str = typer.Argument(..., help="Model name to pull"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
):
    """
    تحميل نموذج - Pull a model
    """

    async def run():
        from distributed_cluster.ai.llm.provider import OllamaProvider

        provider = OllamaProvider(base_url=ollama_url)

        console.print(f"[cyan]📥 Pulling {model_name}...[/cyan]")

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(f"Downloading {model_name}...", total=None)

                async for update in provider.pull_model(model_name):
                    status = update.get("status", "")
                    completed = update.get("completed", 0)
                    total = update.get("total", 0)

                    if total > 0:
                        progress.update(task, description=f"{status}: {completed/1e9:.1f}/{total/1e9:.1f} GB")
                    else:
                        progress.update(task, description=status)

            console.print(f"[green]✓ Successfully pulled {model_name}[/green]")

        except Exception as e:
            console.print(f"[red]❌ Failed to pull {model_name}: {e}[/red]")

        finally:
            await provider.close()

    asyncio.run(run())


@model_app.command("delete")
def model_delete(
    model_name: str = typer.Argument(..., help="Model name to delete"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """
    حذف نموذج - Delete a model
    """
    if not force:
        confirm = Prompt.ask(f"Are you sure you want to delete '{model_name}'?", choices=["y", "n"])
        if confirm != "y":
            console.print("[yellow]Cancelled[/yellow]")
            return

    async def run():
        from distributed_cluster.ai.llm.provider import OllamaProvider

        provider = OllamaProvider(base_url=ollama_url)

        try:
            success = await provider.delete_model(model_name)
            if success:
                console.print(f"[green]✓ Deleted {model_name}[/green]")
            else:
                console.print(f"[red]❌ Failed to delete {model_name}[/red]")

        finally:
            await provider.close()

    asyncio.run(run())


# =============================================================================
# Agent Commands
# =============================================================================


@agent_app.command("run")
def agent_run(
    task: str = typer.Argument(..., help="Task description"),
    model: str = typer.Option("llama3.2", "--model", "-m", help="Model to use"),
    agent_type: str = typer.Option("assistant", "--type", "-t", help="Agent type (assistant, coder, researcher)"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    max_iterations: int = typer.Option(10, "--max-iter", help="Maximum iterations"),
):
    """
    تشغيل وكيل لتنفيذ مهمة - Run an agent to execute a task
    """

    async def run():
        from distributed_cluster.ai.agents.base import Agent, AgentTask
        from distributed_cluster.ai.agents.tools import get_default_tools
        from distributed_cluster.ai.llm.provider import OllamaProvider

        provider = OllamaProvider(base_url=ollama_url)

        try:
            # Check health
            healthy = await provider.health_check()
            if not healthy:
                console.print(f"[red]❌ Cannot connect to Ollama at {ollama_url}[/red]")
                return

            # Create agent
            agent = Agent(
                name=agent_type,
                llm_provider=provider,
                model=model,
                tools=get_default_tools(),
            )

            console.print(f"[cyan]🤖 Running {agent_type} agent...[/cyan]\n")

            # Create task
            agent_task = AgentTask(
                description=task,
                max_iterations=max_iterations,
            )

            # Execute
            with console.status("[bold green]Thinking...[/bold green]"):
                result = await agent.execute_task(agent_task)

            # Show results
            if result.is_success:
                console.print(
                    Panel(
                        Markdown(str(result.result)),
                        title="✅ Result",
                        border_style="green",
                    )
                )
            else:
                console.print(
                    Panel(
                        f"[red]{result.error}[/red]",
                        title="❌ Failed",
                        border_style="red",
                    )
                )

            # Show steps
            if result.steps:
                console.print("\n[bold]Steps:[/bold]")
                for i, step in enumerate(result.steps, 1):
                    if step.thought:
                        console.print(f"  {i}. [dim]{step.thought[:100]}...[/dim]")

            tokens = result.total_tokens
            time_ms = result.total_time_ms
            iters = result.iterations
            console.print(f"\n[dim]Tokens: {tokens} | Time: {time_ms:.0f}ms | Iterations: {iters}[/dim]")

        finally:
            await provider.close()

    asyncio.run(run())


@agent_app.command("list")
def agent_list():
    """
    عرض الوكلاء المتاحين - List available agents
    """
    table = Table(title="🤖 الوكلاء المتاحين - Available Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Tools", style="green")

    agents = [
        ("assistant", "General purpose assistant", "all"),
        ("coder", "Software development specialist", "shell, file, python"),
        ("researcher", "Research and information gathering", "web_search, web_fetch"),
    ]

    for name, desc, tools in agents:
        table.add_row(name, desc, tools)

    console.print(table)


# =============================================================================
# Inference Commands
# =============================================================================


@inference_app.command("start-worker")
def inference_start_worker(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind"),
    port: int = typer.Option(8080, "--port", "-p", help="Port to bind"),
    provider: str = typer.Option("ollama", "--provider", help="LLM provider (ollama, vllm)"),
    llm_url: str = typer.Option("http://localhost:11434", "--llm-url", help="LLM backend URL"),
    master_url: Optional[str] = typer.Option(None, "--master", help="Master URL for registration"),
):
    """
    بدء عامل استنتاج - Start an inference worker
    """
    from distributed_cluster.ai.inference.worker import InferenceWorker, WorkerConfig

    config = WorkerConfig(
        host=host,
        port=port,
        llm_provider=provider,
        llm_url=llm_url,
        master_url=master_url,
    )

    console.print(f"[cyan]⚡ Starting inference worker on {host}:{port}[/cyan]")
    console.print(f"[dim]Provider: {provider} @ {llm_url}[/dim]")

    worker = InferenceWorker(config)
    worker.run()


@inference_app.command("test")
def inference_test(
    prompt: str = typer.Argument(..., help="Test prompt"),
    worker_url: str = typer.Option("http://localhost:8080", "--url", help="Worker URL"),
    model: str = typer.Option("llama3.2", "--model", "-m", help="Model to use"),
):
    """
    اختبار عامل استنتاج - Test an inference worker
    """
    import httpx

    async def run():
        async with httpx.AsyncClient() as client:
            try:
                # Health check
                health = await client.get(f"{worker_url}/health", timeout=5.0)
                health_data = health.json()

                if health_data.get("status") != "healthy":
                    console.print(f"[yellow]⚠ Worker is {health_data.get('status')}[/yellow]")

                # Generate
                console.print("[cyan]Testing generation...[/cyan]")

                response = await client.post(
                    f"{worker_url}/generate",
                    json={
                        "prompt": prompt,
                        "model": model,
                        "max_tokens": 100,
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

                console.print(
                    Panel(
                        data.get("text", ""),
                        title="Response",
                        border_style="green",
                    )
                )

                console.print(f"[dim]Tokens: {data.get('tokens')} | Time: {data.get('generation_time_ms'):.0f}ms[/dim]")

            except Exception as e:
                console.print(f"[red]❌ Error: {e}[/red]")

    asyncio.run(run())


# =============================================================================
# Main Commands
# =============================================================================


@app.command("status")
def status(
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
):
    """
    عرض حالة النظام - Show system status
    """
    import httpx

    async def run():
        console.print("[bold]🔍 Checking AI system status...[/bold]\n")

        # Check Ollama
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{ollama_url}/", timeout=5.0)
                ollama_status = "✅ Online" if response.status_code == 200 else "⚠ Degraded"
        except Exception:
            ollama_status = "❌ Offline"

        table = Table(title="System Status")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("URL", style="dim")

        table.add_row("Ollama", ollama_status, ollama_url)

        console.print(table)

    asyncio.run(run())


@app.command("version")
def version():
    """
    عرض الإصدار - Show version
    """
    console.print("[bold cyan]theEnd AI Module[/bold cyan]")
    console.print("Version: 0.1.0")
    console.print("Components: LLM, Agents, Chat, Inference, Registry")


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
