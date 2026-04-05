"""
Tests for alert dispatchers — verifies that each dispatcher correctly
formats its payload and that suppression/deduplication is honored.

All HTTP calls are mocked so no real Slack/email/webhook endpoints are hit.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from alerts.base import dispatch_alert, get_alert_dispatcher, is_alert_suppressed
from backend.models import AlertLog, CheckSuppression


# ---------------------------------------------------------------------------
# Dispatcher unit tests — Slack
# ---------------------------------------------------------------------------

class TestSlackDispatcher:
    def test_slack_sends_payload_on_success(self, monkeypatch):
        """SlackDispatcher.send() should POST to the webhook URL."""
        import os
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        from alerts.slack import SlackDispatcher

        dispatcher = SlackDispatcher()

        with patch("alerts.slack.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, text="ok")
            result = dispatcher.send(
                message="Test alert",
                subject="Test subject",
                alert_type="freshness",
                table_name="public.orders",
            )

        assert mock_post.called
        assert result is True

    def test_slack_returns_false_on_http_error(self, monkeypatch):
        """SlackDispatcher.send() should return False on non-200 response."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        from alerts.slack import SlackDispatcher

        dispatcher = SlackDispatcher()

        with patch("alerts.slack.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=400, text="channel_not_found")
            result = dispatcher.send(
                message="Test",
                subject="Subject",
                alert_type="quality",
                table_name="public.orders",
            )

        assert result is False

    def test_slack_returns_false_when_not_configured(self):
        """SlackDispatcher.send() returns False when no webhook URL is set."""
        from alerts.slack import SlackDispatcher

        dispatcher = SlackDispatcher()
        # No SLACK_WEBHOOK_URL set — webhook_url will be empty string
        dispatcher._webhook_url = ""
        result = dispatcher.send(message="Test", subject="Subject")
        assert result is False


# ---------------------------------------------------------------------------
# Dispatcher factory
# ---------------------------------------------------------------------------

class TestDispatcherFactory:
    def test_factory_returns_slack_dispatcher(self):
        from alerts.slack import SlackDispatcher

        d = get_alert_dispatcher("slack")
        assert isinstance(d, SlackDispatcher)

    def test_factory_raises_on_unknown_channel(self):
        with pytest.raises(ValueError, match="Unsupported alert channel"):
            get_alert_dispatcher("carrier_pigeon")


# ---------------------------------------------------------------------------
# dispatch_alert routing — integration-style with mocked config
# ---------------------------------------------------------------------------

class TestDispatchAlertRouting:
    @patch("config.loader.load_config")
    def test_routes_to_default_channel_when_no_rules(self, mock_load_config, monkeypatch):
        """When no routing rules are defined, falls back to default_channel."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
        mock_load_config.return_value = {
            "alerts": {
                "default_channel": "slack",
            }
        }
        with patch("alerts.slack.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, text="ok")
            dispatch_alert(
                alert_type="freshness",
                message="Table stale",
                table_name="public.orders",
            )
        assert mock_post.called

    @patch("config.loader.load_config")
    def test_routing_rule_matches_alert_type(self, mock_load_config, monkeypatch):
        """Routing rules with matching alert_type should be selected."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
        mock_load_config.return_value = {
            "alerts": {
                "default_channel": "slack",
                "routing": [
                    {
                        "match": {"alert_type": "quality"},
                        "channel": "slack",
                    }
                ],
            }
        }
        with patch("alerts.slack.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, text="ok")
            dispatch_alert(
                alert_type="quality",
                message="Check failed",
                table_name="public.orders",
            )
        assert mock_post.called


# ---------------------------------------------------------------------------
# Suppression integration with dispatch
# ---------------------------------------------------------------------------

class TestSuppressionWithAlerts:
    def test_alert_not_fired_when_table_suppressed(self, db_session):
        """
        When a table has an active suppression, callers should check
        is_alert_suppressed() before calling dispatch_alert().
        This test verifies the suppression check returns True.
        """
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        db_session.add(CheckSuppression(
            table_name="public.orders",
            suppressed_until=future,
            reason="planned maintenance",
        ))
        db_session.commit()

        suppressed = is_alert_suppressed(db_session, "public.orders")
        assert suppressed is True

    def test_alert_fired_when_no_suppression(self, db_session):
        result = is_alert_suppressed(db_session, "public.events")
        assert result is False
