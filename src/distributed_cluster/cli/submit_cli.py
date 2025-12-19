"""
Submit CLI - واجهة إرسال Jobs
==============================

أوامر إرسال وإدارة jobs.
"""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="dc-submit",
    help="Submit and manage jobs on the distributed cluster",
    add_completion=False,
)
console = Console()


@app.command()
def run(
    command: str = typer.Argument(..., help="Command to run"),
    master_url: str = typer.Option("http://localhost:8765", "--master", "-m", help="Master URL"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Job name"),
    cpu: float = typer.Option(1.0, "--cpu", help="CPU cores required"),
    memory: int = typer.Option(512, "--memory", "--mem", help="Memory in MB"),
    gpu: int = typer.Option(0, "--gpu", help="Number of GPUs required"),
    docker_image: Optional[str] = typer.Option(None, "--docker", "-d", help="Docker image"),
    timeout: int = typer.Option(3600, "--timeout", "-t", help="Timeout in seconds"),
    tags: Optional[str] = typer.Option(None, "--tags", help="Required worker tags"),
    priority: int = typer.Option(50, "--priority", "-p", help="Job priority (0-200)"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Environment vars (KEY=VAL,...)"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
) -> None:
    """
    إرسال job جديد.

    مثال:
        dc-submit run "python train.py" --gpu 1 --memory 8192
        dc-submit run "echo hello" --docker python:3.11
    """
    import time

    import httpx

    # Parse environment variables
    environment = {}
    if env:
        for pair in env.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                environment[k.strip()] = v.strip()

    # Parse tags
    required_tags = []
    if tags:
        required_tags = [t.strip() for t in tags.split(",")]

    # Build job submission
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

    if docker_image:
        job_data["docker_image"] = docker_image

    try:
        response = httpx.post(f"{master_url}/jobs", json=job_data, timeout=30)
        response.raise_for_status()
        result = response.json()

        job_id = result["job_id"]
        console.print(f"[green]Job submitted: {job_id}[/green]")

        if wait:
            console.print("Waiting for completion...")
            while True:
                time.sleep(2)
                resp = httpx.get(f"{master_url}/jobs/{job_id}", timeout=10)
                resp.raise_for_status()
                job = resp.json()

                status = job["status"]
                if status in ("completed", "failed", "cancelled", "timeout"):
                    if status == "completed":
                        console.print("[green]Job completed successfully[/green]")
                        if job.get("result", {}).get("stdout"):
                            console.print("\n[bold]Output:[/bold]")
                            console.print(job["result"]["stdout"][:5000])
                    else:
                        console.print(f"[red]Job {status}[/red]")
                        if job.get("result", {}).get("stderr"):
                            console.print("\n[bold]Error:[/bold]")
                            console.print(job["result"]["stderr"][:5000])
                    break

    except httpx.ConnectError:
        console.print("[red]Error: Cannot connect to master[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def status(
    job_id: str = typer.Argument(..., help="Job ID"),
    master_url: str = typer.Option("http://localhost:8765", "--master", "-m", help="Master URL"),
) -> None:
    """
    عرض حالة job.

    مثال:
        dc-submit status job-abc123
    """
    import httpx

    try:
        response = httpx.get(f"{master_url}/jobs/{job_id}", timeout=10)
        response.raise_for_status()
        job = response.json()

        console.print(f"\n[bold]Job: {job['job_id']}[/bold]")
        console.print(f"  Name: {job.get('name', '-')}")
        console.print(f"  Status: {job['status']}")
        console.print(f"  Worker: {job.get('assigned_worker', '-')}")
        console.print(f"  Created: {job.get('created_at', '-')}")

        if job.get("execution_time_seconds"):
            console.print(f"  Execution Time: {job['execution_time_seconds']:.2f}s")

        if job.get("result"):
            result = job["result"]
            console.print("\n[bold]Result:[/bold]")
            console.print(f"  Exit Code: {result['exit_code']}")
            if result.get("stdout"):
                console.print(f"\n[bold]stdout:[/bold]\n{result['stdout'][:2000]}")
            if result.get("stderr"):
                console.print(f"\n[bold]stderr:[/bold]\n{result['stderr'][:2000]}")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]Job not found: {job_id}[/red]")
        else:
            console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def cancel(
    job_id: str = typer.Argument(..., help="Job ID"),
    master_url: str = typer.Option("http://localhost:8765", "--master", "-m", help="Master URL"),
) -> None:
    """
    إلغاء job.

    مثال:
        dc-submit cancel job-abc123
    """
    import httpx

    try:
        response = httpx.delete(f"{master_url}/jobs/{job_id}", timeout=10)
        response.raise_for_status()
        console.print(f"[green]Job cancelled: {job_id}[/green]")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]Job not found or already terminal: {job_id}[/red]")
        else:
            console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command("list")
def list_jobs(
    master_url: str = typer.Option("http://localhost:8765", "--master", "-m", help="Master URL"),
    status_filter: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of jobs"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """
    عرض قائمة jobs.

    مثال:
        dc-submit list --status running
    """
    import httpx

    try:
        params = {"limit": limit}
        if status_filter:
            params["status"] = status_filter

        response = httpx.get(f"{master_url}/jobs", params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if output_json:
            console.print(json.dumps(data, indent=2))
            return

        jobs_list = data.get("jobs", [])

        if not jobs_list:
            console.print("[yellow]No jobs found[/yellow]")
            return

        table = Table(title="Jobs")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Status")
        table.add_column("Worker", style="blue")
        table.add_column("Time", style="magenta")

        for j in jobs_list:
            status = j["status"]
            if status == "completed":
                status_display = "[green]✓ completed[/green]"
            elif status == "failed":
                status_display = "[red]✗ failed[/red]"
            elif status == "running":
                status_display = "[yellow]● running[/yellow]"
            elif status == "pending":
                status_display = "[blue]○ pending[/blue]"
            else:
                status_display = status

            time_display = ""
            if j.get("execution_time_seconds"):
                time_display = f"{j['execution_time_seconds']:.1f}s"
            elif j.get("wait_time_seconds") and j["status"] == "pending":
                time_display = f"wait: {j['wait_time_seconds']:.0f}s"

            table.add_row(
                j["job_id"][:20],
                (j.get("name") or "-")[:25],
                status_display,
                (j.get("assigned_worker") or "-")[:16],
                time_display,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def batch(
    jobs_file: Path = typer.Argument(..., help="JSON file with job definitions"),
    master_url: str = typer.Option("http://localhost:8765", "--master", "-m", help="Master URL"),
) -> None:
    """
    إرسال مجموعة jobs من ملف JSON.

    مثال:
        dc-submit batch jobs.json
    """
    import httpx

    if not jobs_file.exists():
        console.print(f"[red]File not found: {jobs_file}[/red]")
        raise typer.Exit(1)

    with open(jobs_file) as f:
        jobs_data = json.load(f)

    if not isinstance(jobs_data, list):
        jobs_data = [jobs_data]

    console.print(f"Submitting {len(jobs_data)} jobs...")

    submitted = 0
    for job_data in jobs_data:
        try:
            response = httpx.post(f"{master_url}/jobs", json=job_data, timeout=30)
            response.raise_for_status()
            result = response.json()
            console.print(f"  [green]✓[/green] {result['job_id']}")
            submitted += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] Failed: {e}")

    console.print(f"\n[green]Submitted {submitted}/{len(jobs_data)} jobs[/green]")


if __name__ == "__main__":
    app()
