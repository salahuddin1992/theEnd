"""
Control CLI - واجهة التحكم الموحد
=================================

أمر واحد للتحكم الكامل في جميع الحواسيب.

الاستخدام:
    dc-control run "أي أمر"
    dc-control load set pc-2 95
    dc-control status
"""

import asyncio
import platform
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="dc-control",
    help="التحكم الكامل - Full Control CLI",
    add_completion=False,
)
console = Console()


# =============================================================================
# أوامر التنفيذ
# =============================================================================


@app.command("run")
def run_command(
    command: str = typer.Argument(..., help="الأمر للتنفيذ"),
    target: Optional[str] = typer.Option(None, "--on", "-o", help="Worker محدد (فارغ = محلي)"),
    all_workers: bool = typer.Option(False, "--all", "-a", help="تنفيذ على جميع Workers"),
    timeout: int = typer.Option(300, "--timeout", "-t", help="المهلة بالثواني"),
    admin: bool = typer.Option(False, "--admin", help="تشغيل كمسؤول"),
    master: str = typer.Option("http://localhost:8765", "--master", "-m", help="عنوان Master"),
) -> None:
    """
    تنفيذ أمر - الأمر الرئيسي للتحكم الكامل

    أمثلة:
        dc-control run "Get-Process"
        dc-control run "ls -la" --on worker-2
        dc-control run "pip install numpy" --all
    """
    from distributed_cluster.control.remote import RemoteController

    async def execute():
        async with RemoteController(master) as controller:
            if all_workers:
                # تنفيذ على الجميع
                console.print("[bold blue]تنفيذ على جميع Workers...[/]")
                results = await controller.execute_all(
                    command,
                    timeout=timeout,
                    run_as_admin=admin,
                )
                for result in results:
                    _print_result(result)

            elif target:
                # تنفيذ على Worker محدد
                console.print(f"[bold blue]تنفيذ على {target}...[/]")
                result = await controller.execute_on(
                    target,
                    command,
                    timeout=timeout,
                    run_as_admin=admin,
                )
                _print_result(result)

            else:
                # تنفيذ محلي
                result = await controller.execute_local(command, timeout=timeout)
                _print_result(result)

    asyncio.run(execute())


@app.command("ps")
def powershell(
    command: str = typer.Argument(..., help="أمر PowerShell"),
    admin: bool = typer.Option(False, "--admin", "-a", help="تشغيل كمسؤول"),
    timeout: int = typer.Option(300, "--timeout", "-t", help="المهلة"),
) -> None:
    """
    تنفيذ PowerShell مباشرة (Windows)

    أمثلة:
        dc-control ps "Get-Process | Select -First 5"
        dc-control ps "Get-Service | Where-Object {$_.Status -eq 'Running'}"
        dc-control ps "Set-ExecutionPolicy Bypass -Scope Process" --admin
    """
    if platform.system() != "Windows":
        console.print("[yellow]تحذير: أنت لست على Windows، سيتم استخدام pwsh إذا متوفر[/]")

    from distributed_cluster.control.remote import run_command

    result = run_command(command, timeout=timeout)
    _print_result(result)


@app.command("bash")
def bash_command(
    command: str = typer.Argument(..., help="أمر Bash"),
    timeout: int = typer.Option(300, "--timeout", "-t", help="المهلة"),
) -> None:
    """
    تنفيذ Bash مباشرة (Linux/Mac)

    أمثلة:
        dc-control bash "ls -la && pwd"
        dc-control bash "docker ps"
    """
    from distributed_cluster.control.remote import run_command

    result = run_command(command, timeout=timeout)
    _print_result(result)


