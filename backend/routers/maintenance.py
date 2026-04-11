"""
ObservaKit — Scheduled Metadata Purge (v0.2.0)

Automatically deletes metadata records older than a configurable retention
window, preventing the metadata Postgres database from growing unboundedly.

What gets purged
----------------
  Table                       Default retention
  ──────────────────────────  ─────────────────
  freshness_records           90 days
  volume_records              90 days
  check_results               90 days
  schema_snapshots            180 days
  schema_diffs                90 days
  alert_logs                  30 days
  alert_noise_records         30 days  (resets noise state — conservative)
  column_profiles             90 days
  distribution_snapshots      180 days
  distribution_drifts         90 days
  contract_validation_results 90 days
  backfill_events             90 days
  late_arriving_records       90 days
  maintenance_logs            365 days  (keep purge history for a year)

Configuration (kit.yml)
-----------------------
  maintenance:
    enabled: true
    schedule_hours: 24            # run daily
    retention_days: 90            # default retention for all tables
    overrides:                    # per-table overrides (optional)
      schema_snapshots: 180
      distribution_snapshots: 180
      alert_logs: 30
      maintenance_logs: 365

API Endpoints
-------------
  GET  /maintenance/status        — last purge run info
  POST /maintenance/purge         — trigger a manual purge (auth required)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.auth import verify_api_key
from backend.models import (
    AlertLog,
    AlertNoiseRecord,
    BackfillEvent,
    CheckResult,
    ColumnProfile,
    ContractValidationResult,
    DistributionDrift,
    DistributionSnapshot,
    FreshnessRecord,
    LateArrivingRecord,
    MaintenanceLog,
    SchemaDiff,
    SchemaSnapshot,
    VolumeRecord,
    get_db,
)
from config.loader import load_config

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Purgeable tables: (SQLAlchemy model class, datetime column name)
# ---------------------------------------------------------------------------
_PURGEABLE_TABLES: list[tuple] = [
    (FreshnessRecord, "checked_at"),
    (VolumeRecord, "recorded_at"),
    (CheckResult, "executed_at"),
    (SchemaSnapshot, "snapshot_at"),
    (SchemaDiff, "detected_at"),
    (AlertLog, "sent_at"),
    (AlertNoiseRecord, "last_calculated_at"),
    (ColumnProfile, "profiled_at"),
    (DistributionSnapshot, "snapshotted_at"),
    (DistributionDrift, "detected_at"),
    (ContractValidationResult, "validated_at"),
    (BackfillEvent, "detected_at"),
    (LateArrivingRecord, "checked_at"),
    (MaintenanceLog, "started_at"),
]

_DEFAULT_RETENTION: dict[str, int] = {
    "freshness_records": 90,
    "volume_records": 90,
    "check_results": 90,
    "schema_snapshots": 180,
    "schema_diffs": 90,
    "alert_logs": 30,
    "alert_noise_records": 30,
    "column_profiles": 90,
    "distribution_snapshots": 180,
    "distribution_drifts": 90,
    "contract_validation_results": 90,
    "backfill_events": 90,
    "late_arriving_records": 90,
    "maintenance_logs": 365,
}


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@router.get("/status")
def maintenance_status(db: Session = Depends(get_db)):
    """
    Return the most recent purge run details and the configured retention policy.
    """
    try:
        config = load_config("config/kit.yml")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/kit.yml not found")

    maint_cfg = config.get("maintenance", {})
    retention_days = int(maint_cfg.get("retention_days", 90))
    overrides = maint_cfg.get("overrides", {})

    last_log = (
        db.query(MaintenanceLog)
        .order_by(MaintenanceLog.started_at.desc())
        .first()
    )

    policy = {
        table_name: overrides.get(table_name, _DEFAULT_RETENTION.get(table_name, retention_days))
        for table_name in _DEFAULT_RETENTION
    }

    return {
        "enabled": maint_cfg.get("enabled", False),
        "schedule_hours": maint_cfg.get("schedule_hours", 24),
        "retention_policy": policy,
        "last_run": {
            "started_at": last_log.started_at.isoformat() if last_log else None,
            "finished_at": last_log.finished_at.isoformat() if last_log and last_log.finished_at else None,
            "status": last_log.status if last_log else None,
            "deleted_counts": last_log.deleted_counts if last_log else None,
            "error": last_log.error if last_log else None,
        },
    }


@router.post("/purge", dependencies=[Depends(verify_api_key)])
def run_purge(
    retention_days: Optional[int] = None,
    dry_run: bool = False,
    db: Session = Depends(get_db),
):
    """
    Trigger a metadata purge run.

    Parameters:
      retention_days — override the configured retention for this run only
      dry_run        — count what would be deleted without actually deleting

    Returns a summary of deleted (or would-be-deleted) record counts per table.
    """
    try:
        config = load_config("config/kit.yml")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/kit.yml not found")

    maint_cfg = config.get("maintenance", {})
    effective_retention = retention_days or int(maint_cfg.get("retention_days", 90))
    overrides = maint_cfg.get("overrides", {})

    now = datetime.now(timezone.utc)
    log = MaintenanceLog(
        retention_days=effective_retention,
        started_at=now,
        status="running",
        deleted_counts={},
    )
    if not dry_run:
        db.add(log)
        db.flush()

    deleted_counts: dict[str, int] = {}
    error_msg: Optional[str] = None

    try:
        for model_cls, ts_col_name in _PURGEABLE_TABLES:
            table_name = model_cls.__tablename__
            days = overrides.get(table_name, _DEFAULT_RETENTION.get(table_name, effective_retention))
            cutoff = now - timedelta(days=days)

            ts_col = getattr(model_cls, ts_col_name, None)
            if ts_col is None:
                logger.warning("Model %s has no column %s — skipping purge", table_name, ts_col_name)
                continue

            query = db.query(model_cls).filter(ts_col < cutoff)
            count = query.count()

            if not dry_run and count > 0:
                query.delete(synchronize_session=False)
                logger.info("Purged %d rows from %s (cutoff=%s)", count, table_name, cutoff.date())

            deleted_counts[table_name] = count

        if not dry_run:
            finished_at = datetime.now(timezone.utc)
            log.deleted_counts = deleted_counts
            log.finished_at = finished_at
            log.status = "ok"
            db.commit()

    except Exception as exc:
        error_msg = str(exc)
        logger.error("Metadata purge failed: %s", exc)
        if not dry_run:
            log.status = "error"
            log.error = error_msg
            log.finished_at = datetime.now(timezone.utc)
            try:
                db.commit()
            except Exception:
                db.rollback()

    total_deleted = sum(deleted_counts.values())
    return {
        "dry_run": dry_run,
        "retention_days": effective_retention,
        "started_at": now.isoformat(),
        "total_records_deleted": total_deleted,
        "deleted_counts": deleted_counts,
        "status": "ok" if not error_msg else "error",
        "error": error_msg,
    }


# ---------------------------------------------------------------------------
# Scheduler-callable entry point
# ---------------------------------------------------------------------------


def run_scheduled_purge(db: Session):
    """
    Scheduler entry point — called from backend/scheduler.py.

    Reads config and executes a purge, skipping if maintenance is disabled.
    """
    try:
        config = load_config("config/kit.yml")
    except FileNotFoundError:
        logger.warning("config/kit.yml not found — skipping metadata purge")
        return

    maint_cfg = config.get("maintenance", {})
    if not maint_cfg.get("enabled", False):
        return

    retention_days = int(maint_cfg.get("retention_days", 90))
    run_purge(retention_days=retention_days, dry_run=False, db=db)
