"""
Notifications CLI - أوامر نظام الإشعارات

dc-notify test      - اختبار إرسال إشعار
dc-notify config    - عرض/تعديل الإعدادات
dc-notify history   - عرض سجل الإشعارات
"""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..notifications import (
    ConsoleChannel,
    DiscordChannel,
    Notification,
    NotificationCategory,
    NotificationPriority,
    Notifier,
    SlackChannel,
    WebhookChannel,
)

app = typer.Typer(
    name="dc-notify",
    help="Distributed Cluster Notification System - نظام الإشعارات",
)
console = Console()


@app.command("test")
def test_notification(
    channel: str = typer.Option("console", "--channel", "-c", help="القناة للاختبار"),
    title: str = typer.Option("اختبار إشعار", "--title", "-t", help="عنوان الإشعار"),
    message: str = typer.Option("هذا إشعار تجريبي من نظام الكلاستر", "--message", "-m", help="نص الإشعار"),
    priority: str = typer.Option("normal", "--priority", "-p", help="الأولوية (low, normal, high, critical)"),
    webhook_url: Optional[str] = typer.Option(None, "--webhook", "-w", help="URL للـ webhook"),
):
    """
    اختبار إرسال إشعار

    مثال:
        dc-notify test
        dc-notify test --channel slack --webhook https://hooks.slack.com/...
        dc-notify test --priority critical --title "تنبيه هام"
    """

    async def run():
        notifier = Notifier()

        # إضافة القناة
        if channel == "console":
            notifier.add_channel(ConsoleChannel())
        elif channel == "slack" and webhook_url:
            notifier.add_channel(SlackChannel(webhook_url=webhook_url))
        elif channel == "discord" and webhook_url:
            notifier.add_channel(DiscordChannel(webhook_url=webhook_url))
        elif channel == "webhook" and webhook_url:
            notifier.add_channel(WebhookChannel(name="webhook", url=webhook_url))
        else:
            notifier.add_channel(ConsoleChannel())

        # تحديد الأولوية
        priority_map = {
            "low": NotificationPriority.LOW,
            "normal": NotificationPriority.NORMAL,
            "high": NotificationPriority.HIGH,
            "critical": NotificationPriority.CRITICAL,
        }
        prio = priority_map.get(priority, NotificationPriority.NORMAL)

        # إنشاء وإرسال الإشعار
        notification = Notification(
            title=title,
            message=message,
            category=NotificationCategory.SYSTEM,
            priority=prio,
            data={"source": "cli", "test": True},
        )

        console.print("\n[blue]📤 إرسال إشعار تجريبي...[/blue]\n")

        results = await notifier.notify_immediate(notification)

        for ch_name, success in results.items():
            if success:
                console.print(f"[green]✅ {ch_name}: تم الإرسال بنجاح[/green]")
            else:
                console.print(f"[red]❌ {ch_name}: فشل الإرسال[/red]")

    asyncio.run(run())


@app.command("send")
def send_notification(
    category: str = typer.Argument(..., help="التصنيف (job_completed, job_failed, worker_offline, ...)"),
    title: str = typer.Option(..., "--title", "-t", help="عنوان الإشعار"),
    message: str = typer.Option(..., "--message", "-m", help="نص الإشعار"),
    priority: str = typer.Option("normal", "--priority", "-p", help="الأولوية"),
    webhook_url: Optional[str] = typer.Option(None, "--webhook", "-w", help="URL للـ webhook"),
):
    """
    إرسال إشعار

    مثال:
        dc-notify send job_failed -t "فشلت المهمة" -m "المهمة X فشلت بسبب نفاد الذاكرة"
    """

    async def run():
        notifier = Notifier()

        if webhook_url:
            notifier.add_channel(WebhookChannel(name="webhook", url=webhook_url))
        else:
            notifier.add_channel(ConsoleChannel())

        # تحديد التصنيف
        try:
            cat = NotificationCategory(category)
        except ValueError:
            console.print(f"[red]❌ تصنيف غير معروف: {category}[/red]")
            console.print(f"التصنيفات المتاحة: {', '.join(c.value for c in NotificationCategory)}")
            raise typer.Exit(1)

        # تحديد الأولوية
        priority_map = {
            "low": NotificationPriority.LOW,
            "normal": NotificationPriority.NORMAL,
            "high": NotificationPriority.HIGH,
            "critical": NotificationPriority.CRITICAL,
        }
        prio = priority_map.get(priority, NotificationPriority.NORMAL)

        notification = Notification(
            title=title,
            message=message,
            category=cat,
            priority=prio,
        )

        results = await notifier.notify_immediate(notification)

        for ch_name, success in results.items():
            if success:
                console.print("[green]✅ تم الإرسال[/green]")
            else:
                console.print("[red]❌ فشل الإرسال[/red]")

    asyncio.run(run())


