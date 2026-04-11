"""
ObservaKit — APScheduler for Standalone Mode
Schedules freshness polling, volume checks, schema snapshots, and quality checks.
Uses direct function calls instead of HTTP round-trips for reliability in Docker.

Job Locking
-----------
When multiple backend replicas run simultaneously (K8s, docker-compose --scale),
we use a Postgres advisory lock (pg_try_advisory_lock) to ensure each job ID is
executed by exactly one replica per interval.  On SQLite (dev/test), locking is
a no-op and jobs always run — advisory locks are Postgres-specific.

Structured Logging
------------------
Every job emits a JSON-style log line at start and end with:
  run_id, pillar, duration_ms, status
Making it trivial to parse with Loki / CloudWatch Logs Insights.
"""

import logging
import os
import time
import uuid
from contextlib import contextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

# Stable integer constant used to namespace our advisory locks
_ADVISORY_LOCK_NAMESPACE = 0x0B5E2_A0000  # "OBSERVA" in hex-ish


def _advisory_lock_key(job_id: str) -> int:
    """Map a job id string to a stable 64-bit integer for pg_try_advisory_lock."""
    return _ADVISORY_LOCK_NAMESPACE + abs(hash(job_id)) % (2**32)


@contextmanager
def _advisory_lock(db, job_id: str):
    """
    Acquire a Postgres session-level advisory lock for the duration of the job.

    Yields True if the lock was acquired (this replica should run the job),
    False if another replica already holds the lock (skip silently).

    On non-Postgres engines (SQLite in test), always yields True.
    """
    engine_name = db.get_bind().dialect.name if hasattr(db, "get_bind") else "sqlite"
    if engine_name != "postgresql":
        yield True
        return

    lock_key = _advisory_lock_key(job_id)
    try:
        result = db.execute(
            __import__("sqlalchemy").text("SELECT pg_try_advisory_lock(:key)"),
            {"key": lock_key},
        ).scalar()
        if not result:
            logger.debug(
                "Advisory lock busy for job=%s — skipping (another replica is running it)", job_id
            )
            yield False
            return
        yield True
    finally:
        try:
            db.execute(
                __import__("sqlalchemy").text("SELECT pg_advisory_unlock(:key)"),
                {"key": lock_key},
            )
        except Exception:
            pass  # connection may already be closed


def _run_job(pillar: str, job_fn, job_id: str | None = None):
    """
    Wrapper that:
      1. Emits structured start/end log lines.
      2. Acquires an advisory lock so only one replica executes per interval.
      3. Catches all exceptions so a bad connector never crashes the scheduler.
    """
    run_id = str(uuid.uuid4())[:8]
    _job_id = job_id or pillar

    from backend.models import SessionLocal

    db = SessionLocal()
    try:
        with _advisory_lock(db, _job_id) as acquired:
            if not acquired:
                return

            logger.info(
                '{"event":"job_start","run_id":"%s","pillar":"%s"}',
                run_id,
                pillar,
            )
            t0 = time.monotonic()
            try:
                job_fn(db)
                status = "ok"
            except Exception as exc:
                status = "error"
                logger.error(
                    '{"event":"job_error","run_id":"%s","pillar":"%s","error":"%s"}',
                    run_id,
                    pillar,
                    exc,
                )
            finally:
                duration_ms = int((time.monotonic() - t0) * 1000)
                logger.info(
                    '{"event":"job_end","run_id":"%s","pillar":"%s","duration_ms":%d,"status":"%s"}',
                    run_id,
                    pillar,
                    duration_ms,
                    status,
                )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Job implementations — each receives an open DB session
# ---------------------------------------------------------------------------


def _run_freshness_checks():
    """Trigger freshness checks for all configured tables."""

    def _job(db):
        from backend.routers.freshness import poll_freshness
        from connectors.base import get_warehouse_connector

        connector = get_warehouse_connector()
        try:
            poll_freshness(db=db, connector=connector)
        finally:
            connector.close()

    _run_job("freshness", _job)


def _run_volume_checks():
    """Trigger volume anomaly checks."""

    def _job(db):
        from backend.routers.checks import run_volume_checks
        from connectors.base import get_warehouse_connector

        connector = get_warehouse_connector()
        try:
            run_volume_checks(db=db, connector=connector)
        finally:
            connector.close()

    _run_job("volume", _job)


def _run_schema_checks():
    """Trigger schema drift detection."""

    def _job(db):
        from backend.routers.schema_diff import take_snapshot

        take_snapshot(db=db)

    _run_job("schema", _job)


def _run_quality_checks():
    """Trigger quality checks."""

    def _job(db):
        from backend.routers.checks import run_quality_checks

        run_quality_checks(db=db)

    _run_job("quality", _job)


def _run_finops_checks():
    """Trigger FinOps cost checks."""

    def _job(db):
        from backend.routers.finops import poll_finops_costs

        # Defaulting to 7 days for the scheduled check
        poll_finops_costs(days=7, db=db)

    _run_job("finops", _job)


def _run_late_arriving_checks():
    """Check for late-arriving data across all configured tables."""

    def _job(db):
        from backend.routers.late_arriving import poll_late_arriving
        from connectors.base import get_warehouse_connector

        connector = get_warehouse_connector()
        try:
            poll_late_arriving(db=db, connector=connector)
        finally:
            connector.close()

    _run_job("late_arriving", _job)


