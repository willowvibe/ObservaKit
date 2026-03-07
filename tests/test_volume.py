"""
ObservaKit — Volume Monitor Tests
"""

import pytest
from datetime import datetime, timezone, timedelta

from backend.models import VolumeRecord


class TestVolumeModel:
    """Test the VolumeRecord model."""

    def test_create_volume_record(self, db_session):
        record = VolumeRecord(
            table_name="public.orders",
            dag_id="load_orders",
            row_count=5000,
            rolling_avg=4800.0,
            deviation_pct=0.042,
            is_anomaly=False,
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.query(VolumeRecord).first()
        assert result is not None
        assert result.row_count == 5000
        assert result.is_anomaly is False

    def test_anomaly_detection_flag(self, db_session):
        # Normal record
        normal = VolumeRecord(
            table_name="public.orders",
            dag_id="load_orders",
            row_count=5000,
            rolling_avg=4900.0,
            deviation_pct=0.02,
            is_anomaly=False,
        )
        # Anomalous record
        anomaly = VolumeRecord(
            table_name="public.orders",
            dag_id="load_orders",
            row_count=100,
            rolling_avg=4900.0,
            deviation_pct=0.98,
            is_anomaly=True,
        )
        db_session.add_all([normal, anomaly])
        db_session.commit()

        anomalies = db_session.query(VolumeRecord).filter(VolumeRecord.is_anomaly == True).all()
        assert len(anomalies) == 1
        assert anomalies[0].row_count == 100
        assert anomalies[0].deviation_pct == pytest.approx(0.98)

    def test_volume_history_ordering(self, db_session):
        for i in range(5):
            record = VolumeRecord(
                table_name="public.orders",
                dag_id="load_orders",
                row_count=1000 + i * 100,
                recorded_at=datetime.now(timezone.utc) - timedelta(hours=i),
            )
            db_session.add(record)
        db_session.commit()

        records = (
            db_session.query(VolumeRecord)
            .order_by(VolumeRecord.recorded_at.desc())
            .all()
        )
        assert len(records) == 5
        # Most recent should have the lowest row count offset
        assert records[0].row_count == 1000
