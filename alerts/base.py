"""
ObservaKit — Base Alert Dispatcher
Abstract base class, factory, deduplication, and noise suppression logic.
"""

from abc import ABC, abstractmethod


class AlertDispatcher(ABC):
    """Abstract base class for alert dispatchers."""

    @abstractmethod
    def send(
        self,
        message: str,
        subject: str = None,
        alert_type: str = None,
        table_name: str = None,
        **kwargs,
    ) -> bool:
        """
        Send an alert message.
        Returns True if successful, False otherwise.
        """
        ...


def get_alert_dispatcher(channel: str, **kwargs) -> AlertDispatcher:
    """Factory: return the appropriate alert dispatcher."""
    if channel == "slack":
        from alerts.slack import SlackDispatcher

        return SlackDispatcher(**kwargs)
    elif channel == "email":
        from alerts.email import EmailDispatcher

        return EmailDispatcher(**kwargs)
    elif channel == "discord":
        from alerts.discord import DiscordDispatcher

        return DiscordDispatcher(**kwargs)
    elif channel == "webhook":
        from alerts.webhook import WebhookDispatcher

        return WebhookDispatcher(**kwargs)
    elif channel == "teams":
        from alerts.teams import TeamsDispatcher

        return TeamsDispatcher(**kwargs)
    elif channel == "pagerduty":
        from alerts.pagerduty import PagerDutyDispatcher

        return PagerDutyDispatcher(**kwargs)
    else:
        raise ValueError(
            f"Unsupported alert channel: '{channel}'. "
            f"Supported: slack, email, discord, webhook, teams, pagerduty"
        )


# ---------------------------------------------------------------------------
# Noise suppression helpers
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHT = {"fail": 2, "warn": 1, "info": 0}


def _compute_noise_score(count_1h: int, count_24h: int, count_7d: int) -> float:
    """
    Composite noise score in [0, 100].

    Weights are chosen so that:
    - 1 alert/hour  →  ~30 pts  (moderate — watch but don't throttle)
    - 3 alerts/hour →  ~90 pts  (high — significant throttle applied)
    - 5+ alerts/hour → 100 pts  (maximum throttle)
    - Background churn (e.g. 20 alerts over 7 days) adds at most ~10 pts.
    """
    score = (count_1h * 20.0) + (count_24h * 2.0) + (count_7d * 0.5)
    return round(min(score, 100.0), 2)


def _compute_severity_trend(recent_severities: list[str], older_severities: list[str]) -> str:
    """
    Compare the average severity weight of two groups of alerts.
    Returns 'worsening', 'improving', or 'stable'.

    Returns 'stable' if either group is empty — no baseline means no trend.
    """
    if not recent_severities or not older_severities:
        return "stable"

    def _avg(sev_list):
        return sum(_SEVERITY_WEIGHT.get(s, 0) for s in sev_list) / len(sev_list)

    delta = _avg(recent_severities) - _avg(older_severities)
    if delta > 0.3:
        return "worsening"
    if delta < -0.3:
        return "improving"
    return "stable"


def _get_noise_config(config: dict) -> dict:
    """Extract noise_suppression section with safe defaults."""
    return config.get("alerts", {}).get("noise_suppression", {})


def _get_adaptive_dedup_window(noise_score: float, noise_cfg: dict) -> int:
    """
    Convert a noise score into a dedup window (minutes).

    The window grows exponentially with the score so that the first doubling
    happens around score=25 and the max is reached around score=75+.

    score=0   → min_window  (default 60 min)
    score=25  → ~2× min_window
    score=50  → ~4× min_window
    score=75  → ~8× min_window
    score=100 → max_window   (default 480 min / 8 h)
    """
    min_window = int(noise_cfg.get("min_dedup_window_minutes", 60))
    max_window = int(noise_cfg.get("max_dedup_window_minutes", 480))

    if noise_score <= 0:
        return min_window

    multiplier = 2 ** (noise_score / 25.0)
    adaptive = int(min_window * multiplier)
    return min(adaptive, max_window)


