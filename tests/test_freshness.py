"""
ObservaKit — Freshness Monitor Tests
"""

from datetime import datetime, timedelta, timezone

from backend.models import FreshnessRecord
from backend.routers.freshness import _parse_duration


class TestParseDuration:
    """Test the duration string parser."""

    def test_parse_hours(self):
        assert _parse_duration("1h") == 3600
        assert _parse_duration("2h") == 7200
        assert _parse_duration("0.5h") == 1800

    def test_parse_minutes(self):
        assert _parse_duration("30m") == 1800
        assert _parse_duration("15m") == 900

    def test_parse_seconds(self):
        assert _parse_duration("60s") == 60

    def test_parse_days(self):
        assert _parse_duration("1d") == 86400

    def test_parse_raw_number(self):
        assert _parse_duration("3600") == 3600


class TestFreshnessModel:
    """Test the FreshnessRecord model."""

    def test_create_freshness_record(self, db_session):
        record = FreshnessRecord(
            table_name="public.orders",
            timestamp_column="updated_at",
            last_updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
            lag_seconds=3600,
            status="warn",
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.query(FreshnessRecord).first()
        assert result is not None
        assert result.table_name == "public.orders"
        assert result.status == "warn"
        assert result.lag_seconds == 3600

    def test_freshness_statuses(self, db_session):
        for status in ("ok", "warn", "fail"):
            record = FreshnessRecord(
                table_name=f"table_{status}",
                timestamp_column="updated_at",
                lag_seconds=100,
                status=status,
            )
            db_session.add(record)
        db_session.commit()

        records = db_session.query(FreshnessRecord).all()
        assert len(records) == 3
        statuses = {r.status for r in records}
        assert statuses == {"ok", "warn", "fail"}
