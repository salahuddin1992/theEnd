"""
Secrets CLI - واجهة إدارة الأسرار
==================================

واجهة سطر أوامر متقدمة لإدارة الأسرار:
- إنشاء وحذف وتحديث الأسرار
- تدوير المفاتيح
- استيراد وتصدير
- تكامل مع Vault الخارجي
- تنبيهات انتهاء الصلاحية
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree

from distributed_cluster.security.secrets import (
    SecretType,
    SecretsManager,
    FileSecretStore,
    MemorySecretStore,
    Encryptor,
    create_secrets_manager,
)

app = typer.Typer(
    name="dc-secrets",
    help="إدارة الأسرار - Secrets Management CLI",
    add_completion=True,
    no_args_is_help=True,
)

console = Console()

# Default paths
DEFAULT_SECRETS_PATH = os.environ.get("NEBULA_SECRETS_PATH", "./data/secrets")
DEFAULT_MASTER_KEY = os.environ.get("NEBULA_SECRET_KEY")


def get_manager(
    store_path: Optional[str] = None,
    master_key: Optional[str] = None,
) -> SecretsManager:
    """Get secrets manager instance."""
    path = store_path or DEFAULT_SECRETS_PATH
    key = master_key or DEFAULT_MASTER_KEY
    return create_secrets_manager(
        master_key=key,
        store_type="file",
        store_path=path,
    )


def run_async(coro):
    """Run async function."""
    return asyncio.get_event_loop().run_until_complete(coro)


# =============================================================================
# Basic Commands
# =============================================================================


@app.command("list")
def list_secrets(
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Filter by namespace"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s", help="Secrets store path"),
    output: str = typer.Option("table", "--output", "-o", help="Output format (table/json)"),
    show_expired: bool = typer.Option(False, "--show-expired", help="Show expired secrets"),
):
    """List all secrets (metadata only, values hidden)."""
    manager = get_manager(store_path)

    async def do_list():
        secrets = await manager.list_secrets(namespace)

        if output == "json":
            console.print(json.dumps(secrets, indent=2, default=str))
            return

        if not secrets:
            console.print("[yellow]No secrets found[/yellow]")
            return

        # Filter expired if needed
        now = datetime.utcnow()
        if not show_expired:
            secrets = [
                s for s in secrets
                if not s.get("expires_at") or datetime.fromisoformat(s["expires_at"]) > now
            ]

        table = Table(title=f"Secrets ({len(secrets)})")
        table.add_column("Name", style="cyan")
        table.add_column("Namespace", style="blue")
        table.add_column("Type", style="magenta")
        table.add_column("Version", style="green")
        table.add_column("Created", style="white")
        table.add_column("Expires", style="yellow")
        table.add_column("Status")

        for s in secrets:
            expires = s.get("expires_at")
            status = "[green]● Active[/green]"
            expires_str = "-"

            if expires:
                exp_dt = datetime.fromisoformat(expires)
                expires_str = exp_dt.strftime("%Y-%m-%d")

                if exp_dt < now:
                    status = "[red]● Expired[/red]"
                elif exp_dt < now + timedelta(days=7):
                    status = "[yellow]● Expiring Soon[/yellow]"

            table.add_row(
                s["name"],
                s.get("namespace", "default"),
                s.get("type", "opaque"),
                str(s.get("version", 1)),
                s.get("created_at", "-")[:10],
                expires_str,
                status,
            )

        console.print(table)

    run_async(do_list())


@app.command("create")
def create_secret(
    name: str = typer.Argument(..., help="Secret name"),
    namespace: str = typer.Option("default", "--namespace", "-n", help="Namespace"),
    secret_type: str = typer.Option("opaque", "--type", "-t", help="Secret type"),
    value: Optional[str] = typer.Option(None, "--value", "-v", help="Secret value (key=value)"),
    from_file: Optional[Path] = typer.Option(None, "--from-file", "-f", help="Read from file"),
    from_env: Optional[str] = typer.Option(None, "--from-env", "-e", help="Read from env file"),
    expires_days: Optional[int] = typer.Option(None, "--expires", help="Expiration in days"),
    owner: Optional[str] = typer.Option(None, "--owner", help="Owner identifier"),
    allowed_jobs: Optional[str] = typer.Option(None, "--allowed-jobs", help="Allowed job patterns (comma-separated)"),
    allowed_users: Optional[str] = typer.Option(None, "--allowed-users", help="Allowed users (comma-separated)"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
    generate: bool = typer.Option(False, "--generate", "-g", help="Generate random value"),
    generate_length: int = typer.Option(32, "--length", "-l", help="Generated value length"),
):
    """Create a new secret."""
    manager = get_manager(store_path)

    # Collect data
    data = {}

    if generate:
        # Generate random secret
        data["value"] = manager.generate_password(generate_length)
        console.print(f"[dim]Generated value: {data['value'][:8]}...[/dim]")
    elif value:
        # Parse key=value pairs
        for pair in value.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                data[k.strip()] = v.strip()
            else:
                data["value"] = pair
    elif from_file:
        if not from_file.exists():
            console.print(f"[red]File not found: {from_file}[/red]")
            raise typer.Exit(1)
        data["value"] = from_file.read_text(encoding="utf-8")
    elif from_env:
        # Parse .env file
        env_path = Path(from_env)
        if not env_path.exists():
            console.print(f"[red]Env file not found: {from_env}[/red]")
            raise typer.Exit(1)

        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip('"\'')
    else:
        # Prompt for value
        secret_value = typer.prompt("Enter secret value", hide_input=True)
        data["value"] = secret_value

    if not data:
        console.print("[red]No secret data provided[/red]")
        raise typer.Exit(1)

    # Parse options
    expires_in = timedelta(days=expires_days) if expires_days else None
    jobs = [j.strip() for j in allowed_jobs.split(",")] if allowed_jobs else None
    users = [u.strip() for u in allowed_users.split(",")] if allowed_users else None

    async def do_create():
        success = await manager.create_secret(
            name=name,
            data=data,
            namespace=namespace,
            secret_type=SecretType(secret_type),
            expires_in=expires_in,
            owner=owner,
            allowed_jobs=jobs,
            allowed_users=users,
        )

        if success:
            console.print(f"[green]Secret created: {namespace}/{name}[/green]")
            console.print(f"  Keys: {', '.join(data.keys())}")
            if expires_in:
                console.print(f"  Expires: {expires_days} days")
        else:
            console.print(f"[red]Failed to create secret (may already exist)[/red]")
            raise typer.Exit(1)

    run_async(do_create())


@app.command("get")
def get_secret(
    name: str = typer.Argument(..., help="Secret name"),
    namespace: str = typer.Option("default", "--namespace", "-n"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="Specific key to retrieve"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
    output: str = typer.Option("text", "--output", "-o", help="Output format"),
    reveal: bool = typer.Option(False, "--reveal", "-r", help="Show actual values"),
):
    """Get a secret's value."""
    manager = get_manager(store_path)

    async def do_get():
        data = await manager.get_secret(name, namespace)

        if not data:
            console.print(f"[red]Secret not found: {namespace}/{name}[/red]")
            raise typer.Exit(1)

        if key:
            if key not in data:
                console.print(f"[red]Key not found: {key}[/red]")
                raise typer.Exit(1)

            if output == "raw":
                # Raw output for piping
                print(data[key], end="")
            else:
                if reveal:
                    console.print(data[key])
                else:
                    console.print(f"{key}: {'*' * 8}")
        else:
            if output == "json":
                if reveal:
                    console.print(json.dumps(data, indent=2))
                else:
                    hidden = {k: "*" * 8 for k in data}
                    console.print(json.dumps(hidden, indent=2))
            else:
                tree = Tree(f"[bold cyan]Secret: {namespace}/{name}[/bold cyan]")
                for k, v in data.items():
                    if reveal:
                        tree.add(f"[green]{k}:[/green] {v}")
                    else:
                        tree.add(f"[green]{k}:[/green] {'*' * 8}")
                console.print(tree)

    run_async(do_get())


