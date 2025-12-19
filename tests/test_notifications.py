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
            title="", message="",
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
            title="", message="",
            category=NotificationCategory.SYSTEM,
            priority=NotificationPriority.LOW,
        )
        n_high = Notification(
            title="", message="",
            category=NotificationCategory.SYSTEM,
            priority=NotificationPriority.HIGH,
        )
        n_critical = Notification(
            title="", message="",
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

        engine.add_rule(NotificationRule(
            name="all",
            condition=RuleCondition.ALWAYS,
            channels=["console"],
        ))

        engine.add_rule(NotificationRule(
            name="failed",
            condition=RuleCondition.CATEGORY_IS,
            condition_value=NotificationCategory.JOB_FAILED,
            channels=["slack", "email"],
        ))

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
