"""
ObservaKit — Data Observability Starter Kit
FastAPI Backend Service
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from alembic import command
from backend.auth import verify_api_key
from backend.routers import checks, finops, freshness, profiling, schema_diff, suppressions, webhooks
from backend.scheduler import shutdown_scheduler, start_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — run migrations and start scheduler."""
    # Run Alembic migrations to ensure schema is up to date
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied successfully.")
    except Exception:
        logger.exception("Failed to run Alembic migrations — falling back to create_all.")
        from backend.models import Base, engine
        Base.metadata.create_all(bind=engine)
    logger.info(
        "\n"
        "  ╔═══════════════════════════════════════╗\n"
        "  ║  🔭 ObservaKit v%s                    ║\n"
        "  ║  Data Observability Starter Kit       ║\n"
        "  ║  Built by WillowVibe DataSynapse      ║\n"
        "  ║  https://www.willowvibe.com           ║\n"
        "  ╚═══════════════════════════════════════╝",
        app.version,
    )
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="ObservaKit",
    description=(
        "Data Observability Starter Kit — self-hosted observability layer "
        "providing Freshness, Volume, Quality, Schema Drift, and Pipeline Health monitoring."
    ),
    version="0.1.7",
    lifespan=lifespan,
)

# CORS — allow Grafana frontend and local dev
# Note: explicit origins required when allow_credentials=True (CORS spec)
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Prometheus /metrics endpoint ----
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# ---- Routers ----
app.include_router(
    freshness.router,
    prefix="/freshness",
    tags=["Freshness"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    checks.router,
    prefix="/checks",
    tags=["Quality Checks"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    schema_diff.router,
    prefix="/schema",
    tags=["Schema Drift"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    finops.router,
    prefix="/finops",
    tags=["FinOps"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(profiling.router, prefix="/profiling", tags=["Column Profiling"], dependencies=[Depends(verify_api_key)])
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"], dependencies=[Depends(verify_api_key)])
app.include_router(suppressions.router, prefix="/suppress", tags=["Suppressions"], dependencies=[Depends(verify_api_key)])


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "ObservaKit",
        "version": "0.1.7",
        "status": "running",
        "docs": "/docs",
        "maintained_by": "WillowVibe DataSynapse",
        "website": "https://www.willowvibe.com",
        "source": "https://github.com/willowvibe/ObservaKit",
    }


@app.get("/status", tags=["Health"])
async def get_status():
    """
    Single-call health summary across all observability pillars.
    Returns stale table count, schema drifts, quality pass rate, volume anomalies,
    and active suppressions. Suitable for badges, Slack digests, and embedded widgets.
    """
    from datetime import timedelta
    from sqlalchemy import func as sqlfunc
    from backend.models import (
        FreshnessRecord, VolumeRecord, CheckResult,
        SchemaDiff, CheckSuppression, SessionLocal
    )

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff_24h = now - timedelta(hours=24)

        # Freshness: count tables with status != ok in last 24h
        stale_count = db.query(FreshnessRecord).filter(
            FreshnessRecord.checked_at >= cutoff_24h,
            FreshnessRecord.status != "ok"
        ).count()

        # Volume: anomalies in last 24h
        volume_anomalies = db.query(VolumeRecord).filter(
            VolumeRecord.recorded_at >= cutoff_24h,
            VolumeRecord.is_anomaly == True  # noqa: E712
        ).count()

        # Quality: pass rate in last 24h
        total_checks = db.query(CheckResult).filter(
            CheckResult.executed_at >= cutoff_24h
        ).count()
        passed_checks = db.query(CheckResult).filter(
            CheckResult.executed_at >= cutoff_24h,
            CheckResult.passed == True  # noqa: E712
        ).count()
        quality_pass_rate = round((passed_checks / total_checks) * 100, 1) if total_checks > 0 else None

        # Schema: drift events in last 24h
        schema_drifts = db.query(SchemaDiff).filter(
            SchemaDiff.detected_at >= cutoff_24h
        ).count()

        # Active suppressions
        active_suppressions = db.query(CheckSuppression).filter(
            CheckSuppression.suppressed_until >= now
        ).count()

        # Last run timestamps per pillar
        last_freshness = db.query(sqlfunc.max(FreshnessRecord.checked_at)).scalar()
        last_volume = db.query(sqlfunc.max(VolumeRecord.recorded_at)).scalar()
        last_quality = db.query(sqlfunc.max(CheckResult.executed_at)).scalar()
        last_schema = db.query(sqlfunc.max(SchemaDiff.detected_at)).scalar()

        return {
            "generated_at": now.isoformat(),
            "window_hours": 24,
            "freshness": {
                "stale_tables": stale_count,
                "last_checked": last_freshness.isoformat() if last_freshness else None,
            },
            "volume": {
                "anomalies": volume_anomalies,
                "last_checked": last_volume.isoformat() if last_volume else None,
            },
            "quality": {
                "total_checks": total_checks,
                "passed_checks": passed_checks,
                "pass_rate_pct": quality_pass_rate,
                "last_checked": last_quality.isoformat() if last_quality else None,
            },
            "schema": {
                "drift_events": schema_drifts,
                "last_detected": last_schema.isoformat() if last_schema else None,
            },
            "suppressions": {
                "active": active_suppressions,
            },
        }
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Run ObservaKit Backend")
    parser.add_argument("--lite", action="store_true", help="Run in lite mode with SQLite")
    args = parser.parse_args()

    if args.lite:
        logger.info("Starting in LITE mode...")
        os.environ["METADATA_DB_TYPE"] = "sqlite"
        # In lite mode, we might want to disable some heavyweight components
        os.environ["OTEL_ENABLED"] = "false"
        os.environ["PROMETHEUS_ENABLED"] = "false"

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
