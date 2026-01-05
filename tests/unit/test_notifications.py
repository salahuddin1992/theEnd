"""
Tests for Notification System
اختبارات نظام الإشعارات
"""

import asyncio

import pytest

from distributed_cluster.notifications.channels import (
    ConsoleChannel,
    DiscordChannel,
    SlackChannel,
    WebhookChannel,
)
from distributed_cluster.notifications.notifier import (
    Notification,
    NotificationCategory,
    NotificationPriority,
    Notifier,
)
from distributed_cluster.notifications.rules import (
    NotificationRule,
    RuleCondition,
    RuleEngine,
)


class TestNotification:
    """اختبارات Notification"""

    def test_notification_creation(self):
        """اختبار إنشاء إشعار"""
        notification = Notification(
            title="Test Title",
            message="Test message",
            category=NotificationCategory.SYSTEM,
        )
        assert notification.title == "Test Title"
        assert notification.category == NotificationCategory.SYSTEM
        assert notification.priority == NotificationPriority.NORMAL
        assert notification.notification_id != ""

    def test_notification_with_priority(self):
        """اختبار إشعار بأولوية"""
        notification = Notification(
            title="Critical Alert",
            message="Something critical happened",
            category=NotificationCategory.CLUSTER_ALERT,
            priority=NotificationPriority.CRITICAL,
        )
        assert notification.priority == NotificationPriority.CRITICAL

    def test_notification_to_dict(self):
        """اختبار تحويل لـ dict"""
        notification = Notification(
            title="Test",
            message="Test message",
            category=NotificationCategory.JOB_COMPLETED,
            data={"job_id": "123"},
        )
        d = notification.to_dict()
        assert d["title"] == "Test"
        assert d["category"] == "job_completed"
        assert d["data"]["job_id"] == "123"

    def test_notification_emoji(self):
        """اختبار الإيموجي"""
        n1 = Notification(title="", message="", category=NotificationCategory.JOB_COMPLETED)
        assert n1.emoji == "✅"

        n2 = Notification(title="", message="", category=NotificationCategory.JOB_FAILED)
        assert n2.emoji == "❌"

    def test_notification_color(self):
        """اختبار اللون"""
        n1 = Notification(
            title="",
            message="",
            category=NotificationCategory.SYSTEM,
            priority=NotificationPriority.CRITICAL,
        )
        assert n1.color == "#ff0000"


class TestConsoleChannel:
    """اختبارات ConsoleChannel"""

    def test_channel_creation(self):
        """اختبار إنشاء القناة"""
        channel = ConsoleChannel()
        assert channel.name == "console"
        assert channel.enabled is True

    @pytest.mark.asyncio
    async def test_send_notification(self):
        """اختبار إرسال إشعار"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification

        channel = ConsoleChannel(colored=False)
        # Use channels.py Notification format
        notification = ChannelNotification(
            title="Test",
            message="Test message",
        )
        result = await channel._do_send(notification)
        assert result is True

    @pytest.mark.asyncio
    async def test_safe_send(self):
        """اختبار الإرسال الآمن عبر send_notification"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification

        channel = ConsoleChannel(colored=False)
        notification = ChannelNotification(
            title="Test",
            message="Test message",
        )
        result = await channel.send_notification(notification)
        # send_notification returns DeliveryResult
        assert result.success is True
        assert channel.metrics.total_sent == 1


