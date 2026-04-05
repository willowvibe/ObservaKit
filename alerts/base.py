"""
ObservaKit — Base Alert Dispatcher
Abstract base class and factory for alert dispatchers.
"""

from abc import ABC, abstractmethod


class AlertDispatcher(ABC):
    """Abstract base class for alert dispatchers."""

    @abstractmethod
    def send(self, message: str, subject: str = None, alert_type: str = None,
             table_name: str = None, **kwargs) -> bool:
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
    else:
        raise ValueError(
            f"Unsupported alert channel: '{channel}'. "
            f"Supported: slack, email, discord, webhook"
        )


def dispatch_alert(alert_type: str, message: str, table_name: str = None, subject: str = None, db=None, severity: str = "fail"):
    """
    Dispatch an alert using routing rules from kit.yml.
    Uses load_config() so that ${VAR:-default} env vars are properly expanded.
    """
    import re
    import logging

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
                if dispatcher.send(formatted_message, subject, alert_type=alert_type, table_name=table_name):
                    dispatched = True
                    used_channel = channel
            except Exception as e:
                logging.getLogger(__name__).error(f"Failed to send alert via {channel}: {e}")

    if not dispatched:
        # Fallback to default channel from config
        default_channel = config.get("alerts", {}).get("default_channel", "slack")
        try:
            dispatcher = get_alert_dispatcher(default_channel)
            if dispatcher.send(formatted_message, subject, alert_type=alert_type, table_name=table_name):
                dispatched = True
                used_channel = default_channel
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to send default alert via {default_channel}: {e}")

    if dispatched and db:
        from backend.models import AlertLog
        try:
            log = AlertLog(
                alert_type=alert_type,
                channel=used_channel,
                table_name=table_name,
                message=formatted_message,
                success=True
            )
            db.add(log)
            db.commit()
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to insert AlertLog: {e}")
            db.rollback()


def is_alert_suppressed(db, table_name: str) -> bool:
    """
    Return True if there is an active CheckSuppression window for table_name.
    Shared utility used by all router alert triggers.
    """
    from datetime import datetime, timezone

    from backend.models import CheckSuppression

    suppression = db.query(CheckSuppression).filter(
        CheckSuppression.table_name == table_name,
        CheckSuppression.suppressed_until >= datetime.now(timezone.utc),
    ).first()
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
    the last window_minutes. Used to prevent notification floods.
    """
    from datetime import datetime, timedelta, timezone

    from backend.models import AlertLog

    recent = db.query(AlertLog).filter(
        AlertLog.table_name == table_name,
        AlertLog.alert_type == alert_type,
        AlertLog.sent_at >= datetime.now(timezone.utc) - timedelta(minutes=window_minutes),
    ).first()
    if recent:
        import logging
        logging.getLogger(__name__).info(
            f"Skipping duplicate {alert_type} alert for {table_name} "
            f"(last sent {recent.sent_at})"
        )
        return True
    return False


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
