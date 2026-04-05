"""
ObservaKit — Slack Alert Dispatcher
Sends alerts to Slack via Incoming Webhooks using Block Kit layouts.

Features:
- Block Kit structured message (header, body, context footer, action button)
- Severity colour strip via Block Kit attachments
- Retry on HTTP 429 (rate limit) and 5xx with exponential backoff
- Falls back gracefully to plain text if blocks are disabled

Configuration (environment variables):
    SLACK_WEBHOOK_URL        — full Incoming Webhook URL
    SLACK_CHANNEL            — target channel (default: #data-alerts)
    OBSERVAKIT_DASHBOARD_URL — optional link included in the alert button
"""

import logging
import os
import time

import httpx

from alerts.base import AlertDispatcher

logger = logging.getLogger(__name__)

_SEVERITY_COLOUR = {
    "fail": "#d63031",  # red
    "warn": "#fdcb6e",  # yellow
    "info": "#74b9ff",  # blue
    "ok": "#00b894",  # green
}


class SlackDispatcher(AlertDispatcher):
    """Sends alerts to Slack using Block Kit via Incoming Webhooks."""

    def __init__(self, **kwargs):
        self._webhook_url = kwargs.get("slack_webhook_url") or os.getenv("SLACK_WEBHOOK_URL", "")
        self._channel = kwargs.get("slack_channel") or os.getenv("SLACK_CHANNEL", "#data-alerts")
        self._dashboard_url = os.getenv("OBSERVAKIT_DASHBOARD_URL", "")

    def send(
        self,
        message: str,
        subject: str = None,
        alert_type: str = None,
        table_name: str = None,
        severity: str = "fail",
        blocks: list = None,
        **kwargs,
    ) -> bool:
        if not self._webhook_url or self._webhook_url.startswith(
            "https://hooks.slack.com/services/YOUR"
        ):
            logger.warning("Slack webhook URL not configured — skipping alert")
            return False

        payload = self._build_payload(
            message=message,
            subject=subject,
            alert_type=alert_type,
            table_name=table_name,
            severity=severity,
            blocks=blocks,
        )
        return self._post_with_retry(payload)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        message: str,
        subject: str = None,
        alert_type: str = None,
        table_name: str = None,
        severity: str = "fail",
        blocks: list = None,
    ) -> dict:
        """Build a Slack Incoming Webhook payload using Block Kit."""
        title = subject or f"ObservaKit: {alert_type or 'alert'}"
        colour = _SEVERITY_COLOUR.get(severity, _SEVERITY_COLOUR["fail"])

        if blocks:
            # Caller supplied custom blocks — wrap in attachment for colour strip
            return {
                "channel": self._channel,
                "username": "ObservaKit",
                "icon_emoji": ":mag:",
                "attachments": [{"color": colour, "blocks": blocks}],
            }

        # Build standard Block Kit layout
        body_blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title, "emoji": True},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message},
            },
        ]

        # Context footer (table name + alert type)
        context_elements = []
        if table_name:
            context_elements.append({"type": "mrkdwn", "text": f"*Table:* `{table_name}`"})
        if alert_type:
            context_elements.append({"type": "mrkdwn", "text": f"*Type:* {alert_type}"})
        if context_elements:
            body_blocks.append({"type": "context", "elements": context_elements})

        # Dashboard action button
        if self._dashboard_url:
            body_blocks.append({"type": "divider"})
            body_blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View in ObservaKit"},
                            "url": self._dashboard_url,
                            "style": "primary" if severity == "ok" else "danger",
                        }
                    ],
                }
            )

        return {
            "channel": self._channel,
            "username": "ObservaKit",
            "icon_emoji": ":mag:",
            "attachments": [{"color": colour, "blocks": body_blocks}],
        }

    def _post_with_retry(self, payload: dict, max_attempts: int = 3) -> bool:
        """POST to the Slack webhook with retry on 429 and 5xx errors."""
        for attempt in range(1, max_attempts + 1):
            try:
                resp = httpx.post(self._webhook_url, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info("Slack alert sent to %s", self._channel)
                    return True

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2**attempt))
                    logger.warning(
                        "Slack rate limited (429) — retrying in %ds (attempt %d/%d)",
                        retry_after,
                        attempt,
                        max_attempts,
                    )
                    time.sleep(retry_after)
                    continue

                if resp.status_code >= 500:
                    backoff = 2**attempt
                    logger.warning(
                        "Slack 5xx (%d) — retrying in %ds (attempt %d/%d)",
                        resp.status_code,
                        backoff,
                        attempt,
                        max_attempts,
                    )
                    time.sleep(backoff)
                    continue

                # 4xx client error other than 429 — do not retry
                logger.error("Slack webhook returned %d: %s", resp.status_code, resp.text)
                return False

            except Exception as exc:
                backoff = 2**attempt
                logger.warning(
                    "Slack request error: %s — retrying in %ds (attempt %d/%d)",
                    exc,
                    backoff,
                    attempt,
                    max_attempts,
                )
                if attempt < max_attempts:
                    time.sleep(backoff)

        logger.error("Slack alert failed after %d attempts", max_attempts)
        return False
