"""
Tests for alert suppression window and deduplication logic.

Uses the actual CheckSuppression + AlertLog SQLAlchemy models with an
in-memory SQLite DB (from the db_session fixture in conftest.py).
"""

from datetime import datetime, timedelta, timezone

from alerts.base import is_alert_deduped, is_alert_suppressed
from backend.models import AlertLog, CheckSuppression


class TestAlertSuppression:
    """Tests for is_alert_suppressed() which queries CheckSuppression."""

    def test_no_suppression_row_returns_false(self, db_session):
        result = is_alert_suppressed(db_session, "public.orders")
        assert result is False

    def test_active_suppression_returns_true(self, db_session):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        suppression = CheckSuppression(
            table_name="public.orders",
            suppressed_until=future,
            reason="maintenance window",
        )
        db_session.add(suppression)
        db_session.commit()

        result = is_alert_suppressed(db_session, "public.orders")
        assert result is True

    def test_expired_suppression_returns_false(self, db_session):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        suppression = CheckSuppression(
            table_name="public.events",
            suppressed_until=past,
            reason="old maintenance window",
        )
        db_session.add(suppression)
        db_session.commit()

        result = is_alert_suppressed(db_session, "public.events")
        assert result is False

    def test_suppression_for_different_table_does_not_match(self, db_session):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        suppression = CheckSuppression(
            table_name="public.users",
            suppressed_until=future,
            reason="scoped suppression",
        )
        db_session.add(suppression)
        db_session.commit()

        # Different table — should not be suppressed
        result = is_alert_suppressed(db_session, "public.orders")
        assert result is False

    def test_suppression_just_on_boundary(self, db_session):
        """suppressed_until = now + 1 second should still be active."""
        almost_now = datetime.now(timezone.utc) + timedelta(seconds=1)
        suppression = CheckSuppression(
            table_name="public.boundary",
            suppressed_until=almost_now,
            reason="boundary test",
        )
        db_session.add(suppression)
        db_session.commit()

        result = is_alert_suppressed(db_session, "public.boundary")
        assert result is True


class TestAlertDeduplication:
    """Tests for is_alert_deduped() which queries AlertLog."""

    def test_no_recent_alert_not_deduped(self, db_session):
        result = is_alert_deduped(db_session, "public.orders", "freshness")
        assert result is False

    def test_recent_alert_is_deduped(self, db_session):
        recent = datetime.now(timezone.utc) - timedelta(minutes=10)
        alert = AlertLog(
            alert_type="freshness",
            table_name="public.orders",
            message="Table is stale",
            channel="slack",
            sent_at=recent,
        )
        db_session.add(alert)
        db_session.commit()

        result = is_alert_deduped(db_session, "public.orders", "freshness")
        assert result is True

    def test_old_alert_is_not_deduped(self, db_session):
        """Alert older than the default 60-min window should not suppress new alerts."""
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        alert = AlertLog(
            alert_type="quality",
            table_name="public.payments",
            message="Check failed",
            channel="slack",
            sent_at=old,
        )
        db_session.add(alert)
        db_session.commit()

        result = is_alert_deduped(db_session, "public.payments", "quality")
        assert result is False

    def test_dedup_is_type_scoped(self, db_session):
        """A freshness alert should not suppress a volume alert for the same table."""
        recent = datetime.now(timezone.utc) - timedelta(minutes=5)
        alert = AlertLog(
            alert_type="freshness",
            table_name="public.orders",
            message="Stale",
            channel="slack",
            sent_at=recent,
        )
        db_session.add(alert)
        db_session.commit()

        # Same table, different alert type — NOT deduped
        result = is_alert_deduped(db_session, "public.orders", "volume")
        assert result is False

    def test_custom_window_respected(self, db_session):
        """Alert 30 minutes old is within a 60-min window but outside a 20-min window."""
        alert = AlertLog(
            alert_type="schema",
            table_name="public.users",
            message="Column added",
            channel="slack",
            sent_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        db_session.add(alert)
        db_session.commit()

        assert is_alert_deduped(db_session, "public.users", "schema", window_minutes=60) is True
        assert is_alert_deduped(db_session, "public.users", "schema", window_minutes=20) is False
