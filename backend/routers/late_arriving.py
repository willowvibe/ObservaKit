"""
ObservaKit — Late-Arriving Data Detector (v0.2.0)

Tracks whether data arrives at a table within an expected time window.

This is intentionally distinct from the Freshness monitor:

  Freshness     — "How old is the newest record in this table?"
                  (measures staleness of the newest row relative to now)

  Late-Arriving — "Did the expected batch/stream arrive on time?"
                  (measures whether rows arrived in the window between
                   expected_arrival_time and expected_arrival_time + grace_period)

Example
-------
  The `orders` table receives a nightly ETL batch.  The pipeline should land
  rows with an `inserted_at` timestamp between 01:45 and 02:15 UTC each night.

  If we check at 03:00 UTC and find zero rows with `inserted_at` in that window,
  we fire a LATE_DATA alert — even if the table itself has a very recent
  `updated_at` timestamp from a previous successful batch.

Configuration (kit.yml)
-----------------------
  late_arriving:
    enabled: true
    schedule_minutes: 30
    tables:
      - table: public.orders
        timestamp_column: inserted_at          # column holding ingestion time
        expected_arrival_cron: "0 2 * * *"    # daily at 02:00 UTC
        grace_period_minutes: 60              # fire alert if no rows by 03:00 UTC
        min_rows_expected: 1                  # at least this many rows must arrive
        alert: slack

API Endpoints
-------------
  GET  /late-arriving/             — list recent late-arriving records
  GET  /late-arriving/{table}      — last result for a specific table
  POST /late-arriving/check        — trigger a manual check (auth required)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from alerts.base import dispatch_alert
from backend.auth import verify_api_key
from backend.models import LateArrivingRecord, get_db
from config.loader import load_config

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@router.get("/")
def list_late_arriving(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    List recent late-arriving data check results.

    Query params:
      status — filter by 'ok' | 'late' | 'missing'
      limit  — max records returned (default 50)
    """
    query = db.query(LateArrivingRecord).order_by(LateArrivingRecord.checked_at.desc())
    if status:
        query = query.filter(LateArrivingRecord.status == status)
    records = query.limit(limit).all()

    return [
        {
            "table": r.table_name,
            "expected_at": r.expected_at.isoformat(),
            "checked_at": r.checked_at.isoformat(),
            "rows_arrived": r.rows_arrived,
            "delay_seconds": r.delay_seconds,
            "status": r.status,
        }
        for r in records
    ]


@router.get("/{table_name}")
def get_late_arriving(table_name: str, db: Session = Depends(get_db)):
    """Get the most recent late-arriving check result for a specific table."""
    record = (
        db.query(LateArrivingRecord)
        .filter(LateArrivingRecord.table_name == table_name)
        .order_by(LateArrivingRecord.checked_at.desc())
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=404, detail=f"No late-arriving data for table '{table_name}'"
        )
    return {
        "table": record.table_name,
        "expected_at": record.expected_at.isoformat(),
        "checked_at": record.checked_at.isoformat(),
        "rows_arrived": record.rows_arrived,
        "delay_seconds": record.delay_seconds,
        "status": record.status,
    }


