"""
ObservaKit — Slack Alert Dispatcher
Sends alerts to Slack via incoming webhooks.
"""

import logging
import os

import httpx

from alerts.base import AlertDispatcher

logger = logging.getLogger(__name__)


class SlackDispatcher(AlertDispatcher):
    """Sends alerts to Slack using incoming webhooks."""

    def __init__(self, **kwargs):
        self._webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        # Use provided channel from routing rule, else standard env var
        self._channel = kwargs.get("slack_channel") or os.getenv("SLACK_CHANNEL", "#data-alerts")

    def send(self, message: str, subject: str = None, blocks: list = None, **kwargs) -> bool:
        """Send a Slack message via webhook."""
        if not self._webhook_url or self._webhook_url.startswith("https://hooks.slack.com/services/YOUR"):
            logger.warning("Slack webhook URL not configured — skipping alert")
            return False

        payload = {
            "channel": self._channel,
            "username": "ObservaKit",
            "icon_emoji": ":mag:",
        }

        if blocks:
            payload["blocks"] = blocks
        else:
            payload["text"] = f"*{subject}*\n{message}" if subject else message

        try:
            resp = httpx.post(self._webhook_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"Slack alert sent to {self._channel}")
                return True
            else:
                logger.error(f"Slack webhook returned {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False