@app.command("exec")
def execute_file(
    file_path: str = typer.Argument(..., help="مسار الملف للتنفيذ"),
    args: Optional[str] = typer.Option(None, "--args", "-a", help="معاملات إضافية"),
    target: Optional[str] = typer.Option(None, "--on", "-o", help="Worker محدد"),
    timeout: int = typer.Option(600, "--timeout", "-t", help="المهلة"),
) -> None:
    """
    تنفيذ ملف (script أو برنامج)

    أمثلة:
        dc-control exec script.py
        dc-control exec script.ps1 --on worker-2
        dc-control exec program.exe --args "--input data.txt"
    """
    from distributed_cluster.control.remote import RemoteController

    # تحديد كيفية التنفيذ
    if file_path.endswith(".py"):
        command = f"python {file_path}"
    elif file_path.endswith(".ps1"):
        command = f"powershell.exe -ExecutionPolicy Bypass -File {file_path}"
    elif file_path.endswith(".sh"):
        command = f"bash {file_path}"
    else:
        command = file_path

    if args:
        command += f" {args}"

    async def execute():
        async with RemoteController() as controller:
            if target:
                result = await controller.execute_on(target, command, timeout=timeout)
            else:
                result = await controller.execute_local(command, timeout=timeout)
            _print_result(result)

    asyncio.run(execute())


# =============================================================================
# أوامر توزيع الحمل
# =============================================================================

load_app = typer.Typer(help="إدارة توزيع الحمل")
app.add_typer(load_app, name="load")


@load_app.command("set")
def set_load(
    worker: str = typer.Argument(..., help="معرف Worker"),
    percentage: int = typer.Argument(95, help="نسبة الحمل (0-100)"),
    master: str = typer.Option("http://localhost:8765", "--master", "-m"),
) -> None:
    """
    تعيين نسبة الحمل لحاسوب

    أمثلة:
        dc-control load set pc-2 95
        dc-control load set worker-3 50
    """
    from distributed_cluster.control.load_balancer import LoadBalancer

    async def run():
        async with LoadBalancer(master) as balancer:
            success = await balancer.offload_to(worker, percentage)
            if success:
                console.print(f"[green]✓[/] تم نقل {percentage}% من الحمل إلى {worker}")
                console.print(f"    الحاسوب المحلي: {100 - percentage}%")
            else:
                console.print("[red]✗[/] فشل في تعيين التوزيع")

    asyncio.run(run())


@load_app.command("distribute")
def distribute_load(
    distribution: str = typer.Argument(..., help="التوزيع: worker1:50,worker2:45,local:5"),
    master: str = typer.Option("http://localhost:8765", "--master", "-m"),
) -> None:
    """
    توزيع الحمل على عدة حواسيب

    أمثلة:
        dc-control load distribute "pc-2:47,pc-3:48,local:5"
        dc-control load distribute "worker-1:33,worker-2:33,worker-3:34"
    """
    from distributed_cluster.control.load_balancer import LoadBalancer

    # تحليل التوزيع
    percentages = {}
    for item in distribution.split(","):
        parts = item.strip().split(":")
        if len(parts) == 2:
            worker_id = parts[0].strip()
            pct = int(parts[1].strip())
            percentages[worker_id] = pct

    async def run():
        async with LoadBalancer(master) as balancer:
            success = await balancer.set_distribution(percentages)
            if success:
                console.print("[green]✓[/] تم تعيين التوزيع:")
                for w, p in percentages.items():
                    console.print(f"    {w}: {p}%")
            else:
                console.print("[red]✗[/] فشل في تعيين التوزيع")

    asyncio.run(run())


@load_app.command("equal")
def equal_distribution(
    master: str = typer.Option("http://localhost:8765", "--master", "-m"),
) -> None:
    """توزيع الحمل بالتساوي"""
    from distributed_cluster.control.load_balancer import LoadBalancer

    async def run():
        async with LoadBalancer(master) as balancer:
            success = await balancer.balance_equally()
            if success:
                console.print("[green]✓[/] تم توزيع الحمل بالتساوي")
            else:
                console.print("[red]✗[/] لا يوجد Workers متصلين")

    asyncio.run(run())


