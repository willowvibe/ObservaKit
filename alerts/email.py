"""
ObservaKit — Email Alert Dispatcher
Sends alerts via SMTP email.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from alerts.base import AlertDispatcher

logger = logging.getLogger(__name__)


class EmailDispatcher(AlertDispatcher):
    """Sends alerts via SMTP email."""

    def __init__(self):
        self._smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self._smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self._smtp_user = os.getenv("SMTP_USER", "")
        self._smtp_password = os.getenv("SMTP_PASSWORD", "")
        self._from_addr = os.getenv("ALERT_EMAIL_FROM", "")
        self._to_addr = os.getenv("ALERT_EMAIL_TO", "")

    def send(self, message: str, subject: str = None) -> bool:
        """Send an email alert via SMTP."""
        if not self._smtp_user or not self._to_addr:
            logger.warning("Email SMTP not configured — skipping alert")
            return False

        msg = MIMEMultipart()
        msg["From"] = self._from_addr or self._smtp_user
        msg["To"] = self._to_addr
        msg["Subject"] = subject or "ObservaKit Alert"
        msg.attach(MIMEText(message, "plain"))

        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                server.login(self._smtp_user, self._smtp_password)
                server.send_message(msg)
            logger.info(f"Email alert sent to {self._to_addr}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False
