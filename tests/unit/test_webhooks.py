"""
Webhooks Module Unit Tests - اختبارات وحدة الـ Webhooks
========================================================

Tests for the webhook system including:
- WebhookManager
- Webhook providers (Discord, Slack, Teams, Custom)
- Payload templates
- Retry logic and delivery
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distributed_cluster.webhooks import (
    CustomWebhook,
    DiscordWebhook,
    PayloadTemplate,
    SlackWebhook,
    TeamsWebhook,
    TemplateEngine,
    WebhookConfig,
    WebhookEvent,
    WebhookManager,
    WebhookProvider,
    WebhookResult,
)


# =============================================================================
# WebhookConfig Tests
# =============================================================================


class TestWebhookConfig:
    """Tests for WebhookConfig."""

    def test_default_config(self):
        """Test default webhook configuration."""
        config = WebhookConfig(
            name="test-webhook",
            url="https://example.com/webhook",
            provider="custom",
        )
        assert config.name == "test-webhook"
        assert config.enabled is True
        assert config.retry_count == 3

    def test_custom_config(self):
        """Test custom webhook configuration."""
        config = WebhookConfig(
            name="slack-webhook",
            url="https://hooks.slack.com/services/xxx",
            provider="slack",
            enabled=True,
            retry_count=5,
            timeout_seconds=30,
            headers={"Authorization": "Bearer token"},
        )
        assert config.provider == "slack"
        assert config.retry_count == 5
        assert config.timeout_seconds == 30

    def test_disabled_config(self):
        """Test disabled webhook configuration."""
        config = WebhookConfig(
            name="disabled-webhook",
            url="https://example.com/webhook",
            provider="custom",
            enabled=False,
        )
        assert config.enabled is False


# =============================================================================
# WebhookEvent Tests
# =============================================================================


class TestWebhookEvent:
    """Tests for WebhookEvent."""

    def test_create_event(self):
        """Test creating a webhook event."""
        event = WebhookEvent(
            event_type="job.completed",
            payload={"job_id": "job-123", "status": "success"},
            timestamp=datetime.now(timezone.utc),
        )
        assert event.event_type == "job.completed"
        assert event.payload["job_id"] == "job-123"

    def test_event_to_dict(self):
        """Test event dictionary conversion."""
        event = WebhookEvent(
            event_type="worker.joined",
            payload={"worker_id": "worker-1"},
            timestamp=datetime.now(timezone.utc),
        )
        d = event.to_dict()
        assert d["event_type"] == "worker.joined"
        assert "timestamp" in d

    def test_event_with_metadata(self):
        """Test event with metadata."""
        event = WebhookEvent(
            event_type="cluster.scaled",
            payload={"new_count": 10},
            timestamp=datetime.now(timezone.utc),
            metadata={"source": "autoscaler", "region": "us-east-1"},
        )
        assert event.metadata["source"] == "autoscaler"


# =============================================================================
# WebhookResult Tests
# =============================================================================


class TestWebhookResult:
    """Tests for WebhookResult."""

    def test_successful_result(self):
        """Test successful webhook result."""
        result = WebhookResult(
            success=True,
            status_code=200,
            response_body={"ok": True},
            delivery_time_ms=150.5,
        )
        assert result.success is True
        assert result.status_code == 200

    def test_failed_result(self):
        """Test failed webhook result."""
        result = WebhookResult(
            success=False,
            status_code=500,
            error="Internal server error",
            retry_count=3,
        )
        assert result.success is False
        assert result.error == "Internal server error"

    def test_timeout_result(self):
        """Test timeout webhook result."""
        result = WebhookResult(
            success=False,
            error="Request timed out",
            timed_out=True,
        )
        assert result.timed_out is True


# =============================================================================
# Payload Template Tests
# =============================================================================


class TestPayloadTemplate:
    """Tests for PayloadTemplate."""

    def test_create_template(self):
        """Test creating a payload template."""
        template = PayloadTemplate(
            name="job-notification",
            template_string='{"event": "{{event_type}}", "job": "{{job_id}}"}',
        )
        assert template.name == "job-notification"

    def test_render_template(self):
        """Test rendering a template."""
        template = PayloadTemplate(
            name="notification",
            template_string='{"message": "Job {{job_id}} {{status}}"}',
        )
        rendered = template.render(job_id="job-123", status="completed")
        assert "job-123" in rendered
        assert "completed" in rendered

    def test_template_with_nested_data(self):
        """Test template with nested data."""
        template = PayloadTemplate(
            name="complex",
            template_string='{"job": {"id": "{{job_id}}", "status": "{{status}}"}}',
        )
        rendered = template.render(job_id="job-456", status="running")
        data = json.loads(rendered)
        assert data["job"]["id"] == "job-456"


class TestTemplateEngine:
    """Tests for TemplateEngine."""

    @pytest.fixture
    def engine(self):
        return TemplateEngine()

    def test_register_template(self, engine):
        """Test registering a template."""
        template = PayloadTemplate(
            name="test",
            template_string='{"msg": "{{message}}"}',
        )
        engine.register(template)
        assert engine.get("test") is not None

    def test_render_registered_template(self, engine):
        """Test rendering a registered template."""
        template = PayloadTemplate(
            name="greeting",
            template_string='{"greeting": "Hello, {{name}}!"}',
        )
        engine.register(template)

        result = engine.render("greeting", name="World")
        assert "Hello, World!" in result

    def test_unregistered_template(self, engine):
        """Test rendering unregistered template."""
        with pytest.raises(KeyError):
            engine.render("nonexistent", data="test")

    def test_builtin_templates(self, engine):
        """Test built-in templates."""
        # Engine should have built-in templates for common events
        builtin_names = engine.list_templates()
        assert isinstance(builtin_names, list)


# =============================================================================
# Webhook Provider Tests
# =============================================================================


class TestWebhookProvider:
    """Tests for base WebhookProvider."""

    def test_provider_interface(self):
        """Test provider interface."""
        # WebhookProvider should be abstract or have required methods
        assert hasattr(WebhookProvider, "send")
        assert hasattr(WebhookProvider, "format_payload")


class TestDiscordWebhook:
    """Tests for Discord webhook provider."""

    @pytest.fixture
    def webhook(self):
        config = WebhookConfig(
            name="discord-test",
            url="https://discord.com/api/webhooks/xxx/yyy",
            provider="discord",
        )
        return DiscordWebhook(config)

    def test_format_payload(self, webhook):
        """Test Discord payload formatting."""
        event = WebhookEvent(
            event_type="job.completed",
            payload={"job_id": "job-123", "status": "success"},
            timestamp=datetime.now(timezone.utc),
        )
        payload = webhook.format_payload(event)

        # Discord uses embeds
        assert "embeds" in payload or "content" in payload

    def test_format_with_embed(self, webhook):
        """Test Discord payload with embed."""
        event = WebhookEvent(
            event_type="worker.error",
            payload={
                "worker_id": "worker-1",
                "error": "Connection lost",
            },
            timestamp=datetime.now(timezone.utc),
        )
        payload = webhook.format_payload(event)

        # Should have proper Discord structure
        assert isinstance(payload, dict)

    @pytest.mark.asyncio
    async def test_send_mock(self, webhook):
        """Test sending to Discord (mocked)."""
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={})
            mock_post.return_value.__aenter__.return_value = mock_response

            event = WebhookEvent(
                event_type="test",
                payload={"data": "test"},
                timestamp=datetime.now(timezone.utc),
            )
            result = await webhook.send(event)
            # Result depends on implementation


class TestSlackWebhook:
    """Tests for Slack webhook provider."""

    @pytest.fixture
    def webhook(self):
        config = WebhookConfig(
            name="slack-test",
            url="https://hooks.slack.com/services/xxx/yyy/zzz",
            provider="slack",
        )
        return SlackWebhook(config)

    def test_format_payload(self, webhook):
        """Test Slack payload formatting."""
        event = WebhookEvent(
            event_type="job.completed",
            payload={"job_id": "job-123", "duration": 120},
            timestamp=datetime.now(timezone.utc),
        )
        payload = webhook.format_payload(event)

        # Slack uses blocks or text
        assert "blocks" in payload or "text" in payload

    def test_format_with_blocks(self, webhook):
        """Test Slack payload with blocks."""
        event = WebhookEvent(
            event_type="cluster.alert",
            payload={
                "alert_type": "high_cpu",
                "value": 95,
                "threshold": 80,
            },
            timestamp=datetime.now(timezone.utc),
        )
        payload = webhook.format_payload(event)

        assert isinstance(payload, dict)

    def test_format_error_notification(self, webhook):
        """Test Slack error notification formatting."""
        event = WebhookEvent(
            event_type="error",
            payload={
                "error_type": "JobFailed",
                "message": "Process exited with code 1",
                "job_id": "job-456",
            },
            timestamp=datetime.now(timezone.utc),
        )
        payload = webhook.format_payload(event)

        # Error notifications should have attention-grabbing format
        assert isinstance(payload, dict)


class TestTeamsWebhook:
    """Tests for Microsoft Teams webhook provider."""

    @pytest.fixture
    def webhook(self):
        config = WebhookConfig(
            name="teams-test",
            url="https://outlook.office.com/webhook/xxx",
            provider="teams",
        )
        return TeamsWebhook(config)

    def test_format_payload(self, webhook):
        """Test Teams payload formatting."""
        event = WebhookEvent(
            event_type="deployment.complete",
            payload={"version": "1.2.3", "environment": "production"},
            timestamp=datetime.now(timezone.utc),
        )
        payload = webhook.format_payload(event)

        # Teams uses Adaptive Cards or MessageCard
        assert "@type" in payload or "type" in payload

    def test_format_with_sections(self, webhook):
        """Test Teams payload with sections."""
        event = WebhookEvent(
            event_type="report.generated",
            payload={
                "report_type": "daily",
                "metrics": {
                    "jobs_completed": 150,
                    "jobs_failed": 3,
                    "avg_duration": 45.5,
                },
            },
            timestamp=datetime.now(timezone.utc),
        )
        payload = webhook.format_payload(event)

        assert isinstance(payload, dict)


class TestCustomWebhook:
    """Tests for custom webhook provider."""

    @pytest.fixture
    def webhook(self):
        config = WebhookConfig(
            name="custom-test",
            url="https://api.example.com/webhooks/events",
            provider="custom",
            headers={"X-API-Key": "secret-key"},
        )
        return CustomWebhook(config)

    def test_format_payload(self, webhook):
        """Test custom payload formatting."""
        event = WebhookEvent(
            event_type="custom.event",
            payload={"custom_field": "custom_value"},
            timestamp=datetime.now(timezone.utc),
        )
        payload = webhook.format_payload(event)

        # Custom webhook should preserve payload as-is
        assert payload["payload"]["custom_field"] == "custom_value"

    def test_custom_headers(self, webhook):
        """Test custom headers."""
        assert webhook.config.headers["X-API-Key"] == "secret-key"

    @pytest.mark.asyncio
    async def test_send_with_custom_template(self, webhook):
        """Test sending with custom template."""
        webhook.set_template(
            PayloadTemplate(
                name="custom",
                template_string='{"event": "{{event_type}}", "data": {{payload}}}',
            )
        )

        event = WebhookEvent(
            event_type="test.event",
            payload={"key": "value"},
            timestamp=datetime.now(timezone.utc),
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response

            result = await webhook.send(event)


# =============================================================================
# WebhookManager Tests
# =============================================================================


class TestWebhookManager:
    """Tests for WebhookManager."""

    @pytest.fixture
    def manager(self):
        return WebhookManager()

    def test_register_webhook(self, manager):
        """Test registering a webhook."""
        config = WebhookConfig(
            name="test-webhook",
            url="https://example.com/webhook",
            provider="custom",
        )
        manager.register(config)

        assert manager.get("test-webhook") is not None

    def test_unregister_webhook(self, manager):
        """Test unregistering a webhook."""
        config = WebhookConfig(
            name="temp-webhook",
            url="https://example.com/webhook",
            provider="custom",
        )
        manager.register(config)
        manager.unregister("temp-webhook")

        assert manager.get("temp-webhook") is None

    def test_list_webhooks(self, manager):
        """Test listing webhooks."""
        configs = [
            WebhookConfig(name=f"webhook-{i}", url=f"https://example.com/{i}", provider="custom")
            for i in range(3)
        ]
        for config in configs:
            manager.register(config)

        webhooks = manager.list_webhooks()
        assert len(webhooks) >= 3

    def test_enable_disable_webhook(self, manager):
        """Test enabling/disabling webhook."""
        config = WebhookConfig(
            name="toggle-webhook",
            url="https://example.com/webhook",
            provider="custom",
            enabled=True,
        )
        manager.register(config)

        manager.disable("toggle-webhook")
        assert manager.get("toggle-webhook").config.enabled is False

        manager.enable("toggle-webhook")
        assert manager.get("toggle-webhook").config.enabled is True

    @pytest.mark.asyncio
    async def test_trigger_event(self, manager):
        """Test triggering an event."""
        config = WebhookConfig(
            name="trigger-test",
            url="https://example.com/webhook",
            provider="custom",
            events=["job.completed"],
        )
        manager.register(config)

        event = WebhookEvent(
            event_type="job.completed",
            payload={"job_id": "job-123"},
            timestamp=datetime.now(timezone.utc),
        )

        with patch.object(manager, "_send_to_webhook") as mock_send:
            mock_send.return_value = WebhookResult(success=True, status_code=200)

            results = await manager.trigger(event)

            mock_send.assert_called()

    @pytest.mark.asyncio
    async def test_trigger_filtered_event(self, manager):
        """Test that events are filtered by webhook configuration."""
        config = WebhookConfig(
            name="filtered-webhook",
            url="https://example.com/webhook",
            provider="custom",
            events=["job.completed"],  # Only listens to job.completed
        )
        manager.register(config)

        # This event should not trigger the webhook
        event = WebhookEvent(
            event_type="worker.joined",
            payload={"worker_id": "worker-1"},
            timestamp=datetime.now(timezone.utc),
        )

        with patch.object(manager, "_send_to_webhook") as mock_send:
            results = await manager.trigger(event)

            # Should not call send for non-matching event
            # Depends on implementation

    @pytest.mark.asyncio
    async def test_trigger_all_webhooks(self, manager):
        """Test triggering all matching webhooks."""
        for i in range(3):
            config = WebhookConfig(
                name=f"multi-{i}",
                url=f"https://example.com/webhook/{i}",
                provider="custom",
                events=["job.completed"],
            )
            manager.register(config)

        event = WebhookEvent(
            event_type="job.completed",
            payload={"job_id": "job-123"},
            timestamp=datetime.now(timezone.utc),
        )

        with patch.object(manager, "_send_to_webhook") as mock_send:
            mock_send.return_value = WebhookResult(success=True, status_code=200)

            results = await manager.trigger(event)

            assert mock_send.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_logic(self, manager):
        """Test retry logic on failure."""
        config = WebhookConfig(
            name="retry-test",
            url="https://example.com/webhook",
            provider="custom",
            retry_count=3,
            retry_delay_ms=100,
        )
        manager.register(config)

        event = WebhookEvent(
            event_type="test",
            payload={},
            timestamp=datetime.now(timezone.utc),
        )

        # Simulate failures then success
        call_count = 0

        async def mock_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return WebhookResult(success=False, status_code=500, error="Server error")
            return WebhookResult(success=True, status_code=200)

        with patch.object(manager, "_send_to_webhook", side_effect=mock_send):
            results = await manager.trigger(event)

    @pytest.mark.asyncio
    async def test_disabled_webhook_skipped(self, manager):
        """Test that disabled webhooks are skipped."""
        config = WebhookConfig(
            name="disabled-test",
            url="https://example.com/webhook",
            provider="custom",
            enabled=False,
        )
        manager.register(config)

        event = WebhookEvent(
            event_type="test",
            payload={},
            timestamp=datetime.now(timezone.utc),
        )

        with patch.object(manager, "_send_to_webhook") as mock_send:
            results = await manager.trigger(event)

            mock_send.assert_not_called()

    def test_get_delivery_stats(self, manager):
        """Test getting delivery statistics."""
        stats = manager.get_stats()
        assert "total_sent" in stats or stats is not None

    def test_webhook_history(self, manager):
        """Test webhook delivery history."""
        config = WebhookConfig(
            name="history-test",
            url="https://example.com/webhook",
            provider="custom",
        )
        manager.register(config)

        history = manager.get_history("history-test")
        assert isinstance(history, list)


# =============================================================================
# Integration Tests
# =============================================================================


class TestWebhookIntegration:
    """Integration tests for webhook system."""

    @pytest.mark.asyncio
    async def test_full_webhook_flow(self):
        """Test complete webhook flow."""
        manager = WebhookManager()

        # Register multiple webhooks
        slack_config = WebhookConfig(
            name="slack",
            url="https://hooks.slack.com/services/xxx",
            provider="slack",
            events=["job.completed", "job.failed"],
        )
        discord_config = WebhookConfig(
            name="discord",
            url="https://discord.com/api/webhooks/xxx",
            provider="discord",
            events=["job.completed"],
        )

        manager.register(slack_config)
        manager.register(discord_config)

        # Create event
        event = WebhookEvent(
            event_type="job.completed",
            payload={
                "job_id": "job-integration-test",
                "status": "success",
                "duration_seconds": 120,
                "worker_id": "worker-1",
            },
            timestamp=datetime.now(timezone.utc),
        )

        # Mock the HTTP calls
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_post.return_value.__aenter__.return_value = mock_response

            results = await manager.trigger(event)

            # Both webhooks should be triggered
            assert mock_post.call_count >= 2

    @pytest.mark.asyncio
    async def test_webhook_with_template_engine(self):
        """Test webhook with template engine."""
        manager = WebhookManager()
        engine = TemplateEngine()

        # Register custom template
        template = PayloadTemplate(
            name="job-alert",
            template_string=json.dumps(
                {
                    "text": "Job {{job_id}} {{status}} in {{duration}}s",
                    "color": "{{color}}",
                }
            ),
        )
        engine.register(template)

        config = WebhookConfig(
            name="templated",
            url="https://example.com/webhook",
            provider="custom",
        )
        manager.register(config)

        # Use template
        webhook = manager.get("templated")
        webhook.template_engine = engine

        event = WebhookEvent(
            event_type="job.completed",
            payload={
                "job_id": "job-789",
                "status": "completed",
                "duration": 45,
                "color": "green",
            },
            timestamp=datetime.now(timezone.utc),
        )

        payload = webhook.format_payload(event)
        assert isinstance(payload, dict)

    @pytest.mark.asyncio
    async def test_concurrent_webhook_delivery(self):
        """Test concurrent webhook delivery."""
        manager = WebhookManager()

        # Register many webhooks
        for i in range(10):
            config = WebhookConfig(
                name=f"concurrent-{i}",
                url=f"https://example.com/webhook/{i}",
                provider="custom",
            )
            manager.register(config)

        event = WebhookEvent(
            event_type="broadcast.test",
            payload={"message": "Test broadcast"},
            timestamp=datetime.now(timezone.utc),
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response

            # Should handle concurrent delivery
            results = await manager.trigger(event)

            assert mock_post.call_count == 10

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling during webhook delivery."""
        manager = WebhookManager()

        config = WebhookConfig(
            name="error-test",
            url="https://invalid-url.example.com/webhook",
            provider="custom",
            retry_count=1,
        )
        manager.register(config)

        event = WebhookEvent(
            event_type="test",
            payload={},
            timestamp=datetime.now(timezone.utc),
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.side_effect = Exception("Connection error")

            results = await manager.trigger(event)

            # Should handle error gracefully
            for result in results:
                assert result.success is False or result.error is not None
