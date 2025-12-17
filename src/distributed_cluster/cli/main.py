"""
NebulaCompute CLI - Unified Command-Line Interface
===================================================

واجهة سطر أوامر موحدة للتفاعل مع نظام NebulaCompute.
"""

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from typing import Optional
from pathlib import Path
import json
import sys

# Create main app
app = typer.Typer(
    name="nebula",
    help="NebulaCompute - Distributed Computing CLI",
    add_completion=True,
    no_args_is_help=True,
)

# Sub-apps
jobs_app = typer.Typer(help="Manage jobs")
workers_app = typer.Typer(help="Manage workers")
templates_app = typer.Typer(help="Manage job templates")
pools_app = typer.Typer(help="Manage worker pools")
queues_app = typer.Typer(help="Manage priority queues")
secrets_app = typer.Typer(help="Manage secrets")
config_app = typer.Typer(help="Configuration management")

app.add_typer(jobs_app, name="jobs")
app.add_typer(workers_app, name="workers")
app.add_typer(templates_app, name="templates")
app.add_typer(pools_app, name="pools")
app.add_typer(queues_app, name="queues")
app.add_typer(secrets_app, name="secrets")
app.add_typer(config_app, name="config")

# Import and add workflow commands
from distributed_cluster.cli.workflow_cli import workflow_app
app.add_typer(workflow_app, name="workflows")

# Import and add HA commands
from distributed_cluster.cli.ha_cli import app as ha_app
app.add_typer(ha_app, name="ha")

console = Console()

# Default master URL
DEFAULT_MASTER = "http://localhost:8765"


def get_client():
    """Get HTTP client."""
    import httpx
    return httpx.Client(timeout=30)


# =============================================================================
# Main Commands
# =============================================================================

