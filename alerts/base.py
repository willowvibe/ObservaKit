"""
ObservaKit — Base Alert Dispatcher
Abstract base class and factory for alert dispatchers.
"""

from abc import ABC, abstractmethod


class AlertDispatcher(ABC):
    """Abstract base class for alert dispatchers."""

    @abstractmethod
    def send(self, message: str, subject: str = None) -> bool:
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
    else:
        raise ValueError(f"Unsupported alert channel: {channel}")


def dispatch_alert(alert_type: str, message: str, table_name: str = None, subject: str = None):
    """
    Dispatch an alert using routing rules from kit.yml.
    """
    import yaml
    import re
    import os

    try:
        with open("config/kit.yml", "r") as f:
            config = yaml.safe_load(f)
    except Exception:
        config = {}

    routing_rules = config.get("alerts", {}).get("routing", [])
    dispatched = False

    for rule in routing_rules:
        match = rule.get("match", {})
        type_match = match.get("alert_type") == alert_type or match.get("alert_type") is None
        
        table_match = True
        if table_name and match.get("table_pattern"):
            pattern = match.get("table_pattern").replace("*", ".*")
            table_match = bool(re.match(f"^{pattern}$", table_name))
        
        if type_match and table_match:
            channel = rule.get("channel", "slack")
            # Pass extra config (like specific slack channel) to the dispatcher
            kwargs = {k: v for k, v in rule.items() if k not in ["match", "channel"]}
            dispatcher = get_alert_dispatcher(channel, **kwargs)
            dispatcher.send(message, subject)
            dispatched = True

    if not dispatched:
        # Fallback to default channel from config
        default_channel = config.get("alerts", {}).get("default_channel", "slack")
        dispatcher = get_alert_dispatcher(default_channel)
        dispatcher.send(message, subject)


def get_lineage_impact(table_name: str) -> list[str]:
    """Get downstream tables impacted by an issue in table_name."""
    import yaml
    try:
        with open("config/kit.yml", "r") as f:
            config = yaml.safe_load(f)
    except Exception:
        return []

    lineage = config.get("lineage", [])
    for entry in lineage:
        if entry.get("table") == table_name:
            return entry.get("downstream", [])
    return []
