"""
Web Dashboard CLI - أوامر واجهة الويب

dc-web start    - بدء واجهة الويب
dc-web open     - فتح الواجهة في المتصفح
"""

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="dc-web",
    help="Distributed Cluster Web Dashboard",
)
console = Console()


@app.command("start")
def start_dashboard(
    port: int = typer.Option(8080, "--port", "-p", help="منفذ واجهة الويب"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="عنوان الاستماع"),
    master: str = typer.Option("http://localhost:8765", "--master", "-m", help="عنوان Master"),
    reload: bool = typer.Option(False, "--reload", help="إعادة التحميل التلقائي (للتطوير)"),
):
    """
    بدء واجهة الويب

    مثال:
        dc-web start
        dc-web start --port 3000 --master http://192.168.1.10:8765
    """
    import uvicorn

    from ..web.app import WebDashboard

    console.print(
        Panel(
            f"[bold green]🌐 Starting Web Dashboard[/bold green]\n\n"
            f"URL: http://{host if host != '0.0.0.0' else 'localhost'}:{port}\n"
            f"Master: {master}\n\n"
            f"[dim]Press Ctrl+C to stop[/dim]",
            title="Web Dashboard",
        )
    )

    # إنشاء التطبيق
    dashboard = WebDashboard(master_url=master)
    app = dashboard.app

    # تشغيل الخادم
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command("open")
def open_browser(
    url: str = typer.Option("http://localhost:8080", "--url", "-u", help="عنوان الواجهة"),
):
    """
    فتح واجهة الويب في المتصفح
    """
    import webbrowser

    console.print(f"[blue]🌐 Opening {url}...[/blue]")
    webbrowser.open(url)


def main():
    """نقطة الدخول الرئيسية"""
    app()


if __name__ == "__main__":
    main()
