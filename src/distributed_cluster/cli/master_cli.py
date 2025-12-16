"""
Master CLI - واجهة سطر الأوامر للـ Master
==========================================

أوامر تشغيل وإدارة Master node.
"""

from pathlib import Path
from typing import Optional
import logging

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="dc-master",
    help="Distributed Cluster Master - Control Plane",
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
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8765, "--port", "-p", help="Port to bind to"),
    log_level: str = typer.Option("INFO", "--log-level", "-l", help="Log level"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """
    بدء Master server.

    مثال:
        dc-master start --port 8765
    """
    setup_logging(log_level)

    from distributed_cluster.core.config import MasterConfig, ClusterConfig
    from distributed_cluster.master.server import MasterServer

    # Load config
    if config and config.exists():
        cluster_config = ClusterConfig.load(config)
        master_config = cluster_config.master
    else:
        master_config = MasterConfig()

    # Override from CLI
    master_config.host = host
    master_config.port = port
    master_config.log_level = log_level

    console.print(f"[bold green]Starting Master on {host}:{port}...[/bold green]")
    console.print(f"  API: http://{host}:{port}/docs")
    console.print(f"  WebSocket: ws://{host}:{port}/ws")

    server = MasterServer(master_config)
    server.run()


@app.command()
def status(
    master_url: str = typer.Option(
        "http://localhost:8765", "--master", "-m", help="Master URL"
    ),
) -> None:
    """
    عرض حالة الكلاستر.

    مثال:
        dc-master status
    """
    import httpx

    try:
        response = httpx.get(f"{master_url}/stats", timeout=10)
        response.raise_for_status()
        stats = response.json()

        console.print("\n[bold]Cluster Status[/bold]\n")

        # Workers table
        table = Table(title="Resources")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Active Workers", str(stats.get("active_workers", 0)))
        table.add_row("Total Workers", str(stats.get("total_workers", 0)))
        table.add_row("Total CPU Cores", f"{stats.get('total_cpu_cores', 0):.1f}")
        table.add_row("Available CPU Cores", f"{stats.get('available_cpu_cores', 0):.1f}")
        table.add_row("Total Memory", f"{stats.get('total_memory_gb', 0):.1f} GB")
        table.add_row("Available Memory", f"{stats.get('available_memory_gb', 0):.1f} GB")
        table.add_row("Total GPUs", str(stats.get("total_gpus", 0)))
        table.add_row("Available GPUs", str(stats.get("available_gpus", 0)))

        console.print(table)

        # Jobs table
        table2 = Table(title="\nJobs")
        table2.add_column("Status", style="cyan")
        table2.add_column("Count", style="green")

        table2.add_row("Pending", str(stats.get("pending_jobs", 0)))
        table2.add_row("Running", str(stats.get("running_jobs", 0)))
        table2.add_row("Completed", str(stats.get("completed_jobs", 0)))
        table2.add_row("Failed", str(stats.get("failed_jobs", 0)))
        table2.add_row("Total Submitted", str(stats.get("total_jobs_submitted", 0)))

        console.print(table2)

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to master[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def workers(
    master_url: str = typer.Option(
        "http://localhost:8765", "--master", "-m", help="Master URL"
    ),
) -> None:
    """
    عرض قائمة workers.

    مثال:
        dc-master workers
    """
    import httpx

    try:
        response = httpx.get(f"{master_url}/workers", timeout=10)
        response.raise_for_status()
        data = response.json()

        workers = data.get("workers", [])

        if not workers:
            console.print("[yellow]No workers registered[/yellow]")
            return

        table = Table(title="Workers")
        table.add_column("ID", style="cyan")
        table.add_column("Hostname", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("CPU", style="blue")
        table.add_column("Memory", style="blue")
        table.add_column("GPU", style="magenta")
        table.add_column("Active Jobs")

        for w in workers:
            status_color = "green" if w["status"] == "ready" else "red"
            table.add_row(
                w["worker_id"][:16],
                w["hostname"],
                f"[{status_color}]{w['status']}[/{status_color}]",
                f"{w['available_resources']['cpu_cores']:.1f}/{w['total_resources']['cpu_cores']:.1f}",
                f"{w['available_resources']['memory_mb']}/{w['total_resources']['memory_mb']} MB",
                f"{w['available_resources']['gpu_count']}/{w['total_resources']['gpu_count']}",
                str(len(w.get("active_jobs", []))),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def jobs(
    master_url: str = typer.Option(
        "http://localhost:8765", "--master", "-m", help="Master URL"
    ),
    status_filter: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of jobs to show"),
) -> None:
    """
    عرض قائمة jobs.

    مثال:
        dc-master jobs --status running
    """
    import httpx

    try:
        params = {"limit": limit}
        if status_filter:
            params["status"] = status_filter

        response = httpx.get(f"{master_url}/jobs", params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        jobs_list = data.get("jobs", [])

        if not jobs_list:
            console.print("[yellow]No jobs found[/yellow]")
            return

        table = Table(title="Jobs")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Worker", style="blue")
        table.add_column("Time", style="magenta")

        for j in jobs_list:
            status = j["status"]
            if status == "completed":
                status_display = "[green]completed[/green]"
            elif status == "failed":
                status_display = "[red]failed[/red]"
            elif status == "running":
                status_display = "[yellow]running[/yellow]"
            else:
                status_display = status

            time_display = ""
            if j.get("execution_time_seconds"):
                time_display = f"{j['execution_time_seconds']:.1f}s"
            elif j.get("wait_time_seconds"):
                time_display = f"wait: {j['wait_time_seconds']:.0f}s"

            table.add_row(
                j["job_id"][:16],
                j.get("name", "")[:20],
                status_display,
                (j.get("assigned_worker") or "-")[:16],
                time_display,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