@load_app.command("status")
def load_status(
    master: str = typer.Option("http://localhost:8765", "--master", "-m"),
) -> None:
    """عرض حالة توزيع الحمل"""
    from distributed_cluster.control.load_balancer import LoadBalancer

    async def run():
        async with LoadBalancer(master) as balancer:
            load = await balancer.get_cluster_load()

            table = Table(title="حالة الكلاستر")
            table.add_column("العنصر", style="cyan")
            table.add_column("القيمة", style="green")

            table.add_row("Workers الكلي", str(load.total_workers))
            table.add_row("Workers النشطين", str(load.active_workers))
            table.add_row("المهام الكلية", str(load.total_jobs))
            table.add_row("المهام الجارية", str(load.running_jobs))
            table.add_row("المهام المعلقة", str(load.pending_jobs))

            console.print(table)

            if load.distributions:
                console.print("\n[bold]توزيع الحمل:[/]")
                for d in load.distributions:
                    bar = "█" * (d.percentage // 5) + "░" * (20 - d.percentage // 5)
                    console.print(f"  {d.worker_id}: [{bar}] {d.percentage}%")

    asyncio.run(run())


# =============================================================================
# أوامر Workers
# =============================================================================


@app.command("workers")
def list_workers(
    master: str = typer.Option("http://localhost:8765", "--master", "-m"),
) -> None:
    """عرض Workers المتصلين"""
    from distributed_cluster.control.remote import RemoteController

    async def run():
        async with RemoteController(master) as controller:
            workers = await controller.get_workers()

            if not workers:
                console.print("[yellow]لا يوجد Workers متصلين[/]")
                return

            table = Table(title="Workers المتصلين")
            table.add_column("ID", style="cyan")
            table.add_column("الحالة", style="green")
            table.add_column("CPU", style="yellow")
            table.add_column("RAM", style="yellow")
            table.add_column("GPU", style="magenta")

            for w in workers:
                status = "🟢 متصل" if w.get("status") == "online" else "🔴 غير متصل"
                resources = w.get("resources", {})
                cpu = f"{resources.get('cpu_cores', '?')} cores"
                ram = f"{resources.get('memory_total_gb', '?'):.1f} GB" if resources.get("memory_total_gb") else "?"
                gpu = resources.get("gpu_count", 0)
                gpu_str = f"{gpu} GPU" if gpu else "-"

                table.add_row(w.get("worker_id", "?"), status, cpu, ram, gpu_str)

            console.print(table)

    asyncio.run(run())


@app.command("status")
def cluster_status(
    master: str = typer.Option("http://localhost:8765", "--master", "-m"),
) -> None:
    """عرض حالة الكلاستر"""
    import httpx

    try:
        response = httpx.get(f"{master}/api/status", timeout=10)
        if response.status_code == 200:
            data = response.json()
            console.print(
                Panel(
                    f"[green]✓[/] الكلاستر متصل\n"
                    f"Workers: {data.get('workers_count', 0)}\n"
                    f"Jobs: {data.get('jobs_count', 0)}",
                    title="حالة الكلاستر",
                )
            )
        else:
            console.print(f"[red]✗[/] فشل الاتصال: HTTP {response.status_code}")
    except Exception as e:
        console.print(f"[red]✗[/] فشل الاتصال: {e}")


# =============================================================================
# الأمر السريع الواحد
# =============================================================================


@app.command("quick")
def quick_command(
    action: str = typer.Argument(..., help="الإجراء: run/load/status"),
    args: Optional[str] = typer.Argument(None, help="المعاملات"),
) -> None:
    """
    الأمر السريع - كل شيء بأمر واحد

    أمثلة:
        dc-control quick run "Get-Process"
        dc-control quick load "pc-2:95"
        dc-control quick status
    """
    if action == "status":
        cluster_status()
    elif action == "run" and args:
        run_command(args)
    elif action == "load" and args:
        if ":" in args:
            distribute_load(args)
        else:
            console.print("[red]صيغة خاطئة. استخدم: worker:percentage[/]")
    else:
        console.print("[yellow]الإجراءات المتاحة: run, load, status[/]")


# =============================================================================
# Helper Functions
# =============================================================================


def _print_result(result) -> None:
    """طباعة نتيجة التنفيذ"""
    if result.success:
        header = f"[green]✓[/] {result.worker_id} ({result.execution_time:.2f}s)"
    else:
        header = f"[red]✗[/] {result.worker_id} (exit: {result.exit_code})"

    console.print(header)

    if result.output:
        console.print(Panel(result.output.strip(), title="Output", border_style="green"))

    if result.error:
        console.print(Panel(result.error.strip(), title="Error", border_style="red"))


def main():
    """نقطة الدخول الرئيسية"""
    app()


if __name__ == "__main__":
    main()
