"""
Verification tests for Stage 3 (P1) Production Readiness:
1. Alert Logging & Deduplication in dispatch_alert.
2. Resilient Query Retries (Tenacity).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from alerts.base import dispatch_alert
from backend.models import AlertLog, CheckSuppression
from connectors.base import resilient_query


class TestStage3Resiliency:
    def test_dispatch_alert_logs_to_db(self, db_session, monkeypatch):
        """Verify that dispatch_alert creates an AlertLog record when db is provided."""
        # Mock dispatcher to return True (success)
        mock_dispatcher = MagicMock()
        mock_dispatcher.send.return_value = True

        monkeypatch.setattr(
            "alerts.base.get_alert_dispatcher", lambda *args, **kwargs: mock_dispatcher
        )
        # Mock config to avoid file lookups
        monkeypatch.setattr(
            "config.loader.load_config", lambda *args: {"alerts": {"default_channel": "slack"}}
        )

        dispatch_alert(
            alert_type="test_alert",
            message="Hello World",
            table_name="public.users",
            db=db_session,
            severity="fail",
        )

        # Verify log entry exists
        log = db_session.query(AlertLog).filter(AlertLog.table_name == "public.users").first()
        assert log is not None
        assert log.alert_type == "test_alert"
        assert "[FAIL]" in log.message
        assert "🔴" in log.message

    def test_dispatch_alert_deduplication(self, db_session, monkeypatch):
        """Verify that dispatch_alert honors the 1-hour deduplication window."""
        mock_dispatcher = MagicMock()
        mock_dispatcher.send.return_value = True
        monkeypatch.setattr(
            "alerts.base.get_alert_dispatcher", lambda *args, **kwargs: mock_dispatcher
        )
        monkeypatch.setattr(
            "config.loader.load_config", lambda *args: {"alerts": {"default_channel": "slack"}}
        )

        # 1. Dispatch first alert
        dispatch_alert("quality", "First fail", "public.orders", db=db_session)
        assert mock_dispatcher.send.call_count == 1

        # 2. Dispatch second alert immediately (same type/table)
        dispatch_alert("quality", "Second fail", "public.orders", db=db_session)
        # Should NOT have sent again
        assert mock_dispatcher.send.call_count == 1

        # 3. Dispatch alert for different table
        dispatch_alert("quality", "Other fail", "public.users", db=db_session)
        assert mock_dispatcher.send.call_count == 2

    def test_dispatch_alert_suppression(self, db_session, monkeypatch):
        """Verify that dispatch_alert honors active CheckSuppression windows."""
        mock_dispatcher = MagicMock()
        mock_dispatcher.send.return_value = True
        monkeypatch.setattr(
            "alerts.base.get_alert_dispatcher", lambda *args, **kwargs: mock_dispatcher
        )
        monkeypatch.setattr(
            "config.loader.load_config", lambda *args: {"alerts": {"default_channel": "slack"}}
        )

        # Add suppression
        db_session.add(
            CheckSuppression(
                table_name="public.orders",
                suppressed_until=datetime.now(timezone.utc) + timedelta(hours=1),
                reason="testing",
            )
        )
        db_session.commit()

        dispatch_alert("quality", "Fail", "public.orders", db=db_session)
        # Should NOT have sent
        assert mock_dispatcher.send.call_count == 0

    def test_resilient_query_retries(self):
        """Verify that the resilient_query decorator retries on failure."""

        call_count = 0

        @resilient_query()
        def unstable_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Transient Error")
            return "Success"

        # We need to monkeypatch the wait to make the test fast
        with patch("tenacity.nap.time.sleep", return_value=None):
            result = unstable_function()

        assert result == "Success"
        assert call_count == 3
