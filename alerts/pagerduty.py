"""
ObservaKit — PagerDuty Alert Dispatcher
Sends alerts via the PagerDuty Events API v2.

Configuration (environment variables):
    PAGERDUTY_ROUTING_KEY — the integration key from a PagerDuty Events API v2 service.
    PAGERDUTY_SEVERITY_MAP — optional JSON map, e.g. '{"fail": "critical", "warn": "warning"}'

Severity mapping (ObservaKit → PagerDuty):
    fail  → critical
    warn  → warning
    info  → info

Deduplication key: <table_name>:<alert_type> — so repeated failures update the
same incident rather than creating new ones. Resolved incidents are auto-resolved
when ObservaKit detects the check is back to 'ok'.

Example kit.yml:
    alerts:
      routing:
        - match: {severity: fail}
          channel: pagerduty
        - match: {severity: warn}
          channel: slack
"""

import json
import logging
import os

import httpx

from alerts.base import AlertDispatcher

logger = logging.getLogger(__name__)

_EVENTS_V2_URL = "https://events.pagerduty.com/v2/enqueue"

_SEVERITY_MAP = {
    "fail": "critical",
    "warn": "warning",
    "info": "info",
    "ok": "info",
}


class PagerDutyDispatcher(AlertDispatcher):
    """Sends alerts using the PagerDuty Events API v2."""

    def __init__(self, **kwargs):
        self._routing_key = kwargs.get("pagerduty_routing_key") or os.getenv("PAGERDUTY_ROUTING_KEY", "")
        # Allow overriding severity map via env var (JSON string)
        custom_map = os.getenv("PAGERDUTY_SEVERITY_MAP")
        if custom_map:
            try:
                self._severity_map = {**_SEVERITY_MAP, **json.loads(custom_map)}
            except json.JSONDecodeError:
                logger.warning("PAGERDUTY_SEVERITY_MAP is not valid JSON — using defaults")
                self._severity_map = _SEVERITY_MAP
        else:
            self._severity_map = _SEVERITY_MAP

    def send(
        self,
        message: str,
        subject: str = None,
        alert_type: str = None,
        table_name: str = None,
        severity: str = "fail",
        **kwargs,
    ) -> bool:
        if not self._routing_key:
            logger.warning("PAGERDUTY_ROUTING_KEY is not configured — skipping PagerDuty alert")
            return False

        pd_severity = self._severity_map.get(severity, "error")
        # Stable dedup key — same key = update existing incident, not a new one
        dedup_key = f"{table_name or 'global'}:{alert_type or 'unknown'}"
        summary = subject or f"ObservaKit {alert_type or 'alert'}: {table_name or 'unknown table'}"

        payload = {
            "routing_key": self._routing_key,
            "event_action": "trigger",
            "dedup_key": dedup_key,
            "payload": {
                "summary": summary,
                "severity": pd_severity,
                "source": "ObservaKit",
                "custom_details": {
                    "message": message,
                    "alert_type": alert_type,
                    "table": table_name,
                },
            },
        }

        try:
            resp = httpx.post(_EVENTS_V2_URL, json=payload, timeout=10)
            data = resp.json()
            if resp.status_code in (200, 202) and data.get("status") == "success":
                logger.info(
                    "PagerDuty alert triggered (dedup_key=%s, severity=%s)", dedup_key, pd_severity
                )
                return True
            else:
                logger.error(
                    "PagerDuty API returned %d: %s", resp.status_code, resp.text
                )
                return False
        except Exception as exc:
            logger.error("Failed to send PagerDuty alert: %s", exc)
            return False

    def resolve(self, alert_type: str, table_name: str = None) -> bool:
        """
        Resolve an open PagerDuty incident.
        Call this when a previously-failing check returns to 'ok'.
        """
        if not self._routing_key:
            return False

        dedup_key = f"{table_name or 'global'}:{alert_type or 'unknown'}"
        payload = {
            "routing_key": self._routing_key,
            "event_action": "resolve",
            "dedup_key": dedup_key,
        }

        try:
            resp = httpx.post(_EVENTS_V2_URL, json=payload, timeout=10)
            if resp.status_code in (200, 202):
                logger.info("PagerDuty incident resolved (dedup_key=%s)", dedup_key)
                return True
            else:
                logger.error("PagerDuty resolve returned %d: %s", resp.status_code, resp.text)
                return False
        except Exception as exc:
            logger.error("Failed to resolve PagerDuty incident: %s", exc)
            return False