@app.command()
def status(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m", help="Master URL"),
):
    """Show cluster status overview."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            # Get stats
            stats_resp = client.get(f"{master_url}/stats")
            stats_resp.raise_for_status()
            stats = stats_resp.json()

            # Display
            console.print(Panel.fit(
                f"[bold green]NebulaCompute Cluster[/bold green]\n"
                f"Master: {master_url}",
                border_style="green"
            ))

            # Resources
            table = Table(title="Cluster Resources", show_header=True)
            table.add_column("Resource", style="cyan")
            table.add_column("Available", style="green")
            table.add_column("Total", style="blue")
            table.add_column("Usage", style="yellow")

            cpu_avail = stats.get("available_cpu_cores", 0)
            cpu_total = stats.get("total_cpu_cores", 0)
            cpu_pct = (1 - cpu_avail / cpu_total * 100) if cpu_total else 0

            mem_avail = stats.get("available_memory_gb", 0)
            mem_total = stats.get("total_memory_gb", 0)
            mem_pct = (1 - mem_avail / mem_total * 100) if mem_total else 0

            gpu_avail = stats.get("available_gpus", 0)
            gpu_total = stats.get("total_gpus", 0)
            gpu_pct = (1 - gpu_avail / gpu_total * 100) if gpu_total else 0

            table.add_row("CPU Cores", f"{cpu_avail:.1f}", f"{cpu_total:.1f}", f"{cpu_pct:.1f}%")
            table.add_row("Memory", f"{mem_avail:.1f} GB", f"{mem_total:.1f} GB", f"{mem_pct:.1f}%")
            table.add_row("GPUs", str(gpu_avail), str(gpu_total), f"{gpu_pct:.1f}%")
            table.add_row("Workers",
                          str(stats.get("active_workers", 0)),
                          str(stats.get("total_workers", 0)),
                          "-")

            console.print(table)

            # Jobs summary
            console.print()
            jobs_table = Table(title="Jobs Summary", show_header=True)
            jobs_table.add_column("Status", style="cyan")
            jobs_table.add_column("Count", style="green")

            jobs_table.add_row("Pending", f"[blue]{stats.get('pending_jobs', 0)}[/blue]")
            jobs_table.add_row("Running", f"[yellow]{stats.get('running_jobs', 0)}[/yellow]")
            jobs_table.add_row("Completed", f"[green]{stats.get('completed_jobs', 0)}[/green]")
            jobs_table.add_row("Failed", f"[red]{stats.get('failed_jobs', 0)}[/red]")

            console.print(jobs_table)

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to master at {master_url}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    console.print(Panel.fit(
        "[bold]NebulaCompute[/bold] v1.0.0\n"
        "Distributed Computing System\n\n"
        "Components:\n"
        "  - Master Server\n"
        "  - Worker Agent\n"
        "  - CLI Tools\n"
        "  - Dashboard API",
        title="Version Info",
        border_style="blue"
    ))


# =============================================================================
# Jobs Commands
# =============================================================================

@jobs_app.command("submit")
def jobs_submit(
    command: str = typer.Argument(..., help="Command to execute"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Job name"),
    cpu: float = typer.Option(1.0, "--cpu", help="CPU cores"),
    memory: int = typer.Option(512, "--memory", "--mem", help="Memory in MB"),
    gpu: int = typer.Option(0, "--gpu", help="GPU count"),
    docker: Optional[str] = typer.Option(None, "--docker", "-d", help="Docker image"),
    timeout: int = typer.Option(3600, "--timeout", "-t", help="Timeout seconds"),
    priority: int = typer.Option(50, "--priority", "-p", help="Priority (0-200)"),
    queue: Optional[str] = typer.Option(None, "--queue", "-q", help="Queue name"),
    pool: Optional[str] = typer.Option(None, "--pool", help="Worker pool"),
    template: Optional[str] = typer.Option(None, "--template", help="Use template"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Required tags"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Env vars (K=V,...)"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
    output: str = typer.Option("text", "--output", "-o", help="Output format"),
):
    """Submit a new job to the cluster."""
    import httpx
    import time

    # Parse env vars
    environment = {}
    if env:
        for pair in env.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                environment[k.strip()] = v.strip()

    # Parse tags
    required_tags = [t.strip() for t in tags.split(",")] if tags else []

    # Build job data
    job_data = {
        "command": command,
        "name": name or command[:50],
        "resources": {
            "cpu_cores": cpu,
            "memory_mb": memory,
            "gpu_count": gpu,
        },
        "timeout_seconds": timeout,
        "priority": priority,
        "required_tags": required_tags,
        "environment": environment,
    }

    if docker:
        job_data["docker_image"] = docker
    if queue:
        job_data["queue"] = queue
    if pool:
        job_data["worker_pool"] = pool
    if template:
        job_data["template"] = template

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{master_url}/jobs", json=job_data)
            resp.raise_for_status()
            result = resp.json()

            job_id = result["job_id"]

            if output == "json":
                console.print(json.dumps(result, indent=2))
            else:
                console.print(f"[green]Job submitted:[/green] {job_id}")

            if wait:
                console.print("Waiting for completion...")
                with console.status("Running..."):
                    while True:
                        time.sleep(2)
                        resp = client.get(f"{master_url}/jobs/{job_id}")
                        resp.raise_for_status()
                        job = resp.json()

                        status = job["status"]
                        if status in ("completed", "failed", "cancelled", "timeout"):
                            break

                if status == "completed":
                    console.print(f"[green]Job completed[/green]")
                    if job.get("result", {}).get("stdout"):
                        console.print(Panel(job["result"]["stdout"][:3000], title="Output"))
                else:
                    console.print(f"[red]Job {status}[/red]")
                    if job.get("result", {}).get("stderr"):
                        console.print(Panel(job["result"]["stderr"][:3000], title="Error", border_style="red"))
                    raise typer.Exit(1)

    except httpx.ConnectError:
        console.print("[red]Cannot connect to master[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@jobs_app.command("list")
def jobs_list(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    status_filter: Optional[str] = typer.Option(None, "--status", "-s"),
    queue: Optional[str] = typer.Option(None, "--queue", "-q"),
    limit: int = typer.Option(20, "--limit", "-n"),
    output: str = typer.Option("table", "--output", "-o"),
):
    """List jobs in the cluster."""
    import httpx

    params = {"limit": limit}
    if status_filter:
        params["status"] = status_filter
    if queue:
        params["queue"] = queue

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/jobs", params=params)
            resp.raise_for_status()
            data = resp.json()

        jobs = data.get("jobs", [])

        if output == "json":
            console.print(json.dumps(data, indent=2))
            return

        if not jobs:
            console.print("[yellow]No jobs found[/yellow]")
            return

        table = Table(title=f"Jobs ({len(jobs)} shown)")
        table.add_column("ID", style="cyan", max_width=24)
        table.add_column("Name", style="white", max_width=25)
        table.add_column("Status")
        table.add_column("Queue", style="blue")
        table.add_column("Worker", style="magenta", max_width=16)
        table.add_column("Time")

        status_styles = {
            "pending": "[blue]○ pending[/blue]",
            "running": "[yellow]● running[/yellow]",
            "completed": "[green]✓ completed[/green]",
            "failed": "[red]✗ failed[/red]",
            "cancelled": "[gray]⊘ cancelled[/gray]",
            "timeout": "[red]⏱ timeout[/red]",
        }

        for job in jobs:
            status = job.get("status", "unknown")
            status_display = status_styles.get(status, status)

            time_str = ""
            if job.get("execution_time_seconds"):
                time_str = f"{job['execution_time_seconds']:.1f}s"
            elif job.get("wait_time_seconds") and status == "pending":
                time_str = f"wait {job['wait_time_seconds']:.0f}s"

            table.add_row(
                job["job_id"][:24],
                (job.get("name") or "-")[:25],
                status_display,
                job.get("queue", "default"),
                (job.get("assigned_worker") or "-")[:16],
                time_str,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@jobs_app.command("get")
def jobs_get(
    job_id: str = typer.Argument(..., help="Job ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    output: str = typer.Option("text", "--output", "-o"),
):
    """Get detailed job information."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/jobs/{job_id}")
            resp.raise_for_status()
            job = resp.json()

        if output == "json":
            console.print(json.dumps(job, indent=2))
            return

        # Build tree
        tree = Tree(f"[bold cyan]Job: {job['job_id']}[/bold cyan]")

        info = tree.add("[bold]Info[/bold]")
        info.add(f"Name: {job.get('name', '-')}")
        info.add(f"Status: {job['status']}")
        info.add(f"Priority: {job.get('priority', 50)}")
        info.add(f"Queue: {job.get('queue', 'default')}")

        resources = tree.add("[bold]Resources[/bold]")
        res = job.get("resources", {})
        resources.add(f"CPU: {res.get('cpu_cores', 0)} cores")
        resources.add(f"Memory: {res.get('memory_mb', 0)} MB")
        resources.add(f"GPU: {res.get('gpu_count', 0)}")

        timing = tree.add("[bold]Timing[/bold]")
        timing.add(f"Created: {job.get('created_at', '-')}")
        timing.add(f"Started: {job.get('started_at', '-')}")
        timing.add(f"Completed: {job.get('completed_at', '-')}")
        if job.get("execution_time_seconds"):
            timing.add(f"Duration: {job['execution_time_seconds']:.2f}s")

        if job.get("assigned_worker"):
            worker = tree.add("[bold]Worker[/bold]")
            worker.add(f"ID: {job['assigned_worker']}")

        if job.get("result"):
            result = tree.add("[bold]Result[/bold]")
            result.add(f"Exit Code: {job['result'].get('exit_code', '-')}")

        console.print(tree)

        # Show output if available
        if job.get("result", {}).get("stdout"):
            console.print(Panel(
                job["result"]["stdout"][:5000],
                title="stdout",
                border_style="green"
            ))

        if job.get("result", {}).get("stderr"):
            console.print(Panel(
                job["result"]["stderr"][:5000],
                title="stderr",
                border_style="red"
            ))

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@jobs_app.command("cancel")
def jobs_cancel(
    job_id: str = typer.Argument(..., help="Job ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Cancel a running or pending job."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.delete(f"{master_url}/jobs/{job_id}")
            resp.raise_for_status()

        console.print(f"[green]Job cancelled: {job_id}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@jobs_app.command("logs")
def jobs_logs(
    job_id: str = typer.Argument(..., help="Job ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow logs"),
    tail: int = typer.Option(100, "--tail", "-n", help="Number of lines"),
):
    """View job logs."""
    import httpx
    import time

    try:
        with httpx.Client(timeout=10) as client:
            if follow:
                last_lines = 0
                while True:
                    resp = client.get(f"{master_url}/jobs/{job_id}")
                    resp.raise_for_status()
                    job = resp.json()

                    logs = job.get("logs", [])
                    new_logs = logs[last_lines:]

                    for log in new_logs:
                        console.print(log)

                    last_lines = len(logs)

                    if job["status"] in ("completed", "failed", "cancelled", "timeout"):
                        break

                    time.sleep(1)
            else:
                resp = client.get(f"{master_url}/jobs/{job_id}")
                resp.raise_for_status()
                job = resp.json()

                logs = job.get("logs", [])
                for log in logs[-tail:]:
                    console.print(log)

                if not logs:
                    console.print("[yellow]No logs available[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Workers Commands
# =============================================================================

@workers_app.command("list")
def workers_list(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    pool: Optional[str] = typer.Option(None, "--pool", help="Filter by pool"),
    status_filter: Optional[str] = typer.Option(None, "--status", "-s"),
    output: str = typer.Option("table", "--output", "-o"),
):
    """List workers in the cluster."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/workers")
            resp.raise_for_status()
            data = resp.json()

        workers = data.get("workers", [])

        if pool:
            workers = [w for w in workers if w.get("pool") == pool]
        if status_filter:
            workers = [w for w in workers if w.get("status") == status_filter]

        if output == "json":
            console.print(json.dumps({"workers": workers}, indent=2))
            return

        if not workers:
            console.print("[yellow]No workers found[/yellow]")
            return

        table = Table(title=f"Workers ({len(workers)})")
        table.add_column("ID", style="cyan", max_width=20)
        table.add_column("Hostname", style="white")
        table.add_column("Status")
        table.add_column("Pool", style="blue")
        table.add_column("CPU", style="green")
        table.add_column("Memory", style="green")
        table.add_column("GPU", style="magenta")
        table.add_column("Jobs")

        for w in workers:
            status = w.get("status", "unknown")
            if status == "ready":
                status_display = "[green]● ready[/green]"
            elif status == "busy":
                status_display = "[yellow]● busy[/yellow]"
            elif status == "offline":
                status_display = "[red]○ offline[/red]"
            else:
                status_display = status

            total_res = w.get("total_resources", {})
            avail_res = w.get("available_resources", {})

            table.add_row(
                w["worker_id"][:20],
                w.get("hostname", "-"),
                status_display,
                w.get("pool", "default"),
                f"{avail_res.get('cpu_cores', 0):.1f}/{total_res.get('cpu_cores', 0):.1f}",
                f"{avail_res.get('memory_mb', 0)}/{total_res.get('memory_mb', 0)} MB",
                f"{avail_res.get('gpu_count', 0)}/{total_res.get('gpu_count', 0)}",
                str(len(w.get("active_jobs", []))),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workers_app.command("get")
def workers_get(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    output: str = typer.Option("text", "--output", "-o"),
):
    """Get detailed worker information."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/workers/{worker_id}")
            resp.raise_for_status()
            worker = resp.json()

        if output == "json":
            console.print(json.dumps(worker, indent=2))
            return

        tree = Tree(f"[bold cyan]Worker: {worker['worker_id']}[/bold cyan]")

        info = tree.add("[bold]Info[/bold]")
        info.add(f"Hostname: {worker.get('hostname', '-')}")
        info.add(f"Status: {worker.get('status', '-')}")
        info.add(f"Pool: {worker.get('pool', 'default')}")
        info.add(f"Tags: {', '.join(worker.get('tags', []))}")

        total = worker.get("total_resources", {})
        avail = worker.get("available_resources", {})

        resources = tree.add("[bold]Resources[/bold]")
        resources.add(f"CPU: {avail.get('cpu_cores', 0):.1f} / {total.get('cpu_cores', 0):.1f} cores")
        resources.add(f"Memory: {avail.get('memory_mb', 0)} / {total.get('memory_mb', 0)} MB")
        resources.add(f"GPU: {avail.get('gpu_count', 0)} / {total.get('gpu_count', 0)}")

        jobs = tree.add("[bold]Active Jobs[/bold]")
        for job_id in worker.get("active_jobs", []):
            jobs.add(f"• {job_id}")

        if not worker.get("active_jobs"):
            jobs.add("[dim]No active jobs[/dim]")

        console.print(tree)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workers_app.command("drain")
def workers_drain(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Drain a worker (stop accepting new jobs)."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/workers/{worker_id}/drain")
            resp.raise_for_status()

        console.print(f"[green]Worker {worker_id} drained[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workers_app.command("undrain")
def workers_undrain(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Undrain a worker (resume accepting jobs)."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/workers/{worker_id}/undrain")
            resp.raise_for_status()

        console.print(f"[green]Worker {worker_id} undrained[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Templates Commands
# =============================================================================

@templates_app.command("list")
def templates_list(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    output: str = typer.Option("table", "--output", "-o"),
):
    """List available job templates."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/templates")
            resp.raise_for_status()
            data = resp.json()

        templates = data.get("templates", [])

        if output == "json":
            console.print(json.dumps(data, indent=2))
            return

        if not templates:
            console.print("[yellow]No templates found[/yellow]")
            return

        table = Table(title="Job Templates")
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("CPU", style="green")
        table.add_column("Memory", style="green")
        table.add_column("GPU", style="magenta")
        table.add_column("Docker", style="blue")

        for t in templates:
            res = t.get("resources", {})
            table.add_row(
                t["name"],
                t.get("description", "-")[:40],
                str(res.get("cpu_cores", "-")),
                f"{res.get('memory_mb', '-')} MB",
                str(res.get("gpu_count", "-")),
                t.get("docker_image", "-")[:30],
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@templates_app.command("create")
def templates_create(
    name: str = typer.Argument(..., help="Template name"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    description: Optional[str] = typer.Option(None, "--desc", "-d"),
    cpu: float = typer.Option(1.0, "--cpu"),
    memory: int = typer.Option(512, "--memory", "--mem"),
    gpu: int = typer.Option(0, "--gpu"),
    docker: Optional[str] = typer.Option(None, "--docker"),
    timeout: int = typer.Option(3600, "--timeout", "-t"),
    command: Optional[str] = typer.Option(None, "--command", "-c"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
):
    """Create a new job template."""
    import httpx

    environment = {}
    if env:
        for pair in env.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                environment[k.strip()] = v.strip()

    template_data = {
        "name": name,
        "description": description,
        "resources": {
            "cpu_cores": cpu,
            "memory_mb": memory,
            "gpu_count": gpu,
        },
        "timeout_seconds": timeout,
        "environment": environment,
    }

    if docker:
        template_data["docker_image"] = docker
    if command:
        template_data["command"] = command

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/templates", json=template_data)
            resp.raise_for_status()

        console.print(f"[green]Template created: {name}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@templates_app.command("delete")
def templates_delete(
    name: str = typer.Argument(..., help="Template name"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Delete a job template."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.delete(f"{master_url}/templates/{name}")
            resp.raise_for_status()

        console.print(f"[green]Template deleted: {name}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@templates_app.command("use")
def templates_use(
    template: str = typer.Argument(..., help="Template name"),
    command: str = typer.Argument(..., help="Command to run"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    wait: bool = typer.Option(False, "--wait", "-w"),
):
    """Submit a job using a template."""
    import httpx
    import time

    environment = {}
    if env:
        for pair in env.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                environment[k.strip()] = v.strip()

    job_data = {
        "template": template,
        "command": command,
        "name": name or command[:50],
        "environment": environment,
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{master_url}/jobs", json=job_data)
            resp.raise_for_status()
            result = resp.json()

            job_id = result["job_id"]
            console.print(f"[green]Job submitted from template '{template}': {job_id}[/green]")

            if wait:
                console.print("Waiting for completion...")
                while True:
                    time.sleep(2)
                    resp = client.get(f"{master_url}/jobs/{job_id}")
                    resp.raise_for_status()
                    job = resp.json()

                    if job["status"] in ("completed", "failed", "cancelled", "timeout"):
                        if job["status"] == "completed":
                            console.print("[green]Job completed[/green]")
                        else:
                            console.print(f"[red]Job {job['status']}[/red]")
                            raise typer.Exit(1)
                        break

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Pools Commands
# =============================================================================

@pools_app.command("list")
def pools_list(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    output: str = typer.Option("table", "--output", "-o"),
):
    """List worker pools."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/pools")
            resp.raise_for_status()
            data = resp.json()

        pools = data.get("pools", [])

        if output == "json":
            console.print(json.dumps(data, indent=2))
            return

        if not pools:
            console.print("[yellow]No pools configured[/yellow]")
            return

        table = Table(title="Worker Pools")
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Workers", style="green")
        table.add_column("Min", style="blue")
        table.add_column("Max", style="blue")
        table.add_column("Labels")

        for p in pools:
            table.add_row(
                p["name"],
                p.get("description", "-")[:30],
                str(p.get("worker_count", 0)),
                str(p.get("min_workers", 0)),
                str(p.get("max_workers", "-")),
                ", ".join(p.get("labels", []))[:30],
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@pools_app.command("create")
def pools_create(
    name: str = typer.Argument(..., help="Pool name"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    description: Optional[str] = typer.Option(None, "--desc", "-d"),
    min_workers: int = typer.Option(0, "--min"),
    max_workers: int = typer.Option(10, "--max"),
    labels: Optional[str] = typer.Option(None, "--labels", "-l", help="Labels (comma-separated)"),
    autoscale: bool = typer.Option(True, "--autoscale/--no-autoscale"),
):
    """Create a new worker pool."""
    import httpx

    pool_labels = [l.strip() for l in labels.split(",")] if labels else []

    pool_data = {
        "name": name,
        "description": description,
        "min_workers": min_workers,
        "max_workers": max_workers,
        "labels": pool_labels,
        "autoscale_enabled": autoscale,
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/pools", json=pool_data)
            resp.raise_for_status()

        console.print(f"[green]Pool created: {name}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@pools_app.command("delete")
def pools_delete(
    name: str = typer.Argument(..., help="Pool name"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete with workers"),
):
    """Delete a worker pool."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            params = {"force": force}
            resp = client.delete(f"{master_url}/pools/{name}", params=params)
            resp.raise_for_status()

        console.print(f"[green]Pool deleted: {name}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Queues Commands
# =============================================================================

@queues_app.command("list")
def queues_list(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    output: str = typer.Option("table", "--output", "-o"),
):
    """List priority queues."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/queues")
            resp.raise_for_status()
            data = resp.json()

        queues = data.get("queues", [])

        if output == "json":
            console.print(json.dumps(data, indent=2))
            return

        if not queues:
            console.print("[yellow]No queues configured[/yellow]")
            return

        table = Table(title="Priority Queues")
        table.add_column("Name", style="cyan")
        table.add_column("Priority", style="yellow")
        table.add_column("Weight", style="green")
        table.add_column("Pending", style="blue")
        table.add_column("Running", style="magenta")
        table.add_column("State")

        for q in queues:
            state = q.get("state", "active")
            if state == "active":
                state_display = "[green]● active[/green]"
            elif state == "paused":
                state_display = "[yellow]○ paused[/yellow]"
            else:
                state_display = state

            table.add_row(
                q["name"],
                str(q.get("priority", 50)),
                str(q.get("weight", 1)),
                str(q.get("pending_jobs", 0)),
                str(q.get("running_jobs", 0)),
                state_display,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@queues_app.command("create")
def queues_create(
    name: str = typer.Argument(..., help="Queue name"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    priority: int = typer.Option(50, "--priority", "-p", help="Base priority (0-200)"),
    weight: int = typer.Option(1, "--weight", "-w", help="Scheduling weight"),
    max_concurrent: Optional[int] = typer.Option(None, "--max-concurrent"),
    pool: Optional[str] = typer.Option(None, "--pool", help="Target worker pool"),
):
    """Create a new priority queue."""
    import httpx

    queue_data = {
        "name": name,
        "priority": priority,
        "weight": weight,
    }

    if max_concurrent:
        queue_data["max_concurrent_jobs"] = max_concurrent
    if pool:
        queue_data["target_pool"] = pool

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/queues", json=queue_data)
            resp.raise_for_status()

        console.print(f"[green]Queue created: {name}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@queues_app.command("pause")
def queues_pause(
    name: str = typer.Argument(..., help="Queue name"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Pause a queue (stop scheduling new jobs)."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/queues/{name}/pause")
            resp.raise_for_status()

        console.print(f"[green]Queue paused: {name}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@queues_app.command("resume")
def queues_resume(
    name: str = typer.Argument(..., help="Queue name"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Resume a paused queue."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/queues/{name}/resume")
            resp.raise_for_status()

        console.print(f"[green]Queue resumed: {name}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Secrets Commands
# =============================================================================

@secrets_app.command("list")
def secrets_list(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    output: str = typer.Option("table", "--output", "-o"),
):
    """List secrets (names only, values hidden)."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/secrets")
            resp.raise_for_status()
            data = resp.json()

        secrets = data.get("secrets", [])

        if output == "json":
            console.print(json.dumps(data, indent=2))
            return

        if not secrets:
            console.print("[yellow]No secrets found[/yellow]")
            return

        table = Table(title="Secrets")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="blue")
        table.add_column("Created", style="white")
        table.add_column("Allowed Jobs")

        for s in secrets:
            table.add_row(
                s["name"],
                s.get("type", "generic"),
                s.get("created_at", "-")[:19],
                ", ".join(s.get("allowed_jobs", ["*"]))[:30],
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@secrets_app.command("create")
def secrets_create(
    name: str = typer.Argument(..., help="Secret name"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    value: Optional[str] = typer.Option(None, "--value", "-v", help="Secret value"),
    from_file: Optional[Path] = typer.Option(None, "--from-file", "-f", help="Read from file"),
    secret_type: str = typer.Option("generic", "--type", "-t", help="Secret type"),
    allowed_jobs: Optional[str] = typer.Option(None, "--allowed-jobs", help="Allowed job patterns"),
):
    """Create a new secret."""
    import httpx

    if from_file:
        if not from_file.exists():
            console.print(f"[red]File not found: {from_file}[/red]")
            raise typer.Exit(1)
        value = from_file.read_text()

    if not value:
        # Prompt for value
        value = typer.prompt("Secret value", hide_input=True)

    allowed = [j.strip() for j in allowed_jobs.split(",")] if allowed_jobs else ["*"]

    secret_data = {
        "name": name,
        "value": value,
        "type": secret_type,
        "allowed_jobs": allowed,
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/secrets", json=secret_data)
            resp.raise_for_status()

        console.print(f"[green]Secret created: {name}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@secrets_app.command("delete")
def secrets_delete(
    name: str = typer.Argument(..., help="Secret name"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Delete a secret."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.delete(f"{master_url}/secrets/{name}")
            resp.raise_for_status()

        console.print(f"[green]Secret deleted: {name}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Config Commands
# =============================================================================

@config_app.command("show")
def config_show(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Show current configuration."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/config")
            resp.raise_for_status()
            config = resp.json()

        console.print(Panel(
            json.dumps(config, indent=2),
            title="Cluster Configuration",
            border_style="blue"
        ))

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key (dot notation)"),
    value: str = typer.Argument(..., help="Config value"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Set a configuration value."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{master_url}/config",
                json={"key": key, "value": value}
            )
            resp.raise_for_status()

        console.print(f"[green]Config updated: {key}={value}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Interactive Mode
# =============================================================================

@app.command()
def shell(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m", help="Master URL"),
):
    """Start interactive shell mode."""
    from distributed_cluster.cli.interactive import run_interactive
    run_interactive(master_url)


@app.command()
def watch(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m", help="Master URL"),
    interval: int = typer.Option(2, "--interval", "-i", help="Update interval in seconds"),
):
    """Live cluster dashboard. Press Ctrl+C to stop."""
    import httpx
    import time
    from datetime import datetime

    console.print("Starting live dashboard (Ctrl+C to stop)...")

    try:
        while True:
            console.clear()

            try:
                with httpx.Client(timeout=5) as client:
                    stats = client.get(f"{master_url}/stats").json()

                console.print(Panel.fit(
                    f"[bold cyan]NebulaCompute Dashboard[/bold cyan]\n"
                    f"Updated: {datetime.now().strftime('%H:%M:%S')}",
                    border_style="cyan"
                ))

                # Resources table
                table = Table(show_header=True, header_style="bold")
                table.add_column("Metric", style="cyan")
                table.add_column("Available", style="green")
                table.add_column("Total", style="blue")

                table.add_row(
                    "Workers",
                    str(stats.get("active_workers", 0)),
                    str(stats.get("total_workers", 0))
                )
                table.add_row(
                    "CPU Cores",
                    f"{stats.get('available_cpu_cores', 0):.1f}",
                    f"{stats.get('total_cpu_cores', 0):.1f}"
                )
                table.add_row(
                    "Memory (GB)",
                    f"{stats.get('available_memory_gb', 0):.1f}",
                    f"{stats.get('total_memory_gb', 0):.1f}"
                )
                table.add_row(
                    "GPUs",
                    str(stats.get("available_gpus", 0)),
                    str(stats.get("total_gpus", 0))
                )

                console.print(table)
                console.print()

                # Jobs summary
                console.print(
                    f"[blue]Pending:[/blue] {stats.get('pending_jobs', 0)}  "
                    f"[yellow]Running:[/yellow] {stats.get('running_jobs', 0)}  "
                    f"[green]Completed:[/green] {stats.get('completed_jobs', 0)}  "
                    f"[red]Failed:[/red] {stats.get('failed_jobs', 0)}"
                )

            except Exception as e:
                console.print(f"[red]Connection error: {e}[/red]")

            time.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped[/yellow]")


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Main entry point."""
    app()


def cli():
    """CLI entry point for setup.py."""
    main()


if __name__ == "__main__":
    main()
