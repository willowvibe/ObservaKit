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


def get_alert_dispatcher(channel: str) -> AlertDispatcher:
    """Factory: return the appropriate alert dispatcher."""
    if channel == "slack":
        from alerts.slack import SlackDispatcher
        return SlackDispatcher()
    elif channel == "email":
        from alerts.email import EmailDispatcher
        return EmailDispatcher()
    else:
        raise ValueError(f"Unsupported alert channel: {channel}")