class TestNotifier:
    """اختبارات Notifier"""

    def test_notifier_creation(self):
        """اختبار إنشاء المدير"""
        notifier = Notifier()
        assert len(notifier.channels) == 0
        assert len(notifier.history) == 0

    def test_add_channel(self):
        """اختبار إضافة قناة"""
        notifier = Notifier()
        channel = ConsoleChannel()
        notifier.add_channel(channel)
        assert "console" in notifier.channels

    def test_remove_channel(self):
        """اختبار إزالة قناة"""
        notifier = Notifier()
        notifier.add_channel(ConsoleChannel())
        notifier.remove_channel("console")
        assert "console" not in notifier.channels

    @pytest.mark.asyncio
    async def test_notify_immediate(self):
        """اختبار الإرسال الفوري"""
        notifier = Notifier()
        notifier.add_channel(ConsoleChannel(colored=False))

        notification = Notification(
            title="Test",
            message="Test message",
            category=NotificationCategory.SYSTEM,
        )

        results = await notifier.notify_immediate(notification)
        # Results may be bool or truthy depending on channel interface
        assert "console" in results
        assert len(notifier.history) == 1

    @pytest.mark.asyncio
    async def test_job_completed_notification(self):
        """اختبار إشعار اكتمال المهمة"""
        notifier = Notifier()
        notifier.add_channel(ConsoleChannel(colored=False))
        await notifier.start()

        await notifier.job_completed(
            job_id="job-123",
            job_name="Test Job",
            duration=60.5,
        )

        await asyncio.sleep(0.1)  # انتظار المعالجة
        await notifier.stop()

        assert len(notifier.history) == 1
        assert notifier.history[0].category == NotificationCategory.JOB_COMPLETED

    @pytest.mark.asyncio
    async def test_job_failed_notification(self):
        """اختبار إشعار فشل المهمة"""
        notifier = Notifier()
        notifier.add_channel(ConsoleChannel(colored=False))
        await notifier.start()

        await notifier.job_failed(
            job_id="job-456",
            job_name="Failed Job",
            error="Out of memory",
        )

        await asyncio.sleep(0.1)
        await notifier.stop()

        assert len(notifier.history) == 1
        assert notifier.history[0].category == NotificationCategory.JOB_FAILED
        assert notifier.history[0].priority == NotificationPriority.HIGH

    def test_stats(self):
        """اختبار الإحصائيات"""
        notifier = Notifier()
        notifier.add_channel(ConsoleChannel())
        stats = notifier.stats()
        assert "channels" in stats
        assert "console" in stats["channels"]


class TestNotificationRule:
    """اختبارات NotificationRule"""

    def test_rule_always(self):
        """اختبار قاعدة ALWAYS"""
        rule = NotificationRule(
            name="test",
            condition=RuleCondition.ALWAYS,
            channels=["console"],
        )
        notification = Notification(
            title="Test",
            message="Test",
            category=NotificationCategory.SYSTEM,
        )
        assert rule.matches(notification) is True

    def test_rule_category_is(self):
        """اختبار قاعدة CATEGORY_IS"""
        rule = NotificationRule(
            name="test",
            condition=RuleCondition.CATEGORY_IS,
            condition_value=NotificationCategory.JOB_FAILED,
            channels=["slack"],
        )

        n1 = Notification(title="", message="", category=NotificationCategory.JOB_FAILED)
        n2 = Notification(title="", message="", category=NotificationCategory.JOB_COMPLETED)

        assert rule.matches(n1) is True
        assert rule.matches(n2) is False

    def test_rule_priority_gte(self):
        """اختبار قاعدة PRIORITY_GTE"""
        rule = NotificationRule(
            name="test",
            condition=RuleCondition.PRIORITY_GTE,
            condition_value=NotificationPriority.HIGH,
            channels=["email"],
        )

        n_low = Notification(
            title="",
            message="",
            category=NotificationCategory.SYSTEM,
            priority=NotificationPriority.LOW,
        )
        n_high = Notification(
            title="",
            message="",
            category=NotificationCategory.SYSTEM,
            priority=NotificationPriority.HIGH,
        )
        n_critical = Notification(
            title="",
            message="",
            category=NotificationCategory.SYSTEM,
            priority=NotificationPriority.CRITICAL,
        )

        assert rule.matches(n_low) is False
        assert rule.matches(n_high) is True
        assert rule.matches(n_critical) is True

    def test_rule_disabled(self):
        """اختبار قاعدة معطلة"""
        rule = NotificationRule(
            name="test",
            condition=RuleCondition.ALWAYS,
            channels=["console"],
            enabled=False,
        )
        notification = Notification(title="", message="", category=NotificationCategory.SYSTEM)
        assert rule.matches(notification) is False


