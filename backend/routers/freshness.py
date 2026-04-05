"""
ObservaKit — Freshness Monitor Router
Polls warehouse tables for freshness and emits Prometheus metrics.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import Gauge
from sqlalchemy.orm import Session

from alerts.base import dispatch_alert
from backend.auth import verify_api_key
from backend.models import FreshnessRecord, get_db
from config.loader import load_config

logger = logging.getLogger(__name__)

router = APIRouter()

# Prometheus gauge for freshness lag
freshness_lag_gauge = Gauge(
    "data_freshness_lag_seconds",
    "Seconds since the table was last updated",
    ["table"],
)


@router.get("/{table_name}")
def get_freshness(table_name: str, db: Session = Depends(get_db)):
    """Get the most recent freshness record for a table."""
    record = (
        db.query(FreshnessRecord)
        .filter(FreshnessRecord.table_name == table_name)
        .order_by(FreshnessRecord.checked_at.desc())
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail=f"No freshness data for table '{table_name}'")

    return {
        "table": record.table_name,
        "timestamp_column": record.timestamp_column,
        "last_updated_at": record.last_updated_at.isoformat() if record.last_updated_at else None,
        "lag_seconds": record.lag_seconds,
        "status": record.status,
        "checked_at": record.checked_at.isoformat(),
    }


@router.get("/")
def list_freshness(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List recent freshness records, optionally filtered by status."""
    query = db.query(FreshnessRecord).order_by(FreshnessRecord.checked_at.desc())
    if status:
        query = query.filter(FreshnessRecord.status == status)
    records = query.limit(limit).all()

    return [
        {
            "table": r.table_name,
            "lag_seconds": r.lag_seconds,
            "status": r.status,
            "checked_at": r.checked_at.isoformat(),
        }
        for r in records
    ]


@router.post("/poll", dependencies=[Depends(verify_api_key)])
def poll_freshness(db: Session = Depends(get_db), connector=None):
    """
    Trigger a freshness check for all configured tables.
    Reads config from kit.yml, queries the warehouse, and stores results.
    Accepts an optional pre-built connector for connection reuse from scheduler.
    """

    try:
        config = load_config("config/kit.yml")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/kit.yml not found")

    freshness_config = config.get("freshness", {})
    if not freshness_config.get("enabled", False):
        return {"message": "Freshness monitoring is disabled"}

    tables = freshness_config.get("tables", [])
    results = []

    for table_cfg in tables:
        # Per-check enabled flag — skip without error if explicitly disabled
        if not table_cfg.get("enabled", True):
            logger.debug("Skipping freshness check for %s (enabled: false)", table_cfg.get("table"))
            continue

        table_name = table_cfg["table"]
        ts_col = table_cfg["timestamp_column"]
        warn_after = _parse_duration(table_cfg.get("warn_after", "1h"))
        fail_after = _parse_duration(table_cfg.get("fail_after", "2h"))

        # Query the warehouse for freshness
        try:
            from connectors.base import get_warehouse_connector

            _connector = connector or get_warehouse_connector()
            last_updated = _connector.get_max_timestamp(table_name, ts_col)

            now = datetime.now(timezone.utc)
            lag_seconds = (now - last_updated).total_seconds() if last_updated else None

            # Determine status
            if lag_seconds is None:
                status = "fail"
            elif lag_seconds > fail_after:
                status = "fail"
            elif lag_seconds > warn_after:
                status = "warn"
            else:
                status = "ok"

            # Store record
            record = FreshnessRecord(
                table_name=table_name,
                timestamp_column=ts_col,
                last_updated_at=last_updated,
                lag_seconds=lag_seconds,
                status=status,
            )
            db.add(record)

            # Update Prometheus gauge
            if lag_seconds is not None:
                freshness_lag_gauge.labels(table=table_name).set(lag_seconds)

            results.append({"table": table_name, "lag_seconds": lag_seconds, "status": status})

            # Trigger alert if needed (with deduplication)
            if status in ("warn", "fail"):
                _trigger_alert(table_name, lag_seconds, status, table_cfg.get("alert", "slack"), db)

        except Exception as e:
            logger.error(f"Freshness check failed for {table_name}: {e}")
            results.append({"table": table_name, "error": str(e)})

    db.commit()
    return {"checked": len(results), "results": results}


def _parse_duration(duration_str: str) -> float:
    """Parse a duration string like '1h', '30m', '2h' into seconds."""
    if not duration_str:
        raise ValueError("duration_str must not be empty")
    duration_str = duration_str.strip().lower()
    try:
        if duration_str.endswith("h"):
            return float(duration_str[:-1]) * 3600
        elif duration_str.endswith("m"):
            return float(duration_str[:-1]) * 60
        elif duration_str.endswith("s"):
            return float(duration_str[:-1])
        elif duration_str.endswith("d"):
            return float(duration_str[:-1]) * 86400
        return float(duration_str)
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid duration string '{duration_str}': {e}") from e


def _trigger_alert(table: str, lag_seconds: float, status: str, channel: str, db: Session):
    """Dispatch a freshness alert."""
    lag_str = (
        f"{lag_seconds / 3600:.1f} hours" if lag_seconds is not None else "unknown (no data found)"
    )
    message = (
        f"Freshness Alert: {table}\n"
        f"  Lag: {lag_str}\n"
        f"  Status: {status.upper()}\n"
        f"  Detected at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )

    dispatch_alert(
        alert_type="freshness",
        table_name=table,
        subject=f"{'🔴' if status == 'fail' else '🟡'} Freshness: {table} is {status}",
        message=message,
        db=db,
        severity=status,
    )