@app.command("update")
def update_secret(
    name: str = typer.Argument(..., help="Secret name"),
    namespace: str = typer.Option("default", "--namespace", "-n"),
    value: Optional[str] = typer.Option(None, "--value", "-v", help="New value (key=value)"),
    from_file: Optional[Path] = typer.Option(None, "--from-file", "-f"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
):
    """Update an existing secret."""
    manager = get_manager(store_path)

    # Collect new data
    data = {}

    if value:
        for pair in value.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                data[k.strip()] = v.strip()
            else:
                data["value"] = pair
    elif from_file:
        if not from_file.exists():
            console.print(f"[red]File not found: {from_file}[/red]")
            raise typer.Exit(1)
        data["value"] = from_file.read_text(encoding="utf-8")
    else:
        secret_value = typer.prompt("Enter new secret value", hide_input=True)
        data["value"] = secret_value

    async def do_update():
        success = await manager.update_secret(name, data, namespace)

        if success:
            console.print(f"[green]Secret updated: {namespace}/{name}[/green]")
        else:
            console.print(f"[red]Secret not found: {namespace}/{name}[/red]")
            raise typer.Exit(1)

    run_async(do_update())


@app.command("delete")
def delete_secret(
    name: str = typer.Argument(..., help="Secret name"),
    namespace: str = typer.Option("default", "--namespace", "-n"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a secret."""
    if not force:
        confirm = typer.confirm(f"Delete secret {namespace}/{name}?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            raise typer.Exit(0)

    manager = get_manager(store_path)

    async def do_delete():
        success = await manager.delete_secret(name, namespace)

        if success:
            console.print(f"[green]Secret deleted: {namespace}/{name}[/green]")
        else:
            console.print(f"[red]Secret not found: {namespace}/{name}[/red]")
            raise typer.Exit(1)

    run_async(do_delete())


# =============================================================================
# Advanced Commands
# =============================================================================


@app.command("rotate")
def rotate_secret(
    name: str = typer.Argument(..., help="Secret name"),
    namespace: str = typer.Option("default", "--namespace", "-n"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
    length: int = typer.Option(32, "--length", "-l", help="New value length"),
):
    """Rotate a secret (generate new random values)."""
    manager = get_manager(store_path)

    async def do_rotate():
        success = await manager.rotate_secret(name, namespace)

        if success:
            console.print(f"[green]Secret rotated: {namespace}/{name}[/green]")
            console.print("[dim]All keys have been regenerated with new random values[/dim]")
        else:
            console.print(f"[red]Secret not found: {namespace}/{name}[/red]")
            raise typer.Exit(1)

    run_async(do_rotate())


@app.command("export")
def export_secrets(
    output_file: Path = typer.Argument(..., help="Output file path"),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
    format: str = typer.Option("json", "--format", "-f", help="Export format (json/env)"),
    encrypt: bool = typer.Option(True, "--encrypt/--no-encrypt", help="Encrypt export"),
):
    """Export secrets to a file."""
    manager = get_manager(store_path)

    async def do_export():
        secrets_list = await manager.list_secrets(namespace)

        export_data = []
        for s_meta in secrets_list:
            secret_data = await manager.get_secret(s_meta["name"], s_meta.get("namespace", "default"))
            if secret_data:
                export_data.append({
                    "name": s_meta["name"],
                    "namespace": s_meta.get("namespace", "default"),
                    "type": s_meta.get("type", "opaque"),
                    "data": secret_data,
                })

        if format == "env":
            # Export as .env file
            lines = []
            for s in export_data:
                lines.append(f"# Secret: {s['namespace']}/{s['name']}")
                for k, v in s["data"].items():
                    env_name = f"{s['name'].upper().replace('-', '_')}_{k.upper()}"
                    lines.append(f"{env_name}={v}")
                lines.append("")

            content = "\n".join(lines)
        else:
            content = json.dumps(export_data, indent=2)

        if encrypt:
            # Encrypt the export
            encryptor = Encryptor(DEFAULT_MASTER_KEY)
            encrypted = encryptor.encrypt_string(content)
            output_file.write_text(encrypted, encoding="utf-8")
            console.print(f"[green]Secrets exported (encrypted): {output_file}[/green]")
        else:
            output_file.write_text(content, encoding="utf-8")
            console.print(f"[yellow]Secrets exported (UNENCRYPTED): {output_file}[/yellow]")
            console.print("[dim]Warning: File contains plaintext secrets![/dim]")

        console.print(f"  Total: {len(export_data)} secrets")

    run_async(do_export())


@app.command("import")
def import_secrets(
    input_file: Path = typer.Argument(..., help="Input file path"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
    encrypted: bool = typer.Option(True, "--encrypted/--no-encrypted"),
    overwrite: bool = typer.Option(False, "--overwrite", "-w", help="Overwrite existing"),
):
    """Import secrets from a file."""
    if not input_file.exists():
        console.print(f"[red]File not found: {input_file}[/red]")
        raise typer.Exit(1)

    manager = get_manager(store_path)

    async def do_import():
        content = input_file.read_text(encoding="utf-8")

        if encrypted:
            encryptor = Encryptor(DEFAULT_MASTER_KEY)
            try:
                content = encryptor.decrypt_string(content)
            except Exception as e:
                console.print(f"[red]Decryption failed: {e}[/red]")
                console.print("[dim]Make sure NEBULA_SECRET_KEY matches the export key[/dim]")
                raise typer.Exit(1)

        secrets_data = json.loads(content)

        imported = 0
        skipped = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Importing...", total=len(secrets_data))

            for s in secrets_data:
                progress.update(task, description=f"Importing {s['name']}...")

                success = await manager.create_secret(
                    name=s["name"],
                    data=s["data"],
                    namespace=s.get("namespace", "default"),
                    secret_type=SecretType(s.get("type", "opaque")),
                )

                if success:
                    imported += 1
                elif overwrite:
                    await manager.update_secret(s["name"], s["data"], s.get("namespace", "default"))
                    imported += 1
                else:
                    skipped += 1

                progress.advance(task)

        console.print(f"[green]Import complete: {imported} imported, {skipped} skipped[/green]")

    run_async(do_import())


@app.command("check-expiry")
def check_expiry(
    days: int = typer.Option(7, "--days", "-d", help="Days threshold"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
    output: str = typer.Option("table", "--output", "-o"),
):
    """Check for expiring or expired secrets."""
    manager = get_manager(store_path)

    async def do_check():
        all_secrets = await manager.list_secrets()
        now = datetime.utcnow()
        threshold = now + timedelta(days=days)

        expiring = []
        expired = []

        for s in all_secrets:
            if s.get("expires_at"):
                exp_dt = datetime.fromisoformat(s["expires_at"])
                if exp_dt < now:
                    expired.append(s)
                elif exp_dt < threshold:
                    expiring.append(s)

        if output == "json":
            console.print(json.dumps({
                "expired": expired,
                "expiring_soon": expiring,
            }, indent=2, default=str))
            return

        if expired:
            console.print(Panel.fit(
                f"[bold red]{len(expired)} Expired Secrets[/bold red]",
                border_style="red"
            ))

            table = Table(show_header=True)
            table.add_column("Name", style="red")
            table.add_column("Namespace")
            table.add_column("Expired On")

            for s in expired:
                table.add_row(
                    s["name"],
                    s.get("namespace", "default"),
                    s.get("expires_at", "-")[:10],
                )

            console.print(table)
            console.print()

        if expiring:
            console.print(Panel.fit(
                f"[bold yellow]{len(expiring)} Secrets Expiring Soon[/bold yellow]",
                border_style="yellow"
            ))

            table = Table(show_header=True)
            table.add_column("Name", style="yellow")
            table.add_column("Namespace")
            table.add_column("Expires On")
            table.add_column("Days Left")

            for s in expiring:
                exp_dt = datetime.fromisoformat(s["expires_at"])
                days_left = (exp_dt - now).days

                table.add_row(
                    s["name"],
                    s.get("namespace", "default"),
                    s["expires_at"][:10],
                    str(days_left),
                )

            console.print(table)

        if not expired and not expiring:
            console.print(f"[green]No secrets expiring within {days} days[/green]")

        # Exit with error if expired secrets exist
        if expired:
            raise typer.Exit(1)

    run_async(do_check())


@app.command("generate")
def generate_secret(
    secret_type: str = typer.Argument("password", help="Type: password, api-key, token"),
    length: int = typer.Option(32, "--length", "-l"),
    prefix: Optional[str] = typer.Option(None, "--prefix", "-p", help="Prefix for API keys"),
    count: int = typer.Option(1, "--count", "-c", help="Number of secrets to generate"),
    save_as: Optional[str] = typer.Option(None, "--save-as", help="Save to secret store with this name"),
    namespace: str = typer.Option("default", "--namespace", "-n"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
):
    """Generate secure random secrets."""
    manager = get_manager(store_path)

    generated = []

    for i in range(count):
        if secret_type == "password":
            value = manager.generate_password(length)
        elif secret_type == "api-key":
            value = manager.generate_api_key(prefix or "neb")
        elif secret_type == "token":
            import secrets as py_secrets
            value = py_secrets.token_urlsafe(length)
        else:
            console.print(f"[red]Unknown type: {secret_type}[/red]")
            raise typer.Exit(1)

        generated.append(value)

    if save_as:
        async def do_save():
            if count == 1:
                data = {"value": generated[0]}
            else:
                data = {f"value_{i}": v for i, v in enumerate(generated)}

            success = await manager.create_secret(
                name=save_as,
                data=data,
                namespace=namespace,
                secret_type=SecretType.API_KEY if secret_type == "api-key" else SecretType.PASSWORD,
            )

            if success:
                console.print(f"[green]Secret saved: {namespace}/{save_as}[/green]")
            else:
                console.print(f"[red]Failed to save (may already exist)[/red]")

        run_async(do_save())
    else:
        for v in generated:
            console.print(v)


@app.command("inject")
def inject_secrets(
    secret_refs: str = typer.Argument(..., help="Secret references (comma-separated: ns/name,name)"),
    command: Optional[str] = typer.Option(None, "--exec", "-e", help="Command to execute with secrets as env"),
    output: str = typer.Option("export", "--output", "-o", help="Output format (export/json/dotenv)"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
):
    """Inject secrets as environment variables."""
    manager = get_manager(store_path)
    refs = [r.strip() for r in secret_refs.split(",")]

    async def do_inject():
        env_vars = await manager.inject_secrets(refs)

        if not env_vars:
            console.print("[yellow]No secrets found[/yellow]")
            raise typer.Exit(1)

        if command:
            # Execute command with injected secrets
            import subprocess

            env = os.environ.copy()
            env.update(env_vars)

            console.print(f"[dim]Executing with {len(env_vars)} secret(s)...[/dim]")
            result = subprocess.run(command, shell=True, env=env)
            raise typer.Exit(result.returncode)
        else:
            # Output for sourcing
            if output == "export":
                for k, v in env_vars.items():
                    print(f"export {k}='{v}'")
            elif output == "json":
                print(json.dumps(env_vars, indent=2))
            elif output == "dotenv":
                for k, v in env_vars.items():
                    print(f"{k}={v}")

    run_async(do_inject())


# =============================================================================
# Vault Integration Commands
# =============================================================================


@app.command("vault-sync")
def vault_sync(
    vault_addr: str = typer.Option(..., "--vault-addr", envvar="VAULT_ADDR", help="Vault address"),
    vault_token: str = typer.Option(..., "--vault-token", envvar="VAULT_TOKEN", help="Vault token"),
    vault_path: str = typer.Option("secret/data/nebula", "--vault-path", help="Vault secret path"),
    direction: str = typer.Option("pull", "--direction", "-d", help="Sync direction (pull/push)"),
    store_path: str = typer.Option(DEFAULT_SECRETS_PATH, "--store", "-s"),
):
    """Sync secrets with HashiCorp Vault."""
    try:
        import httpx
    except ImportError:
        console.print("[red]httpx required: pip install httpx[/red]")
        raise typer.Exit(1)

    manager = get_manager(store_path)

    async def do_sync():
        async with httpx.AsyncClient() as client:
            headers = {"X-Vault-Token": vault_token}

            if direction == "pull":
                # Pull from Vault to local
                console.print(f"[blue]Pulling secrets from Vault: {vault_path}[/blue]")

                resp = await client.get(
                    f"{vault_addr}/v1/{vault_path}",
                    headers=headers,
                )

                if resp.status_code != 200:
                    console.print(f"[red]Vault error: {resp.text}[/red]")
                    raise typer.Exit(1)

                vault_data = resp.json().get("data", {}).get("data", {})

                imported = 0
                for name, value in vault_data.items():
                    if isinstance(value, str):
                        success = await manager.create_secret(
                            name=name,
                            data={"value": value},
                            namespace="vault",
                        )
                        if success:
                            imported += 1

                console.print(f"[green]Imported {imported} secrets from Vault[/green]")

            else:
                # Push from local to Vault
                console.print(f"[blue]Pushing secrets to Vault: {vault_path}[/blue]")

                secrets_list = await manager.list_secrets()
                vault_data = {}

                for s_meta in secrets_list:
                    secret_data = await manager.get_secret(
                        s_meta["name"],
                        s_meta.get("namespace", "default")
                    )
                    if secret_data:
                        # Use first value or flatten
                        if len(secret_data) == 1:
                            vault_data[s_meta["name"]] = list(secret_data.values())[0]
                        else:
                            for k, v in secret_data.items():
                                vault_data[f"{s_meta['name']}_{k}"] = v

                resp = await client.post(
                    f"{vault_addr}/v1/{vault_path}",
                    headers=headers,
                    json={"data": vault_data},
                )

                if resp.status_code not in (200, 204):
                    console.print(f"[red]Vault error: {resp.text}[/red]")
                    raise typer.Exit(1)

                console.print(f"[green]Pushed {len(vault_data)} secrets to Vault[/green]")

    run_async(do_sync())


# =============================================================================
# Entry Point
# =============================================================================


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