class TestRuleEngine:
    """اختبارات RuleEngine"""

    def test_engine_creation(self):
        """اختبار إنشاء المحرك"""
        engine = RuleEngine()
        assert len(engine.rules) == 0

    def test_add_rule(self):
        """اختبار إضافة قاعدة"""
        engine = RuleEngine()
        rule = NotificationRule(
            name="test",
            condition=RuleCondition.ALWAYS,
            channels=["console"],
        )
        engine.add_rule(rule)
        assert len(engine.rules) == 1

    def test_remove_rule(self):
        """اختبار إزالة قاعدة"""
        engine = RuleEngine()
        rule = NotificationRule(
            name="test",
            condition=RuleCondition.ALWAYS,
            channels=["console"],
        )
        engine.add_rule(rule)
        engine.remove_rule("test")
        assert len(engine.rules) == 0

    def test_get_matching_channels(self):
        """اختبار الحصول على القنوات المطابقة"""
        engine = RuleEngine()

        engine.add_rule(
            NotificationRule(
                name="all",
                condition=RuleCondition.ALWAYS,
                channels=["console"],
            )
        )

        engine.add_rule(
            NotificationRule(
                name="failed",
                condition=RuleCondition.CATEGORY_IS,
                condition_value=NotificationCategory.JOB_FAILED,
                channels=["slack", "email"],
            )
        )

        n1 = Notification(title="", message="", category=NotificationCategory.JOB_COMPLETED)
        n2 = Notification(title="", message="", category=NotificationCategory.JOB_FAILED)

        channels1 = engine.get_matching_channels(n1)
        channels2 = engine.get_matching_channels(n2)

        assert "console" in channels1
        assert "slack" not in channels1

        assert "console" in channels2
        assert "slack" in channels2
        assert "email" in channels2

    def test_create_default_rules(self):
        """اختبار إنشاء القواعد الافتراضية"""
        engine = RuleEngine()
        engine.create_default_rules()
        assert len(engine.rules) > 0


class TestWebhookChannel:
    """اختبارات WebhookChannel"""

    def test_channel_creation(self):
        """اختبار إنشاء القناة"""
        channel = WebhookChannel(
            name="test-webhook",
            url="https://example.com/webhook",
        )
        assert channel.name == "test-webhook"
        assert channel.url == "https://example.com/webhook"


class TestSlackChannel:
    """اختبارات SlackChannel"""

    def test_channel_creation(self):
        """اختبار إنشاء القناة"""
        channel = SlackChannel(
            webhook_url="https://hooks.slack.com/services/xxx",
            channel="#alerts",
        )
        assert channel.name == "slack"
        assert channel.channel == "#alerts"

    def test_build_message(self):
        """اختبار بناء الرسالة"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification

        channel = SlackChannel(webhook_url="https://test.com")
        notification = ChannelNotification(
            title="Test Alert",
            message="This is a test",
            data={"job_id": "123"},
        )

        # channels.py uses _build_payload
        message = channel._build_payload(notification)
        assert "attachments" in message


class TestDiscordChannel:
    """اختبارات DiscordChannel"""

    def test_channel_creation(self):
        """اختبار إنشاء القناة"""
        channel = DiscordChannel(
            webhook_url="https://discord.com/api/webhooks/xxx",
        )
        assert channel.name == "discord"

    def test_build_message(self):
        """اختبار بناء الرسالة"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification
        from distributed_cluster.notifications.channels import NotificationPriority as ChPriority

        channel = DiscordChannel(webhook_url="https://test.com")
        notification = ChannelNotification(
            title="Test Alert",
            message="This is a test",
            priority=ChPriority.CRITICAL,
        )

        # channels.py uses _build_payload
        message = channel._build_payload(notification)
        assert "embeds" in message
        assert "Test Alert" in message["embeds"][0]["title"]


