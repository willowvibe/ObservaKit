"""
ObservaKit — APScheduler for Standalone Mode
Schedules freshness polling, volume checks, schema snapshots, and quality checks.
Uses direct function calls instead of HTTP round-trips for reliability in Docker.
"""

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_freshness_checks():
    """Trigger freshness checks for all configured tables."""
    logger.info("Scheduled freshness check triggered")
    try:
        from backend.models import SessionLocal
        from backend.routers.freshness import poll_freshness
        from connectors.base import get_warehouse_connector

        connector = get_warehouse_connector()
        db = SessionLocal()
        try:
            poll_freshness(db=db, connector=connector)
        finally:
            db.close()
            connector.close()
    except Exception as e:
        logger.error(f"Freshness check failed: {e}")


def _run_volume_checks():
    """Trigger volume anomaly checks."""
    logger.info("Scheduled volume check triggered")
    try:
        from backend.models import SessionLocal
        from backend.routers.checks import run_volume_checks
        from connectors.base import get_warehouse_connector

        connector = get_warehouse_connector()
        db = SessionLocal()
        try:
            run_volume_checks(db=db, connector=connector)
        finally:
            db.close()
            connector.close()
    except Exception as e:
        logger.error(f"Volume check failed: {e}")


def _run_schema_checks():
    """Trigger schema drift detection."""
    logger.info("Scheduled schema check triggered")
    try:
        from backend.models import SessionLocal
        from backend.routers.schema_diff import take_snapshot

        db = SessionLocal()
        try:
            take_snapshot(db=db)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Schema check failed: {e}")


def _run_quality_checks():
    """Trigger quality checks."""
    logger.info("Scheduled quality check triggered")
    try:
        from backend.models import SessionLocal
        from backend.routers.checks import run_quality_checks

        db = SessionLocal()
        try:
            run_quality_checks(db=db)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Quality check failed: {e}")


def _run_finops_checks():
    """Trigger FinOps cost checks."""
    logger.info("Scheduled FinOps check triggered")
    try:
        from backend.models import SessionLocal
        from backend.routers.finops import poll_finops_costs

        db = SessionLocal()
        try:
            # Defaulting to 7 days for the scheduled check
            poll_finops_costs(days=7, db=db)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"FinOps check failed: {e}")


def _run_dbt_watcher():
    """Poll dbt project's target/run_results.json and ingest if newer than last seen."""
    try:
        from backend.models import SessionLocal
        from dbt_integration.watcher import poll_dbt_artifacts

        db = SessionLocal()
        try:
            result = poll_dbt_artifacts(db=db)
            if result["status"] == "error":
                logger.error(f"dbt watcher error: {result.get('error')}")
            elif result["status"] == "ok":
                logger.info(f"dbt watcher: ingested {result.get('results_ingested', 0)} results")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"dbt watcher failed: {e}")


def start_scheduler():
    """Start the APScheduler background scheduler."""
    global _scheduler

    _scheduler = BackgroundScheduler()

    freshness_interval = int(os.getenv("FRESHNESS_CHECK_INTERVAL", "15"))
    volume_interval = int(os.getenv("VOLUME_CHECK_INTERVAL", "60"))
    schema_interval = int(os.getenv("SCHEMA_CHECK_INTERVAL", "360"))
    quality_interval = int(os.getenv("QUALITY_CHECK_INTERVAL", "60"))
    finops_interval = int(os.getenv("FINOPS_CHECK_INTERVAL", "720")) # Default 12 hours

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
        logger.warning(f"Could not configure dbt watcher: {e}")

    _scheduler.start()
    logger.info(
        "Scheduler started — freshness=%dmin, volume=%dmin, schema=%dmin, quality=%dmin, finops=%dmin",
        freshness_interval,
        volume_interval,
        schema_interval,
        quality_interval,
        finops_interval,
    )


def shutdown_scheduler():
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
