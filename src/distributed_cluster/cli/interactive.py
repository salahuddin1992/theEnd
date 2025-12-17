"""
Interactive CLI Mode - وضع CLI التفاعلي
========================================

Provides an interactive shell for the distributed cluster.
"""

import asyncio
import cmd
import json
import os
import readline
import shlex
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout

console = Console()


class InteractiveShell(cmd.Cmd):
    """
    Interactive shell للتحكم بالكلاستر.

    Features:
    - Tab completion
    - Command history
    - Live status updates
    - Job submission and monitoring
    """

    intro = """
╔══════════════════════════════════════════════════════════════════╗
║                  NebulaCompute Interactive Shell                 ║
║══════════════════════════════════════════════════════════════════║
║  Type 'help' for available commands, 'quit' to exit             ║
║  Use Tab for auto-completion                                     ║
╚══════════════════════════════════════════════════════════════════╝
"""
    prompt = "\033[1;36mnebula>\033[0m "

    def __init__(self, master_url: str = "http://localhost:8765"):
        super().__init__()
        self.master_url = master_url
        self.client = httpx.Client(timeout=30)
        self._job_history: List[str] = []
        self._worker_cache: List[str] = []
        self._setup_history()

    def _setup_history(self) -> None:
        """Setup command history."""
        history_file = os.path.expanduser("~/.nebula_history")
        try:
            readline.read_history_file(history_file)
        except FileNotFoundError:
            pass

        import atexit
        atexit.register(readline.write_history_file, history_file)

    def _api_get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make GET request to API."""
        try:
            resp = self.client.get(f"{self.master_url}{endpoint}", params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            console.print(f"[red]API Error: {e}[/red]")
            return {}

    def _api_post(self, endpoint: str, data: Dict) -> Dict:
        """Make POST request to API."""
        try:
            resp = self.client.post(f"{self.master_url}{endpoint}", json=data)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            console.print(f"[red]API Error: {e}[/red]")
            return {}

    def _api_delete(self, endpoint: str) -> bool:
        """Make DELETE request to API."""
        try:
            resp = self.client.delete(f"{self.master_url}{endpoint}")
            resp.raise_for_status()
            return True
        except Exception as e:
            console.print(f"[red]API Error: {e}[/red]")
            return False

    # =========================================================================
    # Connection Commands
    # =========================================================================

    def do_connect(self, arg: str) -> None:
        """Connect to a different master. Usage: connect <url>"""
        if arg:
            self.master_url = arg
        console.print(f"[green]Connected to: {self.master_url}[/green]")

    def do_status(self, arg: str) -> None:
        """Show cluster status overview."""
        stats = self._api_get("/stats")
        if not stats:
            return

        # Create status display
        table = Table(title="Cluster Status", show_header=True, header_style="bold cyan")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Workers", f"{stats.get('active_workers', 0)} / {stats.get('total_workers', 0)}")
        table.add_row("CPU Cores", f"{stats.get('available_cpu_cores', 0):.1f} / {stats.get('total_cpu_cores', 0):.1f}")
        table.add_row("Memory (GB)", f"{stats.get('available_memory_gb', 0):.1f} / {stats.get('total_memory_gb', 0):.1f}")
        table.add_row("GPUs", f"{stats.get('available_gpus', 0)} / {stats.get('total_gpus', 0)}")
        table.add_row("", "")
        table.add_row("Pending Jobs", str(stats.get('pending_jobs', 0)))
        table.add_row("Running Jobs", str(stats.get('running_jobs', 0)))
        table.add_row("Completed Jobs", str(stats.get('completed_jobs', 0)))
        table.add_row("Failed Jobs", str(stats.get('failed_jobs', 0)))

        console.print(table)

    # =========================================================================
    # Job Commands
    # =========================================================================

    def do_submit(self, arg: str) -> None:
        """
        Submit a job. Usage: submit <command> [options]
        Options:
          --name NAME        Job name
          --cpu N            CPU cores (default: 1)
          --mem N            Memory in MB (default: 512)
          --gpu N            GPU count (default: 0)
          --priority N       Priority 0-200 (default: 50)
          --queue NAME       Queue name
          --docker IMAGE     Docker image
        """
        if not arg:
            console.print("[yellow]Usage: submit <command> [options][/yellow]")
            return

        try:
            parts = shlex.split(arg)
        except ValueError:
            parts = arg.split()

        # Parse options
        command = []
        options = {
            "cpu": 1.0,
            "mem": 512,
            "gpu": 0,
            "priority": 50,
            "name": None,
            "queue": None,
            "docker": None,
        }

        i = 0
        while i < len(parts):
            if parts[i].startswith("--"):
                key = parts[i][2:]
                if i + 1 < len(parts):
                    value = parts[i + 1]
                    if key in ("cpu",):
                        options[key] = float(value)
                    elif key in ("mem", "gpu", "priority"):
                        options[key] = int(value)
                    else:
                        options[key] = value
                    i += 2
                else:
                    i += 1
            else:
                command.append(parts[i])
                i += 1

        if not command:
            console.print("[yellow]No command specified[/yellow]")
            return

        job_data = {
            "command": " ".join(command),
            "name": options["name"] or " ".join(command)[:50],
            "resources": {
                "cpu_cores": options["cpu"],
                "memory_mb": options["mem"],
                "gpu_count": options["gpu"],
            },
            "priority": options["priority"],
        }

        if options["queue"]:
            job_data["queue"] = options["queue"]
        if options["docker"]:
            job_data["docker_image"] = options["docker"]

        result = self._api_post("/jobs", job_data)
        if result:
            job_id = result.get("job_id", "unknown")
            self._job_history.append(job_id)
            console.print(f"[green]Job submitted: {job_id}[/green]")

    def do_jobs(self, arg: str) -> None:
        """List jobs. Usage: jobs [--status STATUS] [--limit N]"""
        params = {"limit": 20}

        if arg:
            parts = arg.split()
            i = 0
            while i < len(parts):
                if parts[i] == "--status" and i + 1 < len(parts):
                    params["status"] = parts[i + 1]
                    i += 2
                elif parts[i] == "--limit" and i + 1 < len(parts):
                    params["limit"] = int(parts[i + 1])
                    i += 2
                else:
                    i += 1

        data = self._api_get("/jobs", params)
        jobs = data.get("jobs", [])

        if not jobs:
            console.print("[yellow]No jobs found[/yellow]")
            return

        table = Table(title=f"Jobs ({len(jobs)})", show_header=True)
        table.add_column("ID", style="cyan", max_width=20)
        table.add_column("Name", max_width=25)
        table.add_column("Status")
        table.add_column("Worker", max_width=15)
        table.add_column("Time")

        status_colors = {
            "pending": "blue",
            "running": "yellow",
            "completed": "green",
            "failed": "red",
            "cancelled": "gray",
        }

        for job in jobs:
            status = job.get("status", "unknown")
            color = status_colors.get(status, "white")

            time_str = ""
            if job.get("execution_time_seconds"):
                time_str = f"{job['execution_time_seconds']:.1f}s"

            table.add_row(
                job["job_id"][:20],
                (job.get("name") or "-")[:25],
                f"[{color}]{status}[/{color}]",
                (job.get("assigned_worker") or "-")[:15],
                time_str,
            )

        console.print(table)

    def do_job(self, arg: str) -> None:
        """Get job details. Usage: job <job_id>"""
        if not arg:
            if self._job_history:
                arg = self._job_history[-1]
            else:
                console.print("[yellow]Usage: job <job_id>[/yellow]")
                return

        job = self._api_get(f"/jobs/{arg}")
        if not job:
            return

        console.print(Panel(
            json.dumps(job, indent=2, default=str),
            title=f"Job: {arg}",
            border_style="cyan"
        ))

        # Show output if available
        if job.get("result", {}).get("stdout"):
            console.print(Panel(
                job["result"]["stdout"][:3000],
                title="stdout",
                border_style="green"
            ))

        if job.get("result", {}).get("stderr"):
            console.print(Panel(
                job["result"]["stderr"][:3000],
                title="stderr",
                border_style="red"
            ))

    def do_cancel(self, arg: str) -> None:
        """Cancel a job. Usage: cancel <job_id>"""
        if not arg:
            console.print("[yellow]Usage: cancel <job_id>[/yellow]")
            return

        if self._api_delete(f"/jobs/{arg}"):
            console.print(f"[green]Job cancelled: {arg}[/green]")

    def do_wait(self, arg: str) -> None:
        """Wait for a job to complete. Usage: wait <job_id>"""
        import time

        if not arg:
            if self._job_history:
                arg = self._job_history[-1]
            else:
                console.print("[yellow]Usage: wait <job_id>[/yellow]")
                return

        console.print(f"Waiting for job {arg}...")

        with console.status("[bold yellow]Running..."):
            while True:
                job = self._api_get(f"/jobs/{arg}")
                status = job.get("status", "unknown")

                if status in ("completed", "failed", "cancelled", "timeout"):
                    break

                time.sleep(2)

        if status == "completed":
            console.print(f"[green]Job completed: {arg}[/green]")
        else:
            console.print(f"[red]Job {status}: {arg}[/red]")

    def complete_job(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Auto-complete job IDs."""
        return [j for j in self._job_history if j.startswith(text)]

    def complete_cancel(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        return self.complete_job(text, line, begidx, endidx)

    def complete_wait(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        return self.complete_job(text, line, begidx, endidx)

    # =========================================================================
    # Worker Commands
    # =========================================================================

    def do_workers(self, arg: str) -> None:
        """List workers. Usage: workers [--pool NAME]"""
        params = {}
        if arg and arg.startswith("--pool "):
            params["pool"] = arg[7:]

        data = self._api_get("/workers", params)
        workers = data.get("workers", [])

        # Update cache
        self._worker_cache = [w["worker_id"] for w in workers]

        if not workers:
            console.print("[yellow]No workers found[/yellow]")
            return

        table = Table(title=f"Workers ({len(workers)})", show_header=True)
        table.add_column("ID", style="cyan", max_width=20)
        table.add_column("Hostname")
        table.add_column("Status")
        table.add_column("CPU")
        table.add_column("Memory")
        table.add_column("GPU")
        table.add_column("Jobs")

        for w in workers:
            status = w.get("status", "unknown")
            status_colors = {"ready": "green", "busy": "yellow", "offline": "red"}
            color = status_colors.get(status, "white")

            total = w.get("total_resources", {})
            avail = w.get("available_resources", {})

            table.add_row(
                w["worker_id"][:20],
                w.get("hostname", "-"),
                f"[{color}]{status}[/{color}]",
                f"{avail.get('cpu_cores', 0):.1f}/{total.get('cpu_cores', 0):.1f}",
                f"{avail.get('memory_mb', 0)}/{total.get('memory_mb', 0)}",
                f"{avail.get('gpu_count', 0)}/{total.get('gpu_count', 0)}",
                str(len(w.get("active_jobs", []))),
            )

        console.print(table)

    def do_drain(self, arg: str) -> None:
        """Drain a worker. Usage: drain <worker_id>"""
        if not arg:
            console.print("[yellow]Usage: drain <worker_id>[/yellow]")
            return

        try:
            resp = self.client.post(f"{self.master_url}/workers/{arg}/drain")
            resp.raise_for_status()
            console.print(f"[green]Worker drained: {arg}[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def complete_drain(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        return [w for w in self._worker_cache if w.startswith(text)]

    # =========================================================================
    # Queue and Pool Commands
    # =========================================================================

    def do_queues(self, arg: str) -> None:
        """List priority queues."""
        data = self._api_get("/queues")
        queues = data.get("queues", [])

        if not queues:
            console.print("[yellow]No queues found[/yellow]")
            return

        table = Table(title="Priority Queues", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Priority")
        table.add_column("Pending")
        table.add_column("Running")
        table.add_column("State")

        for q in queues:
            state = q.get("state", "active")
            color = "green" if state == "active" else "yellow"

            table.add_row(
                q["name"],
                str(q.get("priority", 50)),
                str(q.get("pending_jobs", 0)),
                str(q.get("running_jobs", 0)),
                f"[{color}]{state}[/{color}]",
            )

        console.print(table)

    def do_pools(self, arg: str) -> None:
        """List worker pools."""
        data = self._api_get("/pools")
        pools = data.get("pools", [])

        if not pools:
            console.print("[yellow]No pools found[/yellow]")
            return

        table = Table(title="Worker Pools", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("Workers")
        table.add_column("Min")
        table.add_column("Max")

        for p in pools:
            table.add_row(
                p["name"],
                p.get("description", "-")[:30],
                str(p.get("worker_count", 0)),
                str(p.get("min_workers", 0)),
                str(p.get("max_workers", "-")),
            )

        console.print(table)

    # =========================================================================
    # Utility Commands
    # =========================================================================

    def do_watch(self, arg: str) -> None:
        """
        Live dashboard. Usage: watch [interval]
        Press Ctrl+C to stop.
        """
        import time

        interval = 2
        if arg:
            try:
                interval = int(arg)
            except ValueError:
                pass

        console.print("Starting live dashboard (Ctrl+C to stop)...")

        try:
            while True:
                # Clear screen
                console.clear()

                # Get data
                stats = self._api_get("/stats")

                # Display
                console.print(f"[bold cyan]NebulaCompute Dashboard[/bold cyan] - {datetime.now().strftime('%H:%M:%S')}")
                console.print("=" * 60)
                console.print()

                if stats:
                    console.print(f"Workers: [green]{stats.get('active_workers', 0)}[/green] / {stats.get('total_workers', 0)}")
                    console.print(f"CPU: [green]{stats.get('available_cpu_cores', 0):.1f}[/green] / {stats.get('total_cpu_cores', 0):.1f} cores")
                    console.print(f"Memory: [green]{stats.get('available_memory_gb', 0):.1f}[/green] / {stats.get('total_memory_gb', 0):.1f} GB")
                    console.print(f"GPUs: [green]{stats.get('available_gpus', 0)}[/green] / {stats.get('total_gpus', 0)}")
                    console.print()
                    console.print(f"Jobs: [blue]{stats.get('pending_jobs', 0)}[/blue] pending, [yellow]{stats.get('running_jobs', 0)}[/yellow] running")
                    console.print(f"      [green]{stats.get('completed_jobs', 0)}[/green] completed, [red]{stats.get('failed_jobs', 0)}[/red] failed")

                time.sleep(interval)

        except KeyboardInterrupt:
            console.print("\n[yellow]Dashboard stopped[/yellow]")

    def do_history(self, arg: str) -> None:
        """Show recent job history."""
        if not self._job_history:
            console.print("[yellow]No job history[/yellow]")
            return

        console.print("[bold]Recent Jobs:[/bold]")
        for i, job_id in enumerate(self._job_history[-10:], 1):
            console.print(f"  {i}. {job_id}")

    def do_clear(self, arg: str) -> None:
        """Clear the screen."""
        console.clear()

    def do_help(self, arg: str) -> None:
        """Show help."""
        if arg:
            super().do_help(arg)
            return

        console.print("""
[bold cyan]NebulaCompute Interactive Shell[/bold cyan]

[bold]Connection:[/bold]
  connect <url>      Connect to master
  status             Show cluster status

[bold]Jobs:[/bold]
  submit <cmd>       Submit a job
  jobs [--status X]  List jobs
  job <id>           Show job details
  cancel <id>        Cancel a job
  wait <id>          Wait for job completion

[bold]Workers:[/bold]
  workers            List workers
  drain <id>         Drain a worker

[bold]Resources:[/bold]
  queues             List priority queues
  pools              List worker pools

[bold]Utility:[/bold]
  watch [interval]   Live dashboard
  history            Show job history
  clear              Clear screen
  help               Show this help
  quit               Exit shell
""")

    def do_quit(self, arg: str) -> bool:
        """Exit the shell."""
        console.print("[yellow]Goodbye![/yellow]")
        return True

    def do_exit(self, arg: str) -> bool:
        """Exit the shell."""
        return self.do_quit(arg)

    def do_EOF(self, arg: str) -> bool:
        """Handle Ctrl+D."""
        print()
        return self.do_quit(arg)

    def emptyline(self) -> None:
        """Don't repeat last command on empty line."""
        pass

    def default(self, line: str) -> None:
        """Handle unknown commands."""
        console.print(f"[red]Unknown command: {line}[/red]")
        console.print("Type 'help' for available commands")


def run_interactive(master_url: str = "http://localhost:8765") -> None:
    """Run the interactive shell."""
    shell = InteractiveShell(master_url)

    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\n")
        shell.do_quit("")


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
    run_interactive(url)