def _run_metadata_purge():
    """Purge metadata records older than the configured retention window."""

    def _job(db):
        from backend.routers.maintenance import run_scheduled_purge

        run_scheduled_purge(db=db)

    _run_job("maintenance", _job, job_id="metadata_purge")


def _run_dbt_watcher():
    """Poll dbt project's target/run_results.json and ingest if newer than last seen."""

    def _job(db):
        from dbt_integration.watcher import poll_dbt_artifacts

        result = poll_dbt_artifacts(db=db)
        if result["status"] == "error":
            raise RuntimeError(result.get("error", "unknown dbt watcher error"))
        logger.info("dbt watcher: ingested %d results", result.get("results_ingested", 0))

    _run_job("dbt", _job, job_id="dbt_watcher")


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------


def start_scheduler():
    """Start the APScheduler background scheduler."""
    global _scheduler

    _scheduler = BackgroundScheduler()

    freshness_interval = int(os.getenv("FRESHNESS_CHECK_INTERVAL", "15"))
    volume_interval = int(os.getenv("VOLUME_CHECK_INTERVAL", "60"))
    schema_interval = int(os.getenv("SCHEMA_CHECK_INTERVAL", "360"))
    quality_interval = int(os.getenv("QUALITY_CHECK_INTERVAL", "60"))
    finops_interval = int(os.getenv("FINOPS_CHECK_INTERVAL", "720"))  # Default 12 hours
    late_arriving_interval = int(os.getenv("LATE_ARRIVING_CHECK_INTERVAL", "30"))
    maintenance_interval = int(os.getenv("MAINTENANCE_PURGE_INTERVAL", "1440"))  # Default 24 hours

    _scheduler.add_job(
        _run_freshness_checks,
        trigger=IntervalTrigger(minutes=freshness_interval),
        id="freshness_check",
        name="Freshness Check",
        replace_existing=True,
    )

    _scheduler.add_job(
        _run_volume_checks,
        trigger=IntervalTrigger(minutes=volume_interval),
        id="volume_check",
        name="Volume Check",
        replace_existing=True,
    )

    _scheduler.add_job(
        _run_schema_checks,
        trigger=IntervalTrigger(minutes=schema_interval),
        id="schema_check",
        name="Schema Drift Check",
        replace_existing=True,
    )

    _scheduler.add_job(
        _run_quality_checks,
        trigger=IntervalTrigger(minutes=quality_interval),
        id="quality_check",
        name="Quality Check",
        replace_existing=True,
    )

    _scheduler.add_job(
        _run_finops_checks,
        trigger=IntervalTrigger(minutes=finops_interval),
        id="finops_check",
        name="FinOps Check",
        replace_existing=True,
    )

    # ---- Optional late-arriving data checks ----
    try:
        from config.loader import load_config

        la_cfg = load_config("config/kit.yml").get("late_arriving", {})
        if la_cfg.get("enabled", False):
            _scheduler.add_job(
                _run_late_arriving_checks,
                trigger=IntervalTrigger(minutes=late_arriving_interval),
                id="late_arriving_check",
                name="Late-Arriving Data Check",
                replace_existing=True,
            )
            logger.info("Late-arriving data detector enabled (polling every %dmin)", late_arriving_interval)
    except Exception as e:
        logger.warning("Could not configure late-arriving check: %s", e)

    # ---- Optional scheduled metadata purge ----
    try:
        from config.loader import load_config

        maint_cfg = load_config("config/kit.yml").get("maintenance", {})
        if maint_cfg.get("enabled", False):
            _scheduler.add_job(
                _run_metadata_purge,
                trigger=IntervalTrigger(minutes=maintenance_interval),
                id="metadata_purge",
                name="Metadata Purge",
                replace_existing=True,
            )
            logger.info(
                "Metadata purge enabled (every %dmin, retention=%d days)",
                maintenance_interval,
                int(maint_cfg.get("retention_days", 90)),
            )
    except Exception as e:
        logger.warning("Could not configure metadata purge: %s", e)

    # ---- Optional dbt artifact watcher ----
    try:
        from config.loader import load_config

        dbt_cfg = load_config("config/kit.yml").get("dbt", {})
        if dbt_cfg.get("enabled", False) and dbt_cfg.get("auto_parse_on_run", True):
            dbt_poll_interval = int(dbt_cfg.get("poll_interval_minutes", 5))
            _scheduler.add_job(
                _run_dbt_watcher,
                trigger=IntervalTrigger(minutes=dbt_poll_interval),
                id="dbt_watcher",
                name="dbt Artifact Watcher",
                replace_existing=True,
            )
            logger.info("dbt artifact watcher enabled (polling every %dmin)", dbt_poll_interval)
    except Exception as e:
        logger.warning("Could not configure dbt watcher: %s", e)

    _scheduler.start()
    logger.info(
        "Scheduler started — freshness=%dmin, volume=%dmin, schema=%dmin, "
        "quality=%dmin, finops=%dmin, late_arriving=%dmin, maintenance=%dmin",
        freshness_interval,
        volume_interval,
        schema_interval,
        quality_interval,
        finops_interval,
        late_arriving_interval,
        maintenance_interval,
    )


def shutdown_scheduler():
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")


def get_scheduler_jobs() -> list[dict]:
    """
    Return a list of all scheduled jobs with their next run time and last status.
    Used by GET /scheduler/jobs.
    """
    if not _scheduler:
        return []

    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
                "trigger": str(job.trigger),
            }
        )
    return jobs
