"""
Mesh Network CLI - أوامر شبكة Mesh

dc-mesh start     - بدء عقدة mesh
dc-mesh join      - الانضمام لشبكة موجودة
dc-mesh peers     - عرض العقد المتصلة
dc-mesh status    - حالة العقدة
dc-mesh submit    - إرسال مهمة للشبكة
"""

import asyncio
import signal
import warnings
from typing import List, Optional

# Suppress pynvml deprecation warning
warnings.filterwarnings("ignore", category=FutureWarning, module="pynvml")

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..mesh.discovery import DiscoveryMethod
from ..mesh.node import MeshNode
from ..mesh.router import RoutingStrategy

app = typer.Typer(
    name="dc-mesh",
    help="Distributed Cluster Mesh Network - شبكة لامركزية",
)
console = Console()


def create_status_table(node: MeshNode) -> Table:
    """إنشاء جدول الحالة"""
    table = Table(title="🔗 Mesh Node Status", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    info = node.get_cluster_info()

    table.add_row("Node ID", info["node_id"])
    table.add_row("State", info["state"])
    table.add_row("Is Leader", "✅ Yes" if info["is_leader"] else "❌ No")
    table.add_row("Leader ID", info["leader_id"] or "None")
    table.add_row("Connected Peers", str(info["peer_count"]))
    table.add_row("Local Jobs", str(info["local_jobs"]))
    table.add_row("CPU", f"{info['resources']['cpu_cores']} cores ({info['usage']['cpu_percent']:.1f}%)")
    table.add_row("Memory", f"{info['resources']['memory_mb']} MB ({info['usage']['memory_percent']:.1f}%)")
    table.add_row("GPU", str(info["resources"]["gpu_count"]))

    return table


def create_peers_table(node: MeshNode) -> Table:
    """إنشاء جدول العقد المتصلة"""
    table = Table(title="👥 Connected Peers", show_header=True)
    table.add_column("Node ID", style="cyan")
    table.add_column("Address", style="blue")
    table.add_column("State", style="green")
    table.add_column("Resources", style="yellow")
    table.add_column("Latency", style="magenta")

    for peer in node.peers.values():
        resources = f"CPU:{peer.resources.cpu_cores} RAM:{peer.resources.memory_mb}MB"
        table.add_row(
            peer.node_id,
            peer.address,
            peer.state,
            resources,
            f"{peer.latency_ms:.1f}ms",
        )

    return table


@app.command("start")
def start_node(
    port: int = typer.Option(9000, "--port", "-p", help="منفذ الاستماع"),
    node_id: Optional[str] = typer.Option(None, "--id", help="معرف العقدة"),
    bootstrap: Optional[List[str]] = typer.Option(None, "--bootstrap", "-b", help="عناوين عقد للاتصال بها"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="علامات مفصولة بفاصلة"),
    strategy: str = typer.Option("least_loaded", "--strategy", "-s", help="استراتيجية التوجيه"),
    no_multicast: bool = typer.Option(False, "--no-multicast", help="تعطيل اكتشاف multicast"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="وضع تفاعلي مع عرض مستمر"),
):
    """
    بدء عقدة Mesh جديدة

    مثال:
        dc-mesh start --port 9000
        dc-mesh start --bootstrap 192.168.1.10:9000
        dc-mesh start --tags gpu,high-memory
    """
    # تحديد طرق الاكتشاف
    discovery_methods = [DiscoveryMethod.GOSSIP]
    if not no_multicast:
        discovery_methods.append(DiscoveryMethod.MULTICAST)
    if bootstrap:
        discovery_methods.append(DiscoveryMethod.BOOTSTRAP)

    # تحديد استراتيجية التوجيه
    try:
        routing_strategy = RoutingStrategy(strategy)
    except ValueError:
        console.print(f"[red]استراتيجية غير معروفة: {strategy}[/red]")
        console.print(f"الاستراتيجيات المتاحة: {', '.join(s.value for s in RoutingStrategy)}")
        raise typer.Exit(1)

    # تحديد العلامات
    node_tags = set(tags.split(",")) if tags else set()

    console.print(
        Panel(
            f"[bold green]🚀 Starting Mesh Node[/bold green]\n\n"
            f"Port: {port}\n"
            f"Discovery: {', '.join(m.value for m in discovery_methods)}\n"
            f"Strategy: {routing_strategy.value}\n"
            f"Tags: {', '.join(node_tags) or 'none'}",
            title="Mesh Network",
        )
    )

    async def run():
        node = MeshNode(
            port=port,
            node_id=node_id,
            tags=node_tags,
            discovery_methods=discovery_methods,
            routing_strategy=routing_strategy,
            bootstrap_peers=bootstrap or [],
        )

        # معالجة الإشارات
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def signal_handler():
            console.print("\n[yellow]⏳ Shutting down...[/yellow]")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        # معالجة الأحداث
        def on_peer_added(data):
            console.print(f"[green]✅ Peer connected: {data['peer_id']}[/green]")

        def on_peer_removed(data):
            console.print(f"[red]❌ Peer disconnected: {data['peer_id']}[/red]")

        def on_became_leader(data):
            console.print(f"[bold yellow]👑 Became leader (term {data['term']})[/bold yellow]")

        def on_new_leader(data):
            console.print(f"[blue]👑 New leader: {data['leader_id']}[/blue]")

        node.on("peer_added", on_peer_added)
        node.on("peer_removed", on_peer_removed)
        node.on("became_leader", on_became_leader)
        node.on("new_leader", on_new_leader)

        # بدء العقدة
        await node.start()
        console.print(f"[green]✅ Node started: {node.node_id}[/green]")
        console.print(f"[blue]📡 Listening on port {port}[/blue]")

        if interactive:
            # عرض تفاعلي
            console.print("[dim]Press Ctrl+C to stop[/dim]\n")
            try:
                while not stop_event.is_set():
                    # مسح وعرض الحالة
                    console.clear()
                    console.print(create_status_table(node))
                    console.print()
                    console.print(create_peers_table(node))
                    console.print("\n[dim]Refreshing every 2 seconds... Press Ctrl+C to stop[/dim]")
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                pass
        else:
            # وضع غير تفاعلي
            await stop_event.wait()

        await node.stop()
        console.print("[green]✅ Node stopped[/green]")

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


@app.command("join")
def join_network(
    address: str = typer.Argument(..., help="عنوان عقدة للانضمام (host:port)"),
    port: int = typer.Option(9000, "--port", "-p", help="منفذ الاستماع المحلي"),
):
    """
    الانضمام لشبكة Mesh موجودة

    مثال:
        dc-mesh join 192.168.1.10:9000
    """
    console.print(f"[blue]🔗 Joining network via {address}...[/blue]")

    async def run():
        node = MeshNode(
            port=port,
            bootstrap_peers=[address],
            discovery_methods=[DiscoveryMethod.BOOTSTRAP, DiscoveryMethod.GOSSIP],
        )

        await node.start()

        # انتظار الاتصال
        for _ in range(10):
            if node.peer_count > 0:
                break
            await asyncio.sleep(1)

        if node.peer_count > 0:
            console.print(f"[green]✅ Connected to {node.peer_count} peer(s)[/green]")
            console.print(create_peers_table(node))
        else:
            console.print(f"[red]❌ Failed to connect to {address}[/red]")

        await node.stop()

    asyncio.run(run())


@app.command("peers")
def list_peers(
    address: str = typer.Option("localhost:9000", "--address", "-a", help="عنوان العقدة"),
):
    """
    عرض العقد المتصلة
    """

    # ملاحظة: هذا يحتاج API endpoint - للتبسيط نعرض رسالة
    console.print("[yellow]⚠️ Use 'dc-mesh start --interactive' to see live peers[/yellow]")


@app.command("status")
def show_status(
    address: str = typer.Option("localhost:9000", "--address", "-a", help="عنوان العقدة"),
):
    """
    عرض حالة العقدة
    """
    console.print("[yellow]⚠️ Use 'dc-mesh start --interactive' to see live status[/yellow]")


async def _submit_job_to_node(
    host: str,
    port: int,
    command: str,
    cpu: float,
    memory: int,
    gpu: int,
    timeout: int,
) -> dict:
    """Submit a job to a mesh node via TCP connection."""
    import json
    import uuid
    from datetime import datetime

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=10.0
        )

        # Create job submission message
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        message = {
            "type": "job_submit",
            "sender_id": f"cli-{uuid.uuid4().hex[:8]}",
            "data": {
                "job_id": job_id,
                "command": command,
                "resources": {
                    "cpu_cores": cpu,
                    "memory_mb": memory,
                    "gpu_count": gpu,
                },
                "timeout_seconds": timeout,
            },
            "message_id": uuid.uuid4().hex[:12],
            "timestamp": datetime.utcnow().isoformat(),
            "ttl": 5,
        }

        # Send message
        writer.write((json.dumps(message) + "\n").encode())
        await writer.drain()

        # Wait for response
        response_data = await asyncio.wait_for(reader.readline(), timeout=30.0)
        writer.close()
        await writer.wait_closed()

        if response_data:
            return {"success": True, "job_id": job_id, "response": json.loads(response_data.decode())}
        else:
            return {"success": True, "job_id": job_id, "response": None}

    except asyncio.TimeoutError:
        return {"success": False, "error": "Connection timeout"}
    except ConnectionRefusedError:
        return {"success": False, "error": "Connection refused - is the mesh node running?"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.command("submit")
def submit_job(
    command: str = typer.Argument(..., help="الأمر للتنفيذ"),
    cpu: float = typer.Option(1.0, "--cpu", help="عدد أنوية CPU"),
    memory: int = typer.Option(512, "--memory", "-m", help="الذاكرة بـ MB"),
    gpu: int = typer.Option(0, "--gpu", help="عدد GPUs"),
    timeout: int = typer.Option(300, "--timeout", "-t", help="الحد الأقصى بالثواني"),
    address: str = typer.Option("localhost:9000", "--address", "-a", help="عنوان عقدة"),
):
    """
    إرسال مهمة للشبكة

    مثال:
        dc-mesh submit "echo hello"
        dc-mesh submit "python train.py" --cpu 4 --memory 8192 --gpu 1
    """
    console.print(f"[blue]📤 Submitting job: {command}[/blue]")
    console.print(f"[dim]Resources: CPU={cpu}, Memory={memory}MB, GPU={gpu}[/dim]")
    console.print(f"[dim]Target node: {address}[/dim]")

    # Parse address
    if ":" in address:
        host, port_str = address.rsplit(":", 1)
        port = int(port_str)
    else:
        host = address
        port = 9000

    # Submit job
    with console.status("[bold green]Connecting to mesh node..."):
        result = asyncio.run(_submit_job_to_node(
            host=host,
            port=port,
            command=command,
            cpu=cpu,
            memory=memory,
            gpu=gpu,
            timeout=timeout,
        ))

    if result["success"]:
        console.print("[green]✓ Job submitted successfully![/green]")
        console.print(f"[cyan]Job ID: {result['job_id']}[/cyan]")
        if result.get("response"):
            console.print(f"[dim]Response: {result['response']}[/dim]")
    else:
        console.print(f"[red]✗ Failed to submit job: {result['error']}[/red]")
        console.print("[yellow]Tip: Make sure a mesh node is running with 'dc-mesh start'[/yellow]")


@app.command("info")
def show_info():
    """
    عرض معلومات الجهاز المحلي
    """
    import socket

    import psutil

    table = Table(title="💻 Local System Info", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Hostname", socket.gethostname())
    table.add_row("CPU Cores", str(psutil.cpu_count()))
    table.add_row("CPU Usage", f"{psutil.cpu_percent()}%")
    table.add_row("Memory Total", f"{psutil.virtual_memory().total // (1024**2)} MB")
    table.add_row("Memory Used", f"{psutil.virtual_memory().percent}%")

    # GPU
    gpu_count = 0
    try:
        import pynvml

        pynvml.nvmlInit()
        gpu_count = pynvml.nvmlDeviceGetCount()
        pynvml.nvmlShutdown()
    except Exception:
        pass
    table.add_row("GPUs", str(gpu_count))

    console.print(table)


def main():
    """نقطة الدخول الرئيسية"""
    app()


if __name__ == "__main__":
    main()