@app.command("categories")
def list_categories():
    """
    عرض تصنيفات الإشعارات المتاحة
    """
    table = Table(title="📂 تصنيفات الإشعارات")
    table.add_column("التصنيف", style="cyan")
    table.add_column("الوصف", style="white")

    descriptions = {
        NotificationCategory.JOB_COMPLETED: "اكتملت مهمة بنجاح",
        NotificationCategory.JOB_FAILED: "فشلت مهمة",
        NotificationCategory.JOB_TIMEOUT: "انتهى وقت مهمة",
        NotificationCategory.WORKER_ONLINE: "اتصل عامل جديد",
        NotificationCategory.WORKER_OFFLINE: "انقطع عامل",
        NotificationCategory.WORKER_ERROR: "خطأ في عامل",
        NotificationCategory.CLUSTER_ALERT: "تنبيه عام للكلاستر",
        NotificationCategory.SYSTEM: "إشعار نظام",
    }

    for cat in NotificationCategory:
        table.add_row(cat.value, descriptions.get(cat, ""))

    console.print(table)


@app.command("channels")
def list_channels():
    """
    عرض قنوات الإشعارات المتاحة
    """
    table = Table(title="📡 قنوات الإشعارات")
    table.add_column("القناة", style="cyan")
    table.add_column("الوصف", style="white")
    table.add_column("المتطلبات", style="yellow")

    channels_info = [
        ("console", "طباعة في الـ Terminal", "لا شيء"),
        ("slack", "Slack Webhook", "webhook_url"),
        ("discord", "Discord Webhook", "webhook_url"),
        ("telegram", "Telegram Bot", "bot_token, chat_id"),
        ("email", "البريد الإلكتروني", "SMTP config"),
        ("webhook", "أي Webhook مخصص", "url"),
    ]

    for name, desc, req in channels_info:
        table.add_row(name, desc, req)

    console.print(table)


@app.command("example")
def show_example():
    """
    عرض مثال على استخدام الإشعارات
    """
    example_code = """
# استخدام نظام الإشعارات في الكود

from distributed_cluster.notifications import (
    Notifier,
    SlackChannel,
    DiscordChannel,
    ConsoleChannel,
)

async def main():
    # إنشاء المدير
    notifier = Notifier()

    # إضافة القنوات
    notifier.add_channel(ConsoleChannel())
    notifier.add_channel(SlackChannel(
        webhook_url="https://hooks.slack.com/services/XXX"
    ))
    notifier.add_channel(DiscordChannel(
        webhook_url="https://discord.com/api/webhooks/XXX"
    ))

    # بدء المعالج
    await notifier.start()

    # إرسال إشعارات
    await notifier.job_completed(
        job_id="job-123",
        job_name="Training Model",
        duration=3600.5,
    )

    await notifier.job_failed(
        job_id="job-456",
        job_name="Data Processing",
        error="Out of memory",
    )

    await notifier.worker_offline(
        worker_id="worker-1",
        hostname="node-1.local",
    )

    # إيقاف
    await notifier.stop()
"""

    console.print(
        Panel(
            example_code,
            title="مثال على استخدام نظام الإشعارات",
            border_style="blue",
        )
    )


def main():
    """نقطة الدخول الرئيسية"""
    app()


if __name__ == "__main__":
    main()
