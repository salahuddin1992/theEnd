"""
Worker CLI - واجهة سطر الأوامر للـ Worker
==========================================

أوامر تشغيل وإدارة Worker node.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="dc-worker",
    help="Distributed Cluster Worker Agent",
    add_completion=False,
)
console = Console()


def setup_logging(level: str) -> None:
    """إعداد التسجيل."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


@app.command()
def start(
    master_url: str = typer.Option("http://localhost:8765", "--master", "-m", help="Master URL"),
    port: int = typer.Option(8766, "--port", "-p", help="Worker port"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Worker name"),
    work_dir: Path = typer.Option(Path("./worker_jobs"), "--work-dir", "-w", help="Working directory"),
    no_docker: bool = typer.Option(False, "--no-docker", help="Disable Docker"),
    log_level: str = typer.Option("INFO", "--log-level", "-l", help="Log level"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """
    بدء Worker Agent.

    مثال:
        dc-worker start --master http://master:8765 --tags gpu,high-memory
    """
    setup_logging(log_level)

    from distributed_cluster.core.config import ClusterConfig, WorkerConfig
    from distributed_cluster.worker.agent import run_worker

    # Load config
    if config and config.exists():
        cluster_config = ClusterConfig.load(config)
        worker_config = cluster_config.worker
    else:
        worker_config = WorkerConfig()

    # Override from CLI
    worker_config.master_url = master_url
    worker_config.port = port
    worker_config.work_dir = work_dir
    worker_config.docker_enabled = not no_docker
    worker_config.log_level = log_level

    if name:
        worker_config.worker_name = name

    if tags:
        worker_config.tags = [t.strip() for t in tags.split(",")]

    console.print("[bold green]Starting Worker Agent...[/bold green]")
    console.print(f"  Master: {master_url}")
    console.print(f"  Tags: {worker_config.tags or 'none'}")
    console.print(f"  Docker: {'enabled' if worker_config.docker_enabled else 'disabled'}")

    try:
        asyncio.run(run_worker(worker_config))
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker stopped[/yellow]")


@app.command()
def info() -> None:
    """
    عرض معلومات الجهاز المحلي.

    مثال:
        dc-worker info
    """
    from rich.table import Table

    from distributed_cluster.core.resource_detector import ResourceDetector

    detector = ResourceDetector()
    info = detector.get_system_info()
    resources = detector.get_total_resources()
    usage = detector.get_current_usage()

    console.print("\n[bold]System Information[/bold]\n")

    table = Table(title="System")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Hostname", info["hostname"])
    table.add_row("IP Address", info["ip_address"])
    table.add_row("Platform", info["platform"])
    table.add_row("Python", info["python_version"])
    table.add_row("Docker", "✓" if info["docker_available"] else "✗")

    console.print(table)

    # Resources
    table2 = Table(title="\nResources")
    table2.add_column("Resource", style="cyan")
    table2.add_column("Total", style="green")
    table2.add_column("Current Usage", style="yellow")

    table2.add_row(
        "CPU Cores",
        str(int(resources.cpu_cores)),
        f"{usage.cpu_percent:.1f}%",
    )
    table2.add_row(
        "Memory",
        f"{resources.memory_mb} MB",
        f"{usage.memory_used_mb}/{usage.memory_total_mb} MB ({usage.memory_percent:.1f}%)",
    )
    table2.add_row(
        "GPUs",
        str(resources.gpu_count),
        "-" if not usage.gpus else f"{len(usage.gpus)} detected",
    )

    console.print(table2)

    # GPU details
    if usage.gpus:
        table3 = Table(title="\nGPU Details")
        table3.add_column("Index", style="cyan")
        table3.add_column("Name", style="green")
        table3.add_column("Memory", style="yellow")
        table3.add_column("Utilization", style="magenta")
        table3.add_column("Temp", style="red")

        for gpu in usage.gpus:
            table3.add_row(
                str(gpu.index),
                gpu.name[:30],
                f"{gpu.memory_used_mb}/{gpu.memory_total_mb} MB",
                f"{gpu.utilization_percent:.1f}%",
                f"{gpu.temperature_c}°C" if gpu.temperature_c else "-",
            )

        console.print(table3)


if __name__ == "__main__":
    app()
