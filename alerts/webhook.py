"""
ObservaKit — Generic Outgoing Webhook Alert Dispatcher

Sends a structured JSON payload to any HTTP endpoint via POST.
This enables integration with any system that accepts webhooks:
  - PagerDuty (Events API v2)
  - Opsgenie
  - Custom internal alerting platforms
  - Zapier / Make (Integromat)
  - n8n
  - Any internal monitoring aggregator

Payload format (sent as application/json):
  {
    "source": "observakit",
    "version": "0.1.7",
    "alert_type": "volume",
    "table_name": "public.orders",
    "subject": "🔴 Volume Anomaly: public.orders",
    "message": "...",
    "timestamp": "2024-01-15T10:30:00Z",
    "severity": "critical"   // info | warning | critical
  }

HMAC Signing (optional):
  Set WEBHOOK_SECRET to a shared secret. ObservaKit will add an
  X-ObservaKit-Signature header (HMAC-SHA256 of the body) so the
  receiver can verify authenticity.

Config in kit.yml:
  alerts:
    routing:
      - match:
          alert_type: "quality"
        channel: webhook
        webhook_url: "https://your-endpoint.example.com/alerts"
        webhook_severity_map:
          quality: critical
          freshness: warning
          volume: critical
          schema: warning
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

import httpx

from alerts.base import AlertDispatcher

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {
    "quality": "critical",
    "volume": "critical",
    "contract": "critical",
    "freshness": "warning",
    "schema": "warning",
    "distribution": "warning",
    "finops": "info",
}


class WebhookDispatcher(AlertDispatcher):
    """Sends a structured JSON alert to a generic HTTP webhook endpoint."""

    def __init__(self, **kwargs):
        # URL can come from routing rule kwargs or environment
        self._url = kwargs.get("webhook_url") or os.getenv("WEBHOOK_ALERT_URL", "")
        self._secret = os.getenv("WEBHOOK_SECRET", "")
        self._severity_map = kwargs.get("webhook_severity_map", {})
        # Extra headers to pass (e.g. Authorization for internal services)
        self._extra_headers: dict = {}
        auth_header = os.getenv("WEBHOOK_AUTH_HEADER", "")   # e.g. "Bearer my-token"
        if auth_header:
            self._extra_headers["Authorization"] = auth_header

    def send(
        self,
        message: str,
        subject: str = None,
        alert_type: str = None,
        table_name: str = None,
    ) -> bool:
        if not self._url:
            logger.warning("Webhook URL not configured — skipping webhook alert")
            return False

        severity = (
            self._severity_map.get(alert_type)
            or _SEVERITY_MAP.get(alert_type, "info")
        )

        payload = {
            "source": "observakit",
            "version": "0.1.7",
            "alert_type": alert_type or "unknown",
            "table_name": table_name,
            "subject": subject,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": severity,
        }

        body = json.dumps(payload, ensure_ascii=False)
        headers = {"Content-Type": "application/json", **self._extra_headers}

        if self._secret:
            sig = hmac.new(
                self._secret.encode(),
                body.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-ObservaKit-Signature"] = f"sha256={sig}"

        try:
            resp = httpx.post(self._url, content=body, headers=headers, timeout=15)
            if 200 <= resp.status_code < 300:
                logger.info(f"Webhook alert sent to {self._url} (HTTP {resp.status_code})")
                return True
            else:
                logger.error(f"Webhook returned {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Failed to send webhook alert to {self._url}: {e}")
            return False