def _refresh_noise_record(db, table_name: str, alert_type: str) -> "AlertNoiseRecord | None":
    """
    Recalculate and persist the AlertNoiseRecord for (table_name, alert_type).
    Creates a new row if none exists. Returns the updated record (or None on error).
    """
    import logging
    from datetime import datetime, timedelta, timezone

    from backend.models import AlertLog, AlertNoiseRecord

    log = logging.getLogger(__name__)
    now = datetime.now(timezone.utc)

    try:
        # Count alerts across three windows from the audit log
        def _count(since: datetime) -> int:
            return (
                db.query(AlertLog)
                .filter(
                    AlertLog.table_name == table_name,
                    AlertLog.alert_type == alert_type,
                    AlertLog.success.is_(True),
                    AlertLog.sent_at >= since,
                )
                .count()
            )

        count_1h = _count(now - timedelta(hours=1))
        count_24h = _count(now - timedelta(hours=24))
        count_7d = _count(now - timedelta(days=7))
        noise_score = _compute_noise_score(count_1h, count_24h, count_7d)

        # Severity trend — compare last 5 alerts vs the 5 before those
        recent_rows = (
            db.query(AlertLog.severity)
            .filter(
                AlertLog.table_name == table_name,
                AlertLog.alert_type == alert_type,
                AlertLog.success.is_(True),
            )
            .order_by(AlertLog.sent_at.desc())
            .limit(10)
            .all()
        )
        severities = [r.severity for r in recent_rows if r.severity]
        severity_trend = _compute_severity_trend(severities[:5], severities[5:])

        # Fetch or create the noise record
        record = (
            db.query(AlertNoiseRecord)
            .filter(
                AlertNoiseRecord.table_name == table_name,
                AlertNoiseRecord.alert_type == alert_type,
            )
            .first()
        )
        if record is None:
            record = AlertNoiseRecord(table_name=table_name, alert_type=alert_type)
            db.add(record)

        record.count_1h = count_1h
        record.count_24h = count_24h
        record.count_7d = count_7d
        record.noise_score = noise_score
        record.severity_trend = severity_trend
        record.last_calculated_at = now

        # Determine whether the alert is currently throttled (score above threshold)
        from config.loader import load_config

        try:
            cfg = load_config("config/kit.yml")
        except Exception:
            cfg = {}
        noise_cfg = _get_noise_config(cfg)
        # Compare 24h count directly against the configured threshold so the
        # intent of "10 alerts per day triggers throttling" is unambiguous.
        throttle_threshold = int(noise_cfg.get("auto_throttle_threshold", 10))
        record.is_throttled = count_24h >= throttle_threshold

        db.commit()
        return record

    except Exception as exc:
        log.warning(f"Failed to refresh noise record for {table_name}/{alert_type}: {exc}")
        db.rollback()
        return None


# ---------------------------------------------------------------------------
# Public gating functions
# ---------------------------------------------------------------------------


def is_alert_suppressed(db, table_name: str) -> bool:
    """
    Return True if there is an active CheckSuppression window for table_name.
    Shared utility used by all router alert triggers.
    """
    from datetime import datetime, timezone

    from backend.models import CheckSuppression

    suppression = (
        db.query(CheckSuppression)
        .filter(
            CheckSuppression.table_name == table_name,
            CheckSuppression.suppressed_until >= datetime.now(timezone.utc),
        )
        .first()
    )
    if suppression:
        import logging

        logging.getLogger(__name__).info(
            f"Alert suppressed for {table_name} until {suppression.suppressed_until} "
            f"— reason: {suppression.reason}"
        )
        return True
    return False


def is_alert_deduped(db, table_name: str, alert_type: str, window_minutes: int = 60) -> bool:
    """
    Return True if an alert of the same (table, type) was already sent within
    the adaptive dedup window.

    The window starts at window_minutes (default 60) and grows exponentially
    based on the stored noise score for this (table, alert_type) pair, up to
    the configured max_dedup_window_minutes (default 480 min / 8 h).

    Noise suppression can be disabled globally via:
        alerts:
          noise_suppression:
            enabled: false
    """
    import logging
    from datetime import datetime, timedelta, timezone

    from backend.models import AlertLog, AlertNoiseRecord

    log = logging.getLogger(__name__)

    # Load noise suppression config
    from config.loader import load_config

    try:
        config = load_config("config/kit.yml")
    except Exception:
        config = {}
    noise_cfg = _get_noise_config(config)
    noise_enabled = noise_cfg.get("enabled", True)

    effective_window = window_minutes

    if noise_enabled and db and table_name:
        # Look up the persisted noise record (don't recalculate here — that
        # happens after a successful dispatch so counts stay accurate).
        try:
            record = (
                db.query(AlertNoiseRecord)
                .filter(
                    AlertNoiseRecord.table_name == table_name,
                    AlertNoiseRecord.alert_type == alert_type,
                )
                .first()
            )
            if record is not None:
                effective_window = _get_adaptive_dedup_window(record.noise_score, noise_cfg)
        except Exception as exc:
            log.warning(f"Could not read noise record for dedup window calculation: {exc}")

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=effective_window)
    recent = (
        db.query(AlertLog)
        .filter(
            AlertLog.table_name == table_name,
            AlertLog.alert_type == alert_type,
            AlertLog.sent_at >= cutoff,
        )
        .first()
    )
    if recent:
        log.info(
            f"Skipping duplicate {alert_type} alert for {table_name} "
            f"(dedup window: {effective_window} min, last sent: {recent.sent_at})"
        )
        return True
    return False


