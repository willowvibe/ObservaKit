"""
Tests for alert noise suppression — scoring, adaptive dedup windows, and
severity trending.

Uses the in-memory SQLite db_session fixture from conftest.py so no real
database or HTTP connections are required.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from alerts.base import (
    _compute_noise_score,
    _compute_severity_trend,
    _get_adaptive_dedup_window,
    _refresh_noise_record,
    is_alert_deduped,
)
from backend.models import AlertLog, AlertNoiseRecord


# ---------------------------------------------------------------------------
# _compute_noise_score
# ---------------------------------------------------------------------------


class TestComputeNoiseScore:
    def test_zero_counts_give_zero_score(self):
        assert _compute_noise_score(0, 0, 0) == 0.0

    def test_one_alert_per_hour_is_low_noise(self):
        # 1/h, 5/24h, 10/7d → 20 + 10 + 5 = 35
        score = _compute_noise_score(1, 5, 10)
        assert score == 35.0

    def test_high_hourly_rate_hits_cap(self):
        # 6/h alone → 120 → capped at 100
        score = _compute_noise_score(6, 0, 0)
        assert score == 100.0

    def test_score_is_capped_at_100(self):
        score = _compute_noise_score(100, 100, 100)
        assert score == 100.0

    def test_24h_contribution(self):
        # Only 24h count: 10 alerts → 10 × 2 = 20
        score = _compute_noise_score(0, 10, 0)
        assert score == 20.0

    def test_7d_contribution(self):
        # Only 7d count: 40 alerts → 40 × 0.5 = 20
        score = _compute_noise_score(0, 0, 40)
        assert score == 20.0


# ---------------------------------------------------------------------------
# _compute_severity_trend
# ---------------------------------------------------------------------------


class TestComputeSeverityTrend:
    def test_equal_groups_are_stable(self):
        recent = ["fail", "fail"]
        older = ["fail", "fail"]
        assert _compute_severity_trend(recent, older) == "stable"

    def test_worsening_when_recent_more_severe(self):
        recent = ["fail", "fail", "fail"]
        older = ["warn", "warn", "warn"]
        assert _compute_severity_trend(recent, older) == "worsening"

    def test_improving_when_recent_less_severe(self):
        recent = ["warn", "warn"]
        older = ["fail", "fail", "fail"]
        assert _compute_severity_trend(recent, older) == "improving"

    def test_empty_recent_is_stable(self):
        assert _compute_severity_trend([], []) == "stable"

    def test_empty_older_is_stable(self):
        # No older baseline to compare against — cannot determine direction, so stable
        assert _compute_severity_trend(["fail"], []) == "stable"
        assert _compute_severity_trend([], ["warn"]) == "stable"

    def test_mixed_groups_can_be_stable(self):
        recent = ["fail", "warn"]   # avg = 1.5
        older = ["fail", "warn"]    # avg = 1.5
        assert _compute_severity_trend(recent, older) == "stable"


# ---------------------------------------------------------------------------
# _get_adaptive_dedup_window
# ---------------------------------------------------------------------------


class TestGetAdaptiveDedupWindow:
    _cfg = {"min_dedup_window_minutes": 60, "max_dedup_window_minutes": 480}

    def test_zero_score_returns_min_window(self):
        assert _get_adaptive_dedup_window(0.0, self._cfg) == 60

    def test_score_25_doubles_window(self):
        # 2^(25/25) = 2.0 → 60 × 2 = 120
        assert _get_adaptive_dedup_window(25.0, self._cfg) == 120

    def test_score_50_quadruples_window(self):
        # 2^(50/25) = 4.0 → 60 × 4 = 240
        assert _get_adaptive_dedup_window(50.0, self._cfg) == 240

    def test_score_100_hits_max_window(self):
        # 2^(100/25) = 16 → 60 × 16 = 960, capped at 480
        assert _get_adaptive_dedup_window(100.0, self._cfg) == 480

    def test_custom_min_max_respected(self):
        cfg = {"min_dedup_window_minutes": 30, "max_dedup_window_minutes": 120}
        # score=25 → 30 × 2 = 60
        assert _get_adaptive_dedup_window(25.0, cfg) == 60
        # score=100 → 30 × 16 = 480, capped at 120
        assert _get_adaptive_dedup_window(100.0, cfg) == 120


# ---------------------------------------------------------------------------
# _refresh_noise_record (integration with in-memory DB)
# ---------------------------------------------------------------------------


class TestRefreshNoiseRecord:
    @patch("config.loader.load_config")
    def test_creates_record_when_none_exists(self, mock_cfg, db_session):
        mock_cfg.return_value = {"alerts": {"noise_suppression": {"auto_throttle_threshold": 10}}}

        record = _refresh_noise_record(db_session, "public.orders", "freshness")

        assert record is not None
        assert record.table_name == "public.orders"
        assert record.alert_type == "freshness"
        assert record.noise_score == 0.0
        assert record.is_throttled is False

    @patch("config.loader.load_config")
    def test_counts_recent_alerts_correctly(self, mock_cfg, db_session):
        mock_cfg.return_value = {"alerts": {"noise_suppression": {"auto_throttle_threshold": 10}}}

        now = datetime.now(timezone.utc)
        for minutes_ago in [5, 15, 45]:
            db_session.add(
                AlertLog(
                    alert_type="freshness",
                    table_name="public.orders",
                    channel="slack",
                    message="stale",
                    severity="fail",
                    success=True,
                    sent_at=now - timedelta(minutes=minutes_ago),
                )
            )
        # One old alert outside 24h window
        db_session.add(
            AlertLog(
                alert_type="freshness",
                table_name="public.orders",
                channel="slack",
                message="stale",
                severity="fail",
                success=True,
                sent_at=now - timedelta(hours=30),
            )
        )
        db_session.commit()

        record = _refresh_noise_record(db_session, "public.orders", "freshness")

        assert record.count_1h == 3   # all three are within 1h
        assert record.count_24h == 3  # fourth is outside 24h
        assert record.count_7d == 4   # all four within 7d

    @patch("config.loader.load_config")
    def test_throttled_flag_set_above_threshold(self, mock_cfg, db_session):
        mock_cfg.return_value = {"alerts": {"noise_suppression": {"auto_throttle_threshold": 5}}}

        now = datetime.now(timezone.utc)
        # 6 alerts in last 24h (above threshold of 5)
        for i in range(6):
            db_session.add(
                AlertLog(
                    alert_type="volume",
                    table_name="public.events",
                    channel="slack",
                    message="anomaly",
                    severity="warn",
                    success=True,
                    sent_at=now - timedelta(hours=i),
                )
            )
        db_session.commit()

        record = _refresh_noise_record(db_session, "public.events", "volume")
        assert record.is_throttled is True

    @patch("config.loader.load_config")
    def test_not_throttled_below_threshold(self, mock_cfg, db_session):
        mock_cfg.return_value = {"alerts": {"noise_suppression": {"auto_throttle_threshold": 10}}}

        # Only 2 alerts in last 24h — well below threshold
        now = datetime.now(timezone.utc)
        for i in range(2):
            db_session.add(
                AlertLog(
                    alert_type="schema",
                    table_name="public.users",
                    channel="slack",
                    message="drift",
                    severity="warn",
                    success=True,
                    sent_at=now - timedelta(hours=i * 2),
                )
            )
        db_session.commit()

        record = _refresh_noise_record(db_session, "public.users", "schema")
        assert record.is_throttled is False

    @patch("config.loader.load_config")
    def test_severity_trend_worsening_detected(self, mock_cfg, db_session):
        mock_cfg.return_value = {"alerts": {"noise_suppression": {"auto_throttle_threshold": 10}}}

        now = datetime.now(timezone.utc)
        # Recent 5: all 'fail'
        for i in range(5):
            db_session.add(
                AlertLog(
                    alert_type="quality",
                    table_name="public.payments",
                    channel="slack",
                    message="check failed",
                    severity="fail",
                    success=True,
                    sent_at=now - timedelta(minutes=i * 10),
                )
            )
        # Older 5: all 'warn'
        for i in range(5):
            db_session.add(
                AlertLog(
                    alert_type="quality",
                    table_name="public.payments",
                    channel="slack",
                    message="check warned",
                    severity="warn",
                    success=True,
                    sent_at=now - timedelta(hours=2 + i),
                )
            )
        db_session.commit()

        record = _refresh_noise_record(db_session, "public.payments", "quality")
        assert record.severity_trend == "worsening"

    @patch("config.loader.load_config")
    def test_idempotent_upsert(self, mock_cfg, db_session):
        """Calling _refresh_noise_record twice should not create duplicate rows."""
        mock_cfg.return_value = {"alerts": {"noise_suppression": {"auto_throttle_threshold": 10}}}

        _refresh_noise_record(db_session, "public.orders", "freshness")
        _refresh_noise_record(db_session, "public.orders", "freshness")

        count = (
            db_session.query(AlertNoiseRecord)
            .filter_by(table_name="public.orders", alert_type="freshness")
            .count()
        )
        assert count == 1


# ---------------------------------------------------------------------------
# is_alert_deduped with noise-aware window (integration)
# ---------------------------------------------------------------------------


class TestIsAlertDedupedWithNoise:
    @patch("config.loader.load_config")
    def test_no_noise_uses_base_window(self, mock_cfg, db_session):
        """With no noise record, the default 60-min window is applied."""
        mock_cfg.return_value = {
            "alerts": {
                "noise_suppression": {
                    "enabled": True,
                    "min_dedup_window_minutes": 60,
                    "max_dedup_window_minutes": 480,
                }
            }
        }
        # Alert sent 30 minutes ago — within 60-min base window
        db_session.add(
            AlertLog(
                alert_type="freshness",
                table_name="public.orders",
                channel="slack",
                message="stale",
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            )
        )
        db_session.commit()

        assert is_alert_deduped(db_session, "public.orders", "freshness") is True

    @patch("config.loader.load_config")
    def test_high_noise_extends_window(self, mock_cfg, db_session):
        """A high noise score (≥25) should extend the dedup window beyond 60 min."""
        mock_cfg.return_value = {
            "alerts": {
                "noise_suppression": {
                    "enabled": True,
                    "min_dedup_window_minutes": 60,
                    "max_dedup_window_minutes": 480,
                }
            }
        }
        # Pre-populate a noise record with a high score
        noise = AlertNoiseRecord(
            table_name="public.orders",
            alert_type="volume",
            count_1h=3,
            count_24h=15,
            count_7d=50,
            noise_score=75.0,  # → window = min(480, 60 × 2^3) = min(480, 480) = 480 min
            severity_trend="worsening",
            is_throttled=True,
        )
        db_session.add(noise)

        # Alert sent 90 minutes ago — outside normal 60-min window but inside 480-min window
        db_session.add(
            AlertLog(
                alert_type="volume",
                table_name="public.orders",
                channel="slack",
                message="anomaly",
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=90),
            )
        )
        db_session.commit()

        # Should be deduped because adaptive window is 480 min
        assert is_alert_deduped(db_session, "public.orders", "volume") is True

    @patch("config.loader.load_config")
    def test_noise_suppression_disabled_uses_passed_window(self, mock_cfg, db_session):
        """When noise_suppression.enabled=false, the passed window_minutes is used directly."""
        mock_cfg.return_value = {
            "alerts": {
                "noise_suppression": {
                    "enabled": False,
                    "min_dedup_window_minutes": 60,
                }
            }
        }
        # High noise record exists but suppression is disabled
        noise = AlertNoiseRecord(
            table_name="public.orders",
            alert_type="schema",
            noise_score=90.0,
            is_throttled=True,
            count_1h=5,
            count_24h=20,
            count_7d=60,
        )
        db_session.add(noise)

        # Alert sent 90 minutes ago — would be inside adaptive window (480 min) if enabled,
        # but since suppression is disabled it falls outside the passed window_minutes=60.
        db_session.add(
            AlertLog(
                alert_type="schema",
                table_name="public.orders",
                channel="slack",
                message="drift",
                sent_at=datetime.now(timezone.utc) - timedelta(minutes=90),
            )
        )
        db_session.commit()

        # Noise suppression off → use window_minutes=60 → 90 min ago is NOT deduped
        assert is_alert_deduped(db_session, "public.orders", "schema", window_minutes=60) is False
