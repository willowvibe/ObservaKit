"""
ObservaKit — Microsoft Teams Alert Dispatcher
Sends alerts to MS Teams via Incoming Webhook connectors.

Configuration (environment variables):
    TEAMS_WEBHOOK_URL — the full URL from the Teams connector configuration.

Example kit.yml:
    alerts:
      default_channel: teams
      routing:
        - match: {severity: fail}
          channel: teams
"""

import logging
import os

import httpx

from alerts.base import AlertDispatcher

logger = logging.getLogger(__name__)


class TeamsDispatcher(AlertDispatcher):
    """Sends alerts to Microsoft Teams using Incoming Webhooks (Adaptive Cards)."""

    def __init__(self, **kwargs):
        self._webhook_url = kwargs.get("teams_webhook_url") or os.getenv("TEAMS_WEBHOOK_URL", "")

    def send(
        self,
        message: str,
        subject: str = None,
        alert_type: str = None,
        table_name: str = None,
        **kwargs,
    ) -> bool:
        if not self._webhook_url:
            logger.warning("TEAMS_WEBHOOK_URL is not configured — skipping Teams alert")
            return False

        title = subject or f"ObservaKit Alert: {alert_type or 'data quality issue'}"

        # Build an Adaptive Card payload (Teams Incoming Webhook format)
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Medium",
                                "weight": "Bolder",
                                "text": title,
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": message,
                                "wrap": True,
                            },
                        ],
                        "actions": (
                            [
                                {
                                    "type": "Action.OpenUrl",
                                    "title": "View in ObservaKit",
                                    "url": os.getenv("OBSERVAKIT_DASHBOARD_URL", "http://localhost:8000/ui"),
                                }
                            ]
                            if os.getenv("OBSERVAKIT_DASHBOARD_URL")
                            else []
                        ),
                    },
                }
            ],
        }

        try:
            resp = httpx.post(self._webhook_url, json=payload, timeout=10)
            # Teams returns "1" with status 200 on success
            if resp.status_code == 200:
                logger.info("Teams alert sent (alert_type=%s, table=%s)", alert_type, table_name)
                return True
            else:
                logger.error("Teams webhook returned %d: %s", resp.status_code, resp.text)
                return False
        except Exception as exc:
            logger.error("Failed to send Teams alert: %s", exc)
            return False