@router.post("/check", dependencies=[Depends(verify_api_key)])
def check_late_arriving(db: Session = Depends(get_db), connector=None):
    """
    Trigger a late-arriving data check for all configured tables.

    For each table, determines whether the expected data window has been
    populated with at least min_rows_expected rows.  If the deadline
    (expected_arrival_cron + grace_period_minutes) has passed and insufficient
    rows arrived, a LATE_DATA alert is fired.
    """
    try:
        config = load_config("config/kit.yml")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/kit.yml not found")

    late_cfg = config.get("late_arriving", {})
    if not late_cfg.get("enabled", False):
        return {"message": "Late-arriving data detection is disabled"}

    tables = late_cfg.get("tables", [])
    results = []

    for table_cfg in tables:
        if not table_cfg.get("enabled", True):
            logger.debug(
                "Skipping late-arriving check for %s (enabled: false)", table_cfg.get("table")
            )
            continue

        table_name = table_cfg["table"]
        ts_col = table_cfg["timestamp_column"]
        cron_expr = table_cfg.get("expected_arrival_cron", "0 2 * * *")
        grace_minutes = int(table_cfg.get("grace_period_minutes", 60))
        min_rows = int(table_cfg.get("min_rows_expected", 1))

        try:
            from connectors.base import get_warehouse_connector

            _connector = connector or get_warehouse_connector()

            now = datetime.now(timezone.utc)
            expected_at = _last_expected_arrival(cron_expr, now)
            deadline = expected_at + timedelta(minutes=grace_minutes)

            # Query rows that arrived in the expected ingestion window
            # (from expected_at back to the previous expected window)
            prev_expected_at = _prev_expected_arrival(cron_expr, expected_at)
            rows_arrived, delay_seconds, status = _evaluate_arrival(
                table_name,
                ts_col,
                prev_expected_at,
                expected_at,
                deadline,
                min_rows,
                now,
                _connector,
            )

            record = LateArrivingRecord(
                table_name=table_name,
                expected_at=expected_at,
                checked_at=now,
                rows_arrived=rows_arrived,
                delay_seconds=delay_seconds,
                status=status,
            )
            db.add(record)

            result = {
                "table": table_name,
                "expected_at": expected_at.isoformat(),
                "deadline": deadline.isoformat(),
                "rows_arrived": rows_arrived,
                "delay_seconds": delay_seconds,
                "status": status,
            }
            results.append(result)

            if status in ("late", "missing"):
                _trigger_late_alert(table_name, expected_at, deadline, rows_arrived, status, db)

        except Exception as exc:
            logger.error("Late-arriving check failed for %s: %s", table_name, exc)
            results.append({"table": table_name, "error": str(exc)})

    db.commit()
    return {"checked": len(results), "results": results}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _evaluate_arrival(
    table_name: str,
    ts_col: str,
    window_start: datetime,
    window_end: datetime,
    deadline: datetime,
    min_rows: int,
    now: datetime,
    connector,
) -> tuple[Optional[int], Optional[float], str]:
    """
    Count rows whose ts_col falls in [window_start, window_end] and classify
    the arrival status.

    Returns (rows_arrived, delay_seconds, status).

    Status values:
      ok      — enough rows arrived before the deadline
      late    — enough rows eventually arrived but after the deadline
      missing — deadline has passed and rows are still insufficient
    """
    from backend.security import is_safe_identifier, is_safe_table_reference

    if not is_safe_table_reference(table_name) or not is_safe_identifier(ts_col):
        raise ValueError(f"Unsafe table/column identifier: {table_name}.{ts_col}")

    rows = connector.execute_query(
        f"SELECT COUNT(*) AS cnt, MAX({ts_col}) AS last_ts FROM {table_name} "
        f"WHERE {ts_col} > :window_start AND {ts_col} <= :window_end",
        {"window_start": window_start, "window_end": window_end},
    )

    rows_arrived: Optional[int] = None
    last_ts: Optional[datetime] = None
    if rows:
        rows_arrived = int(rows[0].get("cnt") or 0)
        last_ts_raw = rows[0].get("last_ts")
        if last_ts_raw:
            if isinstance(last_ts_raw, datetime):
                last_ts = last_ts_raw if last_ts_raw.tzinfo else last_ts_raw.replace(tzinfo=timezone.utc)
            else:
                last_ts = datetime.fromisoformat(str(last_ts_raw)).replace(tzinfo=timezone.utc)

    sufficient = rows_arrived is not None and rows_arrived >= min_rows

    if sufficient:
        if last_ts and last_ts > deadline:
            delay_seconds = (last_ts - deadline).total_seconds()
            return rows_arrived, delay_seconds, "late"
        return rows_arrived, None, "ok"

    # Not enough rows yet
    if now >= deadline:
        return rows_arrived or 0, (now - deadline).total_seconds(), "missing"

    # Deadline hasn't passed — still within grace period
    return rows_arrived or 0, None, "ok"


def _last_expected_arrival(cron_expr: str, now: datetime) -> datetime:
    """
    Parse a cron expression and return the most recent scheduled time before now.

    Uses the `croniter` library if available; falls back to a simple daily
    heuristic (midnight UTC) when croniter is not installed.
    """
    try:
        from croniter import croniter

        it = croniter(cron_expr, now)
        return it.get_prev(datetime).replace(tzinfo=timezone.utc)
    except ImportError:
        logger.debug(
            "croniter not installed — using midnight UTC as the expected arrival time. "
            "Install croniter for cron expression support: pip install croniter"
        )
        return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _prev_expected_arrival(cron_expr: str, current_expected: datetime) -> datetime:
    """Return the scheduled time one period before current_expected."""
    try:
        from croniter import croniter

        # Step back one period from current_expected
        it = croniter(cron_expr, current_expected - timedelta(seconds=1))
        return it.get_prev(datetime).replace(tzinfo=timezone.utc)
    except ImportError:
        return current_expected - timedelta(days=1)


def _trigger_late_alert(
    table: str,
    expected_at: datetime,
    deadline: datetime,
    rows_arrived: Optional[int],
    status: str,
    db: Session,
):
    """Dispatch a late-arriving data alert."""
    if status == "missing":
        emoji = "🔴"
        desc = "No data arrived"
    else:
        emoji = "🟡"
        desc = "Data arrived after deadline"

    message = (
        f"Late-Arriving Data: {table}\n"
        f"  Status: {status.upper()}\n"
        f"  Expected by: {deadline.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"  Rows arrived: {rows_arrived if rows_arrived is not None else 'unknown'}\n"
        f"  Detected at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )

    dispatch_alert(
        alert_type="late_arriving",
        table_name=table,
        subject=f"{emoji} Late Data: {table} — {desc}",
        message=message,
        db=db,
        severity="fail" if status == "missing" else "warn",
    )


# ---------------------------------------------------------------------------
# Scheduler-callable entry point
# ---------------------------------------------------------------------------


def poll_late_arriving(db: Session, connector=None):
    """
    Scheduler entry point — called from backend/scheduler.py.
    Re-uses the same logic as the HTTP endpoint without going through HTTP.
    """
    try:
        config = load_config("config/kit.yml")
    except FileNotFoundError:
        logger.warning("config/kit.yml not found — skipping late-arriving check")
        return

    late_cfg = config.get("late_arriving", {})
    if not late_cfg.get("enabled", False):
        return

    # Delegate to the router function with injected DB/connector
    check_late_arriving(db=db, connector=connector)
