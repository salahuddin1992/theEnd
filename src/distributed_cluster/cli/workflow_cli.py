"""
Workflow CLI Commands - أوامر سير العمل
========================================

CLI commands for managing workflows.
"""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

workflow_app = typer.Typer(help="Manage workflows")
console = Console()

DEFAULT_MASTER = "http://localhost:8765"


@workflow_app.command("list")
def workflow_list(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    status: Optional[str] = typer.Option(None, "--status", "-s"),
    owner: Optional[str] = typer.Option(None, "--owner"),
    output: str = typer.Option("table", "--output", "-o"),
):
    """List workflows."""
    import httpx

    params = {}
    if status:
        params["status"] = status
    if owner:
        params["owner"] = owner

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/workflows", params=params)
            resp.raise_for_status()
            data = resp.json()

        workflows = data.get("workflows", [])

        if output == "json":
            console.print(json.dumps(data, indent=2))
            return

        if not workflows:
            console.print("[yellow]No workflows found[/yellow]")
            return

        table = Table(title=f"Workflows ({len(workflows)})")
        table.add_column("ID", style="cyan", max_width=20)
        table.add_column("Name", style="white")
        table.add_column("Status")
        table.add_column("Version", style="blue")
        table.add_column("Owner")
        table.add_column("Runs")

        status_styles = {
            "draft": "[gray]○ draft[/gray]",
            "active": "[green]● active[/green]",
            "paused": "[yellow]⏸ paused[/yellow]",
            "archived": "[gray]⊘ archived[/gray]",
        }

        for wf in workflows:
            status_display = status_styles.get(wf.get("status", ""), wf.get("status", "-"))

            table.add_row(
                wf["workflow_id"][:20],
                wf.get("name", "-"),
                status_display,
                wf.get("current_version_id", "-")[:12],
                wf.get("owner", "-"),
                str(len(wf.get("runs", []))),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("create")
def workflow_create(
    name: str = typer.Argument(..., help="Workflow name"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    from_file: Optional[Path] = typer.Option(None, "--from-file", "-f", help="Load from YAML/JSON file"),
    description: Optional[str] = typer.Option(None, "--desc", "-d"),
    owner: Optional[str] = typer.Option(None, "--owner"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Tags (comma-separated)"),
):
    """Create a new workflow."""
    import httpx

    if from_file:
        if not from_file.exists():
            console.print(f"[red]File not found: {from_file}[/red]")
            raise typer.Exit(1)

        content = from_file.read_text()

        if from_file.suffix in (".yaml", ".yml"):
            try:
                import yaml
                definition = yaml.safe_load(content)
            except ImportError:
                console.print("[red]PyYAML required for YAML files: pip install pyyaml[/red]")
                raise typer.Exit(1)
        else:
            definition = json.loads(content)
    else:
        # Create minimal definition
        definition = {
            "name": name,
            "steps": [],
        }

    workflow_data = {
        "name": name,
        "definition": definition,
        "description": description or definition.get("description", ""),
        "owner": owner,
        "tags": [t.strip() for t in tags.split(",")] if tags else [],
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/workflows", json=workflow_data)
            resp.raise_for_status()
            result = resp.json()

        console.print(f"[green]Workflow created: {result.get('workflow_id', name)}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("get")
def workflow_get(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    output: str = typer.Option("text", "--output", "-o"),
):
    """Get workflow details."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/workflows/{workflow_id}")
            resp.raise_for_status()
            workflow = resp.json()

        if output == "json":
            console.print(json.dumps(workflow, indent=2))
            return

        # Build display
        tree = Tree(f"[bold cyan]Workflow: {workflow['name']}[/bold cyan]")

        info = tree.add("[bold]Info[/bold]")
        info.add(f"ID: {workflow['workflow_id']}")
        info.add(f"Status: {workflow.get('status', '-')}")
        info.add(f"Owner: {workflow.get('owner', '-')}")
        info.add(f"Description: {workflow.get('description', '-')}")
        info.add(f"Tags: {', '.join(workflow.get('tags', []))}")

        versions = tree.add("[bold]Versions[/bold]")
        for v in workflow.get("versions", [])[-5:]:
            marker = " [current]" if v.get("is_current") else ""
            versions.add(f"v{v.get('version_number', '?')}: {v.get('version_id', '-')[:12]}{marker}")

        triggers = tree.add("[bold]Triggers[/bold]")
        for t in workflow.get("triggers", []):
            enabled = "✓" if t.get("enabled") else "✗"
            triggers.add(f"{enabled} {t.get('trigger_type', '-')}")

        if not workflow.get("triggers"):
            triggers.add("[dim]No triggers configured[/dim]")

        console.print(tree)

        # Show recent runs
        runs = workflow.get("runs", [])[-5:]
        if runs:
            console.print()
            table = Table(title="Recent Runs")
            table.add_column("Run ID", style="cyan")
            table.add_column("Status")
            table.add_column("Started")
            table.add_column("Duration")

            for run in runs:
                status = run.get("status", "unknown")
                status_color = {
                    "pending": "blue",
                    "running": "yellow",
                    "succeeded": "green",
                    "failed": "red",
                }.get(status, "white")

                duration = ""
                if run.get("duration_seconds"):
                    duration = f"{run['duration_seconds']:.1f}s"

                table.add_row(
                    run["run_id"][:16],
                    f"[{status_color}]{status}[/{status_color}]",
                    run.get("started_at", "-")[:19] if run.get("started_at") else "-",
                    duration,
                )

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("run")
def workflow_run(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    params: Optional[str] = typer.Option(None, "--params", "-p", help="JSON parameters"),
    params_file: Optional[Path] = typer.Option(None, "--params-file", help="Parameters from file"),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="Specific version"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for completion"),
):
    """Run a workflow."""
    import httpx
    import time

    # Parse parameters
    run_params = {}
    if params:
        run_params = json.loads(params)
    elif params_file:
        if not params_file.exists():
            console.print(f"[red]File not found: {params_file}[/red]")
            raise typer.Exit(1)
        run_params = json.loads(params_file.read_text())

    run_data = {
        "params": run_params,
    }
    if version:
        run_data["version_id"] = version

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{master_url}/workflows/{workflow_id}/run", json=run_data)
            resp.raise_for_status()
            result = resp.json()

        run_id = result.get("run_id", "unknown")
        console.print(f"[green]Workflow run started: {run_id}[/green]")

        if wait:
            console.print("Waiting for completion...")

            with console.status("[bold yellow]Running..."):
                while True:
                    time.sleep(3)

                    resp = client.get(f"{master_url}/workflows/{workflow_id}/runs/{run_id}")
                    resp.raise_for_status()
                    run = resp.json()

                    status = run.get("status", "unknown")
                    if status in ("succeeded", "failed", "cancelled", "partial"):
                        break

            if status == "succeeded":
                console.print(f"[green]Workflow completed successfully![/green]")
            else:
                console.print(f"[red]Workflow {status}[/red]")
                if run.get("error_message"):
                    console.print(f"Error: {run['error_message']}")
                raise typer.Exit(1)

    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("runs")
def workflow_runs(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    status: Optional[str] = typer.Option(None, "--status", "-s"),
    limit: int = typer.Option(20, "--limit", "-n"),
    output: str = typer.Option("table", "--output", "-o"),
):
    """List workflow runs."""
    import httpx

    params = {"limit": limit}
    if status:
        params["status"] = status

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{master_url}/workflows/{workflow_id}/runs", params=params)
            resp.raise_for_status()
            data = resp.json()

        runs = data.get("runs", [])

        if output == "json":
            console.print(json.dumps(data, indent=2))
            return

        if not runs:
            console.print("[yellow]No runs found[/yellow]")
            return

        table = Table(title=f"Workflow Runs ({len(runs)})")
        table.add_column("Run ID", style="cyan")
        table.add_column("Status")
        table.add_column("Trigger")
        table.add_column("Started")
        table.add_column("Duration")
        table.add_column("Version")

        for run in runs:
            status = run.get("status", "unknown")
            status_colors = {
                "pending": "blue",
                "running": "yellow",
                "succeeded": "green",
                "failed": "red",
                "cancelled": "gray",
                "partial": "magenta",
            }
            color = status_colors.get(status, "white")

            duration = ""
            if run.get("duration_seconds"):
                duration = f"{run['duration_seconds']:.1f}s"

            table.add_row(
                run["run_id"][:16],
                f"[{color}]{status}[/{color}]",
                run.get("trigger", "-"),
                run.get("started_at", "-")[:19] if run.get("started_at") else "-",
                duration,
                run.get("version_id", "-")[:12],
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("cancel")
def workflow_cancel(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    run_id: str = typer.Argument(..., help="Run ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Cancel a workflow run."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.delete(f"{master_url}/workflows/{workflow_id}/runs/{run_id}")
            resp.raise_for_status()

        console.print(f"[green]Run cancelled: {run_id}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("activate")
def workflow_activate(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Activate a workflow."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/workflows/{workflow_id}/activate")
            resp.raise_for_status()

        console.print(f"[green]Workflow activated: {workflow_id}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("pause")
def workflow_pause(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """Pause a workflow."""
    import httpx

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{master_url}/workflows/{workflow_id}/pause")
            resp.raise_for_status()

        console.print(f"[green]Workflow paused: {workflow_id}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("update")
def workflow_update(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    from_file: Path = typer.Option(..., "--from-file", "-f", help="New definition file"),
    changelog: Optional[str] = typer.Option(None, "--changelog", "-c", help="Change description"),
):
    """Update a workflow (create new version)."""
    import httpx

    if not from_file.exists():
        console.print(f"[red]File not found: {from_file}[/red]")
        raise typer.Exit(1)

    content = from_file.read_text()

    if from_file.suffix in (".yaml", ".yml"):
        try:
            import yaml
            definition = yaml.safe_load(content)
        except ImportError:
            console.print("[red]PyYAML required for YAML files: pip install pyyaml[/red]")
            raise typer.Exit(1)
    else:
        definition = json.loads(content)

    update_data = {
        "definition": definition,
        "changelog": changelog or "Updated workflow definition",
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.put(f"{master_url}/workflows/{workflow_id}", json=update_data)
            resp.raise_for_status()
            result = resp.json()

        console.print(f"[green]Workflow updated to version: {result.get('version_id', 'new')}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("delete")
def workflow_delete(
    workflow_id: str = typer.Argument(..., help="Workflow ID"),
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete"),
):
    """Delete a workflow."""
    import httpx

    if not force:
        confirm = typer.confirm(f"Are you sure you want to delete workflow {workflow_id}?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.delete(f"{master_url}/workflows/{workflow_id}")
            resp.raise_for_status()

        console.print(f"[green]Workflow deleted: {workflow_id}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workflow_app.command("templates")
def workflow_templates(
    master_url: str = typer.Option(DEFAULT_MASTER, "--master", "-m"),
):
    """List available workflow templates."""
    from distributed_cluster.workflow.definitions import list_workflow_templates

    templates = list_workflow_templates()

    if not templates:
        console.print("[yellow]No templates available[/yellow]")
        return

    table = Table(title="Workflow Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Description")

    for t in templates:
        table.add_row(t["name"], t.get("description", "-"))

    console.print(table)
    console.print("\n[dim]Use: nebula workflows create <name> --from-template <template>[/dim]")


@workflow_app.command("validate")
def workflow_validate(
    file_path: Path = typer.Argument(..., help="Workflow definition file"),
):
    """Validate a workflow definition file."""
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    content = file_path.read_text()

    try:
        if file_path.suffix in (".yaml", ".yml"):
            from distributed_cluster.workflow.definitions import load_workflow_from_yaml
            definition = load_workflow_from_yaml(content)
        else:
            from distributed_cluster.workflow.definitions import load_workflow_from_json
            definition = load_workflow_from_json(content)

        is_valid, errors = definition.validate()

        if is_valid:
            console.print(f"[green]✓ Workflow definition is valid[/green]")
            console.print(f"  Name: {definition.name}")
            console.print(f"  Steps: {len(definition.steps)}")
        else:
            console.print(f"[red]✗ Workflow definition is invalid[/red]")
            for error in errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error parsing file: {e}[/red]")
        raise typer.Exit(1)
