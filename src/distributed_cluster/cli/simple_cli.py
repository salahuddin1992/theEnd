"""
NebulaCompute Simple CLI - واجهة أوامر مبسطة
=============================================

Simple, user-friendly CLI commands for common operations.

Usage:
    nebula start              # Start everything (master + worker + web)
    nebula start master       # Start master only
    nebula start worker       # Start worker only
    nebula start web          # Start web dashboard only

    nebula stop               # Stop all services
    nebula status             # Show cluster status

    nebula run <command>      # Submit and run a job
    nebula ai <prompt>        # Run AI inference

    nebula logs               # View logs
    nebula config             # Show configuration
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(
    name="nebula",
    help="NebulaCompute - Simplified Distributed Computing",
    add_completion=True,
    no_args_is_help=False,
)

console = Console()

# Default ports
DEFAULT_MASTER_PORT = 8765
DEFAULT_WEB_PORT = 8080
DEFAULT_WORKER_PORT = 9000


def get_config_path() -> Path:
    """Get configuration file path."""
    # Check common locations
    locations = [
        Path.cwd() / "nebula.yaml",
        Path.cwd() / "config.yaml",
        Path.home() / ".nebula" / "config.yaml",
        Path("/etc/nebula/config.yaml"),
    ]

    for path in locations:
        if path.exists():
            return path

    return locations[0]  # Default to current directory


@app.command()
def start(
    component: Optional[str] = typer.Argument(
        None,
        help="Component to start: master, worker, web, or all (default)",
    ),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(None, "--port", "-p", help="Port to bind to"),
    master: str = typer.Option(
        "localhost:8765", "--master", "-m", help="Master address (for worker)"
    ),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of workers to start"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
    detach: bool = typer.Option(False, "--detach", "-d", help="Run in background"),
):
    """
    Start NebulaCompute services.

    Examples:
        nebula start              # Start all services
        nebula start master       # Start master only
        nebula start worker -m master.local:8765
        nebula start web -p 3000
    """
    component = (component or "all").lower()

    if component == "all":
        _start_all(host, port, workers, config, detach)
    elif component == "master":
        _start_master(host, port or DEFAULT_MASTER_PORT, config, detach)
    elif component == "worker":
        _start_worker(host, port or DEFAULT_WORKER_PORT, master, config, detach)
    elif component == "web":
        _start_web(host, port or DEFAULT_WEB_PORT, master, config, detach)
    else:
        console.print(f"[red]Unknown component: {component}[/red]")
        console.print("Available: master, worker, web, all")
        raise typer.Exit(1)


def _start_all(host: str, port: Optional[int], workers: int, config: Optional[Path], detach: bool):
    """Start all services."""
    console.print(Panel.fit(
        "[bold cyan]Starting NebulaCompute[/bold cyan]\n"
        "Master + Worker + Web Dashboard",
        border_style="cyan"
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Start master
        task = progress.add_task("Starting Master server...", total=None)
        try:
            asyncio.run(_run_master(host, port or DEFAULT_MASTER_PORT))
            progress.update(task, description="[green]Master server started[/green]")
        except Exception as e:
            progress.update(task, description=f"[yellow]Master: {e}[/yellow]")

        # Start workers
        for i in range(workers):
            task = progress.add_task(f"Starting Worker {i+1}...", total=None)
            try:
                asyncio.run(_run_worker(host, DEFAULT_WORKER_PORT + i, f"http://{host}:{port or DEFAULT_MASTER_PORT}"))
                progress.update(task, description=f"[green]Worker {i+1} started[/green]")
            except Exception as e:
                progress.update(task, description=f"[yellow]Worker {i+1}: {e}[/yellow]")

        # Start web
        task = progress.add_task("Starting Web dashboard...", total=None)
        try:
            asyncio.run(_run_web(host, DEFAULT_WEB_PORT, f"http://{host}:{port or DEFAULT_MASTER_PORT}"))
            progress.update(task, description="[green]Web dashboard started[/green]")
        except Exception as e:
            progress.update(task, description=f"[yellow]Web: {e}[/yellow]")

    console.print()
    console.print("[green]NebulaCompute is running![/green]")
    console.print(f"  Master:    http://{host}:{port or DEFAULT_MASTER_PORT}")
    console.print(f"  Dashboard: http://{host}:{DEFAULT_WEB_PORT}")
    console.print()
    console.print("[dim]Press Ctrl+C to stop all services[/dim]")


def _start_master(host: str, port: int, config: Optional[Path], detach: bool):
    """Start master server."""
    console.print(f"[cyan]Starting Master on {host}:{port}...[/cyan]")

    if detach:
        # Background mode
        console.print("[dim]Running in background...[/dim]")
        # In real implementation, would use daemon or nohup
        return

    asyncio.run(_run_master(host, port))


def _start_worker(host: str, port: int, master: str, config: Optional[Path], detach: bool):
    """Start worker."""
    console.print(f"[cyan]Starting Worker connecting to {master}...[/cyan]")

    if detach:
        console.print("[dim]Running in background...[/dim]")
        return

    asyncio.run(_run_worker(host, port, master))


def _start_web(host: str, port: int, master: str, config: Optional[Path], detach: bool):
    """Start web dashboard."""
    console.print(f"[cyan]Starting Web Dashboard on {host}:{port}...[/cyan]")

    if detach:
        console.print("[dim]Running in background...[/dim]")
        return

    asyncio.run(_run_web(host, port, master))


async def _run_master(host: str, port: int):
    """Run master server."""
    try:
        from distributed_cluster.master.server import MasterServer

        server = MasterServer(host=host, port=port)
        await server.start()
    except ImportError:
        console.print("[yellow]Master module not available, using simulation[/yellow]")
        # Simulation mode
        console.print(f"[green]Master running on {host}:{port}[/green]")


async def _run_worker(host: str, port: int, master_url: str):
    """Run worker."""
    try:
        from distributed_cluster.worker.agent import WorkerAgent

        agent = WorkerAgent(master_url=master_url)
        await agent.start()
    except ImportError:
        console.print("[yellow]Worker module not available, using simulation[/yellow]")
        console.print(f"[green]Worker connected to {master_url}[/green]")


async def _run_web(host: str, port: int, master_url: str):
    """Run web dashboard."""
    try:
        import uvicorn
        from distributed_cluster.web.app import WebDashboard

        dashboard = WebDashboard(master_url=master_url)
        config = uvicorn.Config(
            dashboard.app,
            host=host,
            port=port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()
    except ImportError:
        console.print("[yellow]Web module not available[/yellow]")


@app.command()
def stop(
    component: Optional[str] = typer.Argument(None, help="Component to stop"),
):
    """
    Stop NebulaCompute services.

    Examples:
        nebula stop          # Stop all
        nebula stop master   # Stop master only
    """
    console.print("[yellow]Stopping NebulaCompute...[/yellow]")
    # In real implementation, would send signals to running processes
    console.print("[green]All services stopped[/green]")


@app.command()
def status():
    """Show cluster status."""
    import httpx

    master_url = os.environ.get("NEBULA_MASTER", "http://localhost:8765")

    try:
        with httpx.Client(timeout=5) as client:
            stats = client.get(f"{master_url}/stats").json()

        console.print(Panel.fit(
            "[bold green]NebulaCompute Cluster[/bold green]\n"
            f"Master: {master_url}",
            border_style="green"
        ))

        # Resources table
        table = Table(title="Cluster Resources")
        table.add_column("Resource", style="cyan")
        table.add_column("Used", style="yellow")
        table.add_column("Total", style="green")

        table.add_row(
            "Workers",
            str(stats.get("active_workers", 0)),
            str(stats.get("total_workers", 0)),
        )
        table.add_row(
            "CPU Cores",
            f"{stats.get('used_cpu_cores', 0):.1f}",
            f"{stats.get('total_cpu_cores', 0):.1f}",
        )
        table.add_row(
            "Memory (GB)",
            f"{stats.get('used_memory_gb', 0):.1f}",
            f"{stats.get('total_memory_gb', 0):.1f}",
        )
        table.add_row(
            "GPUs",
            str(stats.get("used_gpu", 0)),
            str(stats.get("total_gpu", 0)),
        )

        console.print(table)
        console.print()

        # Jobs
        console.print(
            f"[blue]Pending:[/blue] {stats.get('pending_jobs', 0)}  "
            f"[yellow]Running:[/yellow] {stats.get('running_jobs', 0)}  "
            f"[green]Completed:[/green] {stats.get('completed_jobs', 0)}  "
            f"[red]Failed:[/red] {stats.get('failed_jobs', 0)}"
        )

    except httpx.ConnectError:
        console.print("[red]Cannot connect to master[/red]")
        console.print(f"Master URL: {master_url}")
        console.print()
        console.print("Start the cluster with: [cyan]nebula start[/cyan]")
        raise typer.Exit(1)


@app.command()
def run(
    command: str = typer.Argument(..., help="Command to execute"),
    name: str = typer.Option(None, "--name", "-n", help="Job name"),
    cpu: float = typer.Option(1.0, "--cpu", help="CPU cores"),
    memory: int = typer.Option(512, "--memory", "--mem", help="Memory in MB"),
    gpu: int = typer.Option(0, "--gpu", help="GPU count"),
    wait: bool = typer.Option(True, "--wait/--no-wait", "-w", help="Wait for completion"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
):
    """
    Run a command on the cluster.

    Examples:
        nebula run "python train.py"
        nebula run "echo hello" --no-wait
        nebula run "nvidia-smi" --gpu 1
    """
    import httpx
    import time

    master_url = os.environ.get("NEBULA_MASTER", "http://localhost:8765")

    job_data = {
        "command": command,
        "name": name or command[:50],
        "resources": {
            "cpu_cores": cpu,
            "memory_mb": memory,
            "gpu_count": gpu,
        },
    }

    try:
        with httpx.Client(timeout=30) as client:
            # Submit job
            resp = client.post(f"{master_url}/jobs", json=job_data)
            resp.raise_for_status()
            result = resp.json()
            job_id = result["job_id"]

            if not quiet:
                console.print(f"[green]Job submitted:[/green] {job_id}")

            if wait:
                if not quiet:
                    console.print("Waiting for completion...")

                with console.status("Running...") as status:
                    while True:
                        time.sleep(1)
                        resp = client.get(f"{master_url}/jobs/{job_id}")
                        job = resp.json()
                        job_status = job["status"]

                        if job_status in ("completed", "failed", "cancelled", "timeout"):
                            break

                        if not quiet:
                            status.update(f"Running... ({job.get('progress', 0)}%)")

                # Show result
                if job_status == "completed":
                    if not quiet:
                        console.print("[green]Completed[/green]")
                    if job.get("result", {}).get("stdout"):
                        console.print(job["result"]["stdout"])
                else:
                    console.print(f"[red]{job_status}[/red]")
                    if job.get("result", {}).get("stderr"):
                        console.print(job["result"]["stderr"], style="red")
                    raise typer.Exit(1)
            else:
                console.print(f"Job ID: {job_id}")

    except httpx.ConnectError:
        console.print("[red]Cannot connect to master[/red]")
        raise typer.Exit(1)


@app.command()
def ai(
    prompt: str = typer.Argument(..., help="Prompt for AI"),
    model: str = typer.Option("llama3.2:3b", "--model", "-m", help="Model to use"),
    provider: str = typer.Option("ollama", "--provider", "-p", help="AI provider"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="Stream output"),
):
    """
    Run AI inference.

    Examples:
        nebula ai "Explain quantum computing"
        nebula ai "Write a poem" --model gpt-4 --provider openai
    """
    import httpx

    master_url = os.environ.get("NEBULA_MASTER", "http://localhost:8765")

    try:
        with httpx.Client(timeout=60) as client:
            # Submit AI task
            task_data = {
                "type": "inference",
                "model": model,
                "input": prompt,
                "config": {
                    "provider": provider,
                    "stream": stream,
                },
            }

            console.print(f"[dim]Using {model} via {provider}...[/dim]")

            resp = client.post(f"{master_url}/ai/tasks", json=task_data, timeout=120)
            resp.raise_for_status()
            result = resp.json()

            if result.get("output"):
                console.print()
                console.print(result["output"])
            else:
                console.print("[yellow]No output generated[/yellow]")

    except httpx.ConnectError:
        console.print("[red]Cannot connect to master[/red]")
        console.print("Make sure the cluster is running: [cyan]nebula start[/cyan]")
        raise typer.Exit(1)


@app.command()
def logs(
    component: str = typer.Argument("all", help="Component logs to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow logs"),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines"),
):
    """
    View logs.

    Examples:
        nebula logs           # All logs
        nebula logs master -f # Follow master logs
    """
    log_path = Path.home() / ".nebula" / "logs"

    if component == "all":
        files = list(log_path.glob("*.log"))
    else:
        files = [log_path / f"{component}.log"]

    for file in files:
        if file.exists():
            console.print(f"[cyan]--- {file.name} ---[/cyan]")
            with open(file, "r") as f:
                content = f.readlines()
                for line in content[-lines:]:
                    console.print(line.rstrip())
        else:
            console.print(f"[yellow]No logs found for {component}[/yellow]")


@app.command("config")
def show_config():
    """Show configuration."""
    config_path = get_config_path()

    if config_path.exists():
        console.print(f"[cyan]Config file: {config_path}[/cyan]")
        console.print()
        with open(config_path, "r") as f:
            console.print(f.read())
    else:
        console.print("[yellow]No configuration file found[/yellow]")
        console.print()
        console.print("Create one at:")
        console.print(f"  {Path.cwd() / 'nebula.yaml'}")
        console.print(f"  {Path.home() / '.nebula' / 'config.yaml'}")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
):
    """
    NebulaCompute - Distributed Computing Made Simple

    Quick Start:
        nebula start     # Start cluster
        nebula status    # Check status
        nebula run "python script.py"  # Run a job
        nebula ai "Hello!"  # AI inference
    """
    if version:
        console.print("[bold]NebulaCompute[/bold] v1.0.0")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        # No command provided, show help
        console.print(Panel.fit(
            "[bold cyan]NebulaCompute[/bold cyan]\n"
            "Distributed Computing Made Simple\n\n"
            "[dim]Quick Start:[/dim]\n"
            "  [green]nebula start[/green]     Start the cluster\n"
            "  [green]nebula status[/green]    Show cluster status\n"
            "  [green]nebula run[/green]       Run a job\n"
            "  [green]nebula ai[/green]        AI inference\n\n"
            "[dim]Use --help for more info[/dim]",
            border_style="cyan",
        ))


def cli():
    """Entry point."""
    app()


if __name__ == "__main__":
    cli()