# ============================================================================
# Tests for New Notification Components
# ============================================================================


class TestNotificationQueue:
    """اختبارات NotificationQueue"""

    @pytest.mark.asyncio
    async def test_queue_creation(self):
        """اختبار إنشاء الطابور"""
        from distributed_cluster.notifications.queue import NotificationQueue

        queue = NotificationQueue(max_size=100)
        assert queue.size == 0
        assert queue.is_empty is True
        assert queue.is_full is False

    @pytest.mark.asyncio
    async def test_queue_put_get(self):
        """اختبار إضافة والحصول على الإشعارات"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification
        from distributed_cluster.notifications.queue import NotificationQueue

        queue = NotificationQueue(max_size=100)

        notification = ChannelNotification(
            title="Test",
            message="Test message",
        )

        await queue.put(notification)
        assert queue.size == 1

        result = await queue.get(timeout=1.0)
        assert result is not None
        assert result.title == "Test"
        assert queue.size == 0

    @pytest.mark.asyncio
    async def test_queue_priority_ordering(self):
        """اختبار ترتيب الأولوية"""
        from distributed_cluster.notifications.channels import (
            Notification as ChannelNotification,
        )
        from distributed_cluster.notifications.channels import (
            NotificationPriority as ChPriority,
        )
        from distributed_cluster.notifications.queue import NotificationQueue

        queue = NotificationQueue(max_size=100)

        low = ChannelNotification(title="Low", message="", priority=ChPriority.LOW)
        high = ChannelNotification(title="High", message="", priority=ChPriority.HIGH)
        critical = ChannelNotification(title="Critical", message="", priority=ChPriority.CRITICAL)

        # Add in wrong order
        await queue.put(low)
        await queue.put(high)
        await queue.put(critical)

        # Should get highest priority first
        result1 = await queue.get(timeout=1.0)
        result2 = await queue.get(timeout=1.0)
        result3 = await queue.get(timeout=1.0)

        assert result1.title == "Critical"
        assert result2.title == "High"
        assert result3.title == "Low"

    @pytest.mark.asyncio
    async def test_queue_batch_get(self):
        """اختبار الحصول على دفعة"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification
        from distributed_cluster.notifications.queue import NotificationQueue

        queue = NotificationQueue(max_size=100)

        for i in range(5):
            await queue.put(ChannelNotification(title=f"Test {i}", message=""))

        batch = await queue.get_batch(3, timeout=1.0)
        assert len(batch) == 3
        assert queue.size == 2

    @pytest.mark.asyncio
    async def test_queue_stats(self):
        """اختبار إحصائيات الطابور"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification
        from distributed_cluster.notifications.queue import NotificationQueue

        queue = NotificationQueue(max_size=100)

        await queue.put(ChannelNotification(title="Test", message=""))
        await queue.get(timeout=1.0)

        stats = queue.stats
        assert stats["total_enqueued"] == 1
        assert stats["total_dequeued"] == 1
        assert stats["size"] == 0


class TestNotificationHistory:
    """اختبارات NotificationHistory"""

    @pytest.mark.asyncio
    async def test_history_creation(self, tmp_path):
        """اختبار إنشاء السجل"""
        from distributed_cluster.notifications.history import NotificationHistory

        db_path = tmp_path / "test_history.db"
        history = NotificationHistory(db_path=db_path)
        await history.initialize()

        count = await history.count()
        assert count == 0

        await history.close()

    @pytest.mark.asyncio
    async def test_history_add_and_get(self, tmp_path):
        """اختبار إضافة والحصول على الإشعارات"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification
        from distributed_cluster.notifications.history import NotificationHistory

        db_path = tmp_path / "test_history.db"
        history = NotificationHistory(db_path=db_path)
        await history.initialize()

        notification = ChannelNotification(
            title="Test",
            message="Test message",
        )

        await history.add(notification)

        result = await history.get(notification.notification_id)
        assert result is not None
        assert result.title == "Test"

        await history.close()

    @pytest.mark.asyncio
    async def test_history_search(self, tmp_path):
        """اختبار البحث في السجل"""
        from distributed_cluster.notifications.channels import (
            Notification as ChannelNotification,
        )
        from distributed_cluster.notifications.channels import (
            NotificationPriority as ChPriority,
        )
        from distributed_cluster.notifications.history import HistoryQuery, NotificationHistory

        db_path = tmp_path / "test_history.db"
        history = NotificationHistory(db_path=db_path, enable_fts=False)
        await history.initialize()

        # Add notifications
        await history.add(ChannelNotification(title="Normal", message="", priority=ChPriority.NORMAL))
        await history.add(ChannelNotification(title="High", message="", priority=ChPriority.HIGH))
        await history.add(ChannelNotification(title="Critical", message="", priority=ChPriority.CRITICAL))

        # Search by priority
        query = HistoryQuery(priority=ChPriority.HIGH)
        results = await history.search(query)
        assert len(results) == 1
        assert results[0].title == "High"

        await history.close()

    @pytest.mark.asyncio
    async def test_history_stats(self, tmp_path):
        """اختبار إحصائيات السجل"""
        from distributed_cluster.notifications.channels import (
            Notification as ChannelNotification,
        )
        from distributed_cluster.notifications.channels import (
            NotificationPriority as ChPriority,
        )
        from distributed_cluster.notifications.history import NotificationHistory

        db_path = tmp_path / "test_history.db"
        history = NotificationHistory(db_path=db_path)
        await history.initialize()

        await history.add(ChannelNotification(title="Test 1", message="", priority=ChPriority.LOW))
        await history.add(ChannelNotification(title="Test 2", message="", priority=ChPriority.HIGH))

        stats = await history.get_stats()
        assert stats.total_count == 2
        assert "low" in stats.by_priority
        assert "high" in stats.by_priority

        await history.close()