# ---------------------------------------------------------------------------
# Main dispatch entry point
# ---------------------------------------------------------------------------


def dispatch_alert(
    alert_type: str,
    message: str,
    table_name: str = None,
    subject: str = None,
    db=None,
    severity: str = "fail",
):
    """
    Dispatch an alert using routing rules from kit.yml.

    Gate order:
      1. Manual suppression window (CheckSuppression)
      2. Adaptive deduplication window (noise-aware)
      3. Route to matching channel(s) or default channel
      4. Log to AlertLog and refresh AlertNoiseRecord
    """
    import logging
    import re

    log = logging.getLogger(__name__)

    if db and table_name:
        if is_alert_suppressed(db, table_name):
            return
        if is_alert_deduped(db, table_name, alert_type):
            return

    from config.loader import load_config

    try:
        config = load_config("config/kit.yml")
    except Exception:
        config = {}

    routing_rules = config.get("alerts", {}).get("routing", [])
    dispatched = False

    # Prepend severity icon
    icon = "🔴" if severity == "fail" else "🟠"
    formatted_message = f"{icon} [{severity.upper()}] {message}"
    used_channel = None

    for rule in routing_rules:
        match = rule.get("match", {})
        type_match = match.get("alert_type") == alert_type or match.get("alert_type") is None
        severity_match = match.get("severity") == severity or match.get("severity") is None

        table_match = True
        if table_name and match.get("table_pattern"):
            pattern = match.get("table_pattern").replace("*", ".*")
            table_match = bool(re.match(f"^{pattern}$", table_name))

        if type_match and table_match and severity_match:
            channel = rule.get("channel", "slack")
            kwargs = {k: v for k, v in rule.items() if k not in ["match", "channel"]}
            try:
                dispatcher = get_alert_dispatcher(channel, **kwargs)
                if dispatcher.send(
                    formatted_message, subject, alert_type=alert_type, table_name=table_name
                ):
                    dispatched = True
                    used_channel = channel
            except Exception as e:
                log.error(f"Failed to send alert via {channel}: {e}")

    if not dispatched:
        # Fallback to default channel from config
        default_channel = config.get("alerts", {}).get("default_channel", "slack")
        try:
            dispatcher = get_alert_dispatcher(default_channel)
            if dispatcher.send(
                formatted_message, subject, alert_type=alert_type, table_name=table_name
            ):
                dispatched = True
                used_channel = default_channel
        except Exception as e:
            log.error(f"Failed to send default alert via {default_channel}: {e}")

    if dispatched and db:
        from backend.models import AlertLog

        try:
            log_entry = AlertLog(
                alert_type=alert_type,
                channel=used_channel,
                table_name=table_name,
                message=formatted_message,
                severity=severity,
                success=True,
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            log.warning(f"Failed to insert AlertLog: {e}")
            db.rollback()

        # Refresh noise record so the next dedup window is accurate
        if table_name:
            _refresh_noise_record(db, table_name, alert_type)


# ---------------------------------------------------------------------------
# Lineage helper (unchanged)
# ---------------------------------------------------------------------------


def get_lineage_impact(table_name: str) -> list[str]:
    """
    Get downstream tables impacted by an issue in table_name.
    Uses load_config() so env vars in kit.yml are expanded.
    """
    from config.loader import load_config

    try:
        config = load_config("config/kit.yml")
    except Exception:
        return []

    lineage = config.get("lineage", [])
    for entry in lineage:
        if entry.get("table") == table_name:
            return entry.get("downstream", [])
    return []
