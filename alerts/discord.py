"""
ObservaKit — Discord Alert Dispatcher
Sends alerts to Discord via incoming webhooks.

Discord is extremely popular with developer-heavy startups and smaller data teams.
Many seed-stage companies run all ops alerting through Discord before graduating
to PagerDuty or Opsgenie.

Setup:
  1. In your Discord server: Server Settings → Integrations → Webhooks → New Webhook
  2. Choose channel, copy URL.
  3. Set DISCORD_WEBHOOK_URL in your .env file.

Optional: set DISCORD_MENTION to "@here" or a role ID like "<@&ROLE_ID>" to ping
on-call when alerts fire.
"""

import logging
import os

import httpx

from alerts.base import AlertDispatcher

logger = logging.getLogger(__name__)

# Discord message colour codes
COLOUR_OK = 0x57F287  # green
COLOUR_WARN = 0xFEE75C  # yellow
COLOUR_FAIL = 0xED4245  # red
COLOUR_INFO = 0x5865F2  # blurple (default)

# Alert type → colour mapping
_ALERT_COLOURS = {
    "freshness": COLOUR_WARN,
    "volume": COLOUR_FAIL,
    "quality": COLOUR_FAIL,
    "schema": COLOUR_WARN,
    "distribution": COLOUR_WARN,
    "contract": COLOUR_FAIL,
    "finops": COLOUR_WARN,
}


class DiscordDispatcher(AlertDispatcher):
    """Sends alerts to Discord using incoming webhooks with rich embeds."""

    def __init__(self, **kwargs):
        self._webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        self._mention = os.getenv("DISCORD_MENTION", "")  # e.g. "@here" or "<@&ROLE_ID>"

    def send(self, message: str, subject: str = None, alert_type: str = None, **kwargs) -> bool:
        if not self._webhook_url:
            logger.warning("DISCORD_WEBHOOK_URL not configured — skipping Discord alert")
            return False

        colour = _ALERT_COLOURS.get(alert_type or "", COLOUR_INFO)
        title = subject or "ObservaKit Alert"
        mention = f"{self._mention} " if self._mention else ""

        # Discord embeds give a much better UX than plain text
        payload = {
            "content": mention or None,
            "username": "ObservaKit",
            "avatar_url": "https://raw.githubusercontent.com/willowvibe/ObservaKit/main/willowvibe-logo.png",
            "embeds": [
                {
                    "title": title,
                    "description": message,
                    "color": colour,
                    "footer": {
                        "text": "ObservaKit · WillowVibe DataSynapse",
                    },
                    "timestamp": _utc_now_iso(),
                }
            ],
        }
        # Discord ignores null content
        if payload["content"] is None:
            del payload["content"]

        try:
            resp = httpx.post(self._webhook_url, json=payload, timeout=10)
            if resp.status_code in (200, 204):
                logger.info("Discord alert sent successfully")
                return True
            else:
                logger.error(f"Discord webhook returned {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")
            return False


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