class TestNotificationScheduler:
    """اختبارات NotificationScheduler"""

    @pytest.mark.asyncio
    async def test_scheduler_creation(self):
        """اختبار إنشاء المجدول"""
        from distributed_cluster.notifications.scheduler import NotificationScheduler

        scheduler = NotificationScheduler()
        assert scheduler.stats["total_jobs"] == 0

    @pytest.mark.asyncio
    async def test_schedule_once(self):
        """اختبار جدولة مرة واحدة"""
        from datetime import datetime, timedelta, timezone

        from distributed_cluster.notifications.channels import Notification as ChannelNotification
        from distributed_cluster.notifications.scheduler import NotificationScheduler

        scheduler = NotificationScheduler()

        notification = ChannelNotification(title="Scheduled", message="Test")
        run_at = datetime.now(timezone.utc) + timedelta(hours=1)

        job = await scheduler.schedule_once(notification, run_at)

        assert job.job_id is not None
        assert job.next_run is not None
        assert scheduler.stats["total_jobs"] == 1

    @pytest.mark.asyncio
    async def test_schedule_interval(self):
        """اختبار جدولة متكررة"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification
        from distributed_cluster.notifications.scheduler import JobStatus, NotificationScheduler

        scheduler = NotificationScheduler()

        notification = ChannelNotification(title="Recurring", message="Test")

        job = await scheduler.schedule_interval(
            notification,
            interval_seconds=3600,
            max_runs=5,
        )

        assert job.schedule.interval_seconds == 3600
        assert job.schedule.max_runs == 5
        assert job.status == JobStatus.SCHEDULED

    @pytest.mark.asyncio
    async def test_cancel_job(self):
        """اختبار إلغاء المهمة"""
        from datetime import datetime, timedelta

        from distributed_cluster.notifications.channels import Notification as ChannelNotification
        from distributed_cluster.notifications.scheduler import JobStatus, NotificationScheduler

        scheduler = NotificationScheduler()

        notification = ChannelNotification(title="Test", message="")
        run_at = datetime.now(timezone.utc) + timedelta(hours=1)

        job = await scheduler.schedule_once(notification, run_at)
        result = await scheduler.cancel(job.job_id)

        assert result is True
        cancelled_job = await scheduler.get_job(job.job_id)
        assert cancelled_job.status == JobStatus.CANCELLED


class TestTemplateEngine:
    """اختبارات TemplateEngine"""

    def test_engine_creation(self):
        """اختبار إنشاء المحرك"""
        from distributed_cluster.notifications.templates import TemplateEngine

        engine = TemplateEngine()
        templates = engine.list_templates()
        assert len(templates) > 0
        assert "plain_simple" in templates

    def test_render_simple_template(self):
        """اختبار تصيير قالب بسيط"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification
        from distributed_cluster.notifications.templates import TemplateEngine

        engine = TemplateEngine()
        notification = ChannelNotification(
            title="Test Title",
            message="Test message",
        )

        result = engine.render("plain_simple", notification)
        assert "Test Title" in result
        assert "Test message" in result

    def test_render_with_variables(self):
        """اختبار تصيير مع متغيرات"""
        from distributed_cluster.notifications.templates import (
            StringTemplate,
            TemplateEngine,
        )

        engine = TemplateEngine()
        engine.register(StringTemplate(
            name="custom",
            template="Hello {{name}}, your score is {{score}}!",
        ))

        result = engine.render("custom", name="User", score=100)
        assert result == "Hello User, your score is 100!"

    def test_render_html_template(self):
        """اختبار تصيير قالب HTML"""
        from distributed_cluster.notifications.channels import Notification as ChannelNotification
        from distributed_cluster.notifications.templates import TemplateEngine

        engine = TemplateEngine()
        notification = ChannelNotification(
            title="HTML Test",
            message="Test message",
        )

        result = engine.render("email_modern", notification)
        assert "<!DOCTYPE html>" in result
        assert "HTML Test" in result

    def test_template_filters(self):
        """اختبار فلاتر القوالب"""
        from distributed_cluster.notifications.templates import StringTemplate, TemplateContext

        template = StringTemplate(
            name="test",
            template="{{name|upper}} - {{value|lower}}",
        )

        context = TemplateContext(variables={"name": "hello", "value": "WORLD"})
        result = template.render(context)
        assert result == "HELLO - world"


