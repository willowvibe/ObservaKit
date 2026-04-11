"""
ObservaKit — Alert Noise Suppression API

Endpoints for inspecting and managing the noise scores that drive adaptive
alert deduplication.  All routes sit under /alerts/noise.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.models import AlertLog, AlertNoiseRecord, get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize(record: AlertNoiseRecord) -> dict:
    return {
        "table_name": record.table_name,
        "alert_type": record.alert_type,
        "count_1h": record.count_1h,
        "count_24h": record.count_24h,
        "count_7d": record.count_7d,
        "noise_score": record.noise_score,
        "severity_trend": record.severity_trend,
        "is_throttled": record.is_throttled,
        "last_calculated_at": (
            record.last_calculated_at.isoformat() if record.last_calculated_at else None
        ),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", summary="List all noise records")
def list_noise_records(db: Session = Depends(get_db)):
    """
    Return noise scores for every (table, alert_type) pair that has been
    tracked.  Records are sorted by noise_score descending so the noisiest
    alerts surface first.
    """
    records = (
        db.query(AlertNoiseRecord)
        .order_by(AlertNoiseRecord.noise_score.desc())
        .all()
    )
    return {
        "count": len(records),
        "records": [_serialize(r) for r in records],
    }


@router.get("/summary", summary="Noise suppression summary stats")
def noise_summary(db: Session = Depends(get_db)):
    """
    High-level summary: total records, how many are throttled, and the
    top-5 noisiest alert/table combinations.
    """
    total = db.query(AlertNoiseRecord).count()
    throttled = db.query(AlertNoiseRecord).filter(AlertNoiseRecord.is_throttled.is_(True)).count()
    worsening = (
        db.query(AlertNoiseRecord)
        .filter(AlertNoiseRecord.severity_trend == "worsening")
        .count()
    )
    top5 = (
        db.query(AlertNoiseRecord)
        .order_by(AlertNoiseRecord.noise_score.desc())
        .limit(5)
        .all()
    )
    return {
        "total_tracked": total,
        "currently_throttled": throttled,
        "worsening_trend": worsening,
        "top_noisy_alerts": [_serialize(r) for r in top5],
    }


@router.get("/{table_name}/{alert_type}", summary="Get noise record for a specific alert")
def get_noise_record(table_name: str, alert_type: str, db: Session = Depends(get_db)):
    """
    Retrieve the current noise score and trend for a single
    (table_name, alert_type) pair.
    """
    record = (
        db.query(AlertNoiseRecord)
        .filter(
            AlertNoiseRecord.table_name == table_name,
            AlertNoiseRecord.alert_type == alert_type,
        )
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No noise record found for table='{table_name}' alert_type='{alert_type}'",
        )
    return _serialize(record)


@router.post("/{table_name}/{alert_type}/reset", summary="Reset noise score for an alert")
def reset_noise_record(table_name: str, alert_type: str, db: Session = Depends(get_db)):
    """
    Reset the noise score for a (table_name, alert_type) pair to zero and
    clear the throttle flag.

    Use this after investigating and resolving the root cause of a noisy
    alert so it gets a clean slate.  The historical AlertLog rows are *not*
    deleted — only the computed score is zeroed.
    """
    record = (
        db.query(AlertNoiseRecord)
        .filter(
            AlertNoiseRecord.table_name == table_name,
            AlertNoiseRecord.alert_type == alert_type,
        )
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No noise record found for table='{table_name}' alert_type='{alert_type}'",
        )

    record.noise_score = 0.0
    record.count_1h = 0
    record.count_24h = 0
    record.count_7d = 0
    record.severity_trend = "stable"
    record.is_throttled = False
    record.last_calculated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": f"Noise record reset for table='{table_name}' alert_type='{alert_type}'",
        "record": _serialize(record),
    }


@router.get("/{table_name}/{alert_type}/history", summary="Recent alert history for an alert")
def alert_history(
    table_name: str,
    alert_type: str,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    Return the most recent AlertLog rows for a (table_name, alert_type) pair.
    Useful for understanding the pattern that drove the noise score up.
    """
    rows = (
        db.query(AlertLog)
        .filter(
            AlertLog.table_name == table_name,
            AlertLog.alert_type == alert_type,
        )
        .order_by(AlertLog.sent_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return {
        "table_name": table_name,
        "alert_type": alert_type,
        "count": len(rows),
        "alerts": [
            {
                "id": r.id,
                "channel": r.channel,
                "severity": r.severity,
                "sent_at": r.sent_at.isoformat(),
                "success": r.success,
                "message": r.message,
            }
            for r in rows
        ],
    }
