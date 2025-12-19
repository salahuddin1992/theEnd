"""
HA CLI - واجهة سطر الأوامر للتوفر العالي
==========================================

أوامر تشغيل وإدارة Masters عالية التوفر.
"""

from typing import Optional

import typer

app = typer.Typer(
    name="ha",
    help="أوامر التوفر العالي (High Availability)",
)


@app.command("start-master")
def start_ha_master(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="عنوان الاستماع"),
    port: int = typer.Option(8080, "--port", "-p", help="منفذ الاستماع"),
    master_id: Optional[str] = typer.Option(None, "--id", help="معرف Master (فريد)"),
    priority: int = typer.Option(0, "--priority", help="أولوية القيادة (أعلى = أولوية أكبر)"),
    peers: Optional[str] = typer.Option(
        None, "--peers",
        help="قائمة Masters الأخرى (مفصولة بفاصلة): host1:8080,host2:8080"
    ),
    mode: str = typer.Option(
        "active_standby", "--mode", "-m",
        help="نمط HA: standalone, active_standby, active_active"
    ),
    log_level: str = typer.Option("INFO", "--log-level", "-l"),
):
    """
    تشغيل Master server عالي التوفر.

    مثال:
        # Master الأول (أولوية عالية)
        dc-ha start-master --port 8080 --priority 100 --peers localhost:8081,localhost:8082

        # Master الثاني
        dc-ha start-master --port 8081 --priority 50 --peers localhost:8080,localhost:8082

        # Master الثالث
        dc-ha start-master --port 8082 --priority 25 --peers localhost:8080,localhost:8081
    """
    import logging
    logging.basicConfig(level=getattr(logging, log_level.upper()))

    from distributed_cluster.core.config import MasterConfig
    from distributed_cluster.master.ha import HAConfig, HAMasterServer, HAMode

    # Parse peers
    peer_list = []
    if peers:
        peer_list = [p.strip() for p in peers.split(",") if p.strip()]

    # Parse mode
    try:
        ha_mode = HAMode(mode)
    except ValueError:
        typer.echo(f"Invalid mode: {mode}. Use: standalone, active_standby, active_active")
        raise typer.Exit(1)

    # Create configs
    master_config = MasterConfig(
        host=host,
        port=port,
        log_level=log_level,
    )

    ha_config = HAConfig(
        mode=ha_mode,
        master_id=master_id or "",
        address=host if host != "0.0.0.0" else "localhost",
        port=port,
        priority=priority,
        peers=peer_list,
    )

    typer.echo("Starting HA Master server...")
    typer.echo(f"  Mode: {ha_mode.value}")
    typer.echo(f"  Address: {host}:{port}")
    typer.echo(f"  Priority: {priority}")
    typer.echo(f"  Peers: {peer_list}")

    # Start server
    server = HAMasterServer(master_config, ha_config)
    server.run()


@app.command("start-worker")
def start_ha_worker(
    masters: str = typer.Option(
        ..., "--masters", "-m",
        help="قائمة Masters (مفصولة بفاصلة): host1:8080,host2:8080,host3:8080"
    ),
    port: int = typer.Option(9000, "--port", "-p", help="منفذ العامل"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="وسوم (مفصولة بفاصلة)"),
    log_level: str = typer.Option("INFO", "--log-level", "-l"),
):
    """
    تشغيل Worker agent عالي التوفر.

    يتصل بأكثر من Master مع دعم التبديل التلقائي.

    مثال:
        dc-ha start-worker --masters localhost:8080,localhost:8081,localhost:8082
    """
    import asyncio
    import logging
    logging.basicConfig(level=getattr(logging, log_level.upper()))

    from distributed_cluster.core.config import WorkerConfig
    from distributed_cluster.worker.ha_agent import HAWorkerAgent, HAWorkerConfig

    # Parse masters
    master_list = [m.strip() for m in masters.split(",") if m.strip()]

    if not master_list:
        typer.echo("Error: At least one master is required")
        raise typer.Exit(1)

    # Parse tags
    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Create configs
    worker_config = WorkerConfig(
        port=port,
        tags=tag_list,
    )

    ha_config = HAWorkerConfig(
        masters=master_list,
    )

    typer.echo("Starting HA Worker agent...")
    typer.echo(f"  Masters: {master_list}")
    typer.echo(f"  Tags: {tag_list}")

    # Start agent
    agent = HAWorkerAgent(worker_config, ha_config)
    asyncio.run(agent.start())


@app.command("status")
def ha_status(
    master: str = typer.Option(
        "localhost:8080", "--master", "-m",
        help="عنوان Master للاستعلام"
    ),
):
    """
    عرض حالة التوفر العالي للكلاستر.
    """
    import httpx

    url = f"http://{master}/ha/status"

    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()

        typer.echo("\n=== HA Status ===")
        typer.echo(f"Mode: {data.get('mode', 'unknown')}")
        typer.echo(f"Master ID: {data.get('master_id', 'unknown')}")
        typer.echo(f"Role: {data.get('role', 'unknown')}")
        typer.echo(f"Is Leader: {data.get('is_leader', False)}")
        typer.echo(f"Is Active: {data.get('is_active', False)}")

        leader = data.get('current_leader')
        if leader:
            typer.echo("\nCurrent Leader:")
            typer.echo(f"  ID: {leader.get('master_id')}")
            typer.echo(f"  Address: {leader.get('address')}:{leader.get('port')}")
            typer.echo(f"  Term: {leader.get('term')}")

        election = data.get('election', {})
        if election:
            peers = election.get('peers', {})
            if peers:
                typer.echo(f"\nPeers ({len(peers)}):")
                for pid, pinfo in peers.items():
                    status = "✓" if pinfo.get('alive') else "✗"
                    typer.echo(f"  [{status}] {pid} - {pinfo.get('role', 'unknown')}")

        health = data.get('health', {})
        if health:
            summary = health.get('summary', {})
            typer.echo(f"\nCluster Health: {health.get('cluster_status', 'unknown')}")
            typer.echo(f"  Total: {summary.get('total_masters', 0)}")
            typer.echo(f"  Healthy: {summary.get('healthy', 0)}")
            typer.echo(f"  Degraded: {summary.get('degraded', 0)}")
            typer.echo(f"  Unhealthy: {summary.get('unhealthy', 0)}")

    except httpx.HTTPError as e:
        typer.echo(f"Error connecting to {master}: {e}")
        raise typer.Exit(1)


@app.command("failover")
def trigger_failover(
    master: str = typer.Option(
        "localhost:8080", "--master", "-m",
        help="عنوان Master لتحفيز التبديل"
    ),
):
    """
    تحفيز انتخاب قائد جديد (للاختبار).
    """
    import httpx

    typer.echo(f"Triggering election on {master}...")

    url = f"http://{master}/ha/election"

    try:
        resp = httpx.post(
            url,
            json={
                "master_id": "manual_trigger",
                "term": 0,
                "priority": 0,
            },
            timeout=5.0,
        )

        if resp.status_code == 200:
            typer.echo("Election triggered successfully")
        else:
            typer.echo(f"Failed: {resp.text}")

    except httpx.HTTPError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