class TestStringTemplate:
    """اختبارات StringTemplate"""

    def test_variable_substitution(self):
        """اختبار استبدال المتغيرات"""
        from distributed_cluster.notifications.templates import StringTemplate, TemplateContext

        template = StringTemplate(
            name="test",
            template="Hello {{name}}!",
        )
        context = TemplateContext(variables={"name": "World"})
        result = template.render(context)
        assert result == "Hello World!"

    def test_default_value(self):
        """اختبار القيمة الافتراضية"""
        from distributed_cluster.notifications.templates import StringTemplate, TemplateContext

        template = StringTemplate(
            name="test",
            template="Hello {{name|Guest}}!",
        )
        context = TemplateContext(variables={})
        result = template.render(context)
        assert result == "Hello Guest!"

    def test_conditional_block(self):
        """اختبار الكتلة الشرطية"""
        from distributed_cluster.notifications.templates import StringTemplate, TemplateContext

        template = StringTemplate(
            name="test",
            template="{% if show_message %}Hello!{% endif %}",
        )

        ctx_true = TemplateContext(variables={"show_message": True})
        ctx_false = TemplateContext(variables={"show_message": False})

        assert template.render(ctx_true) == "Hello!"
        assert template.render(ctx_false) == ""

    def test_loop_block(self):
        """اختبار كتلة الحلقة"""
        from distributed_cluster.notifications.templates import StringTemplate, TemplateContext

        template = StringTemplate(
            name="test",
            template="{% for item in items %}{{item}},{% endfor %}",
        )

        context = TemplateContext(variables={"items": ["a", "b", "c"]})
        result = template.render(context)
        assert result == "a,b,c,"
