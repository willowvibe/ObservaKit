"""
ObservaKit — Data Observability Starter Kit
FastAPI Backend Service
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from alembic import command
from backend.auth import verify_api_key
from backend.routers import (
    alert_noise,
    checks,
    contracts,
    distribution,
    finops,
    freshness,
    profiling,
    schema_diff,
    suppressions,
    webhooks,
)
from backend.scheduler import get_scheduler_jobs, shutdown_scheduler, start_scheduler

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
    version="0.1.13",
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
app.include_router(
    profiling.router,
    prefix="/profiling",
    tags=["Column Profiling"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    webhooks.router, prefix="/webhooks", tags=["Webhooks"], dependencies=[Depends(verify_api_key)]
)
app.include_router(
    suppressions.router,
    prefix="/suppress",
    tags=["Suppressions"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    distribution.router,
    prefix="/distribution",
    tags=["Distribution Drift"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    contracts.router,
    prefix="/contracts",
    tags=["Data Contracts"],
    dependencies=[Depends(verify_api_key)],
)
app.include_router(
    alert_noise.router,
    prefix="/alerts/noise",
    tags=["Alert Noise Suppression"],
    dependencies=[Depends(verify_api_key)],
)

# ---- Embedded React Dashboard ----
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_STATIC_DIR), html=True), name="ui")

    @app.get("/ui/{full_path:path}", include_in_schema=False)
    async def serve_ui(full_path: str):
        """SPA fallback — serve index.html for any /ui/* path not matched by static files."""
        index = _STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"detail": "Dashboard not built. Run: make ui-build"}


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "ObservaKit",
        "version": "0.1.13",
        "status": "running",
        "docs": "/docs",
        "maintained_by": "WillowVibe DataSynapse",
        "website": "https://www.willowvibe.com",
        "source": "https://github.com/willowvibe/ObservaKit",
    }


@app.get("/healthz", tags=["Health"], include_in_schema=True)
async def healthz():
    """
    Kubernetes / Docker liveness & readiness probe endpoint.

    Returns HTTP 200 when the service is up and the metadata database is reachable.
    Returns HTTP 503 if the database is unreachable so that Kubernetes can restart
    the pod or remove it from the load-balancer.

    Usage in Kubernetes:
      livenessProbe:
        httpGet:
          path: /healthz
          port: 8000
        initialDelaySeconds: 15
        periodSeconds: 20
      readinessProbe:
        httpGet:
          path: /healthz
          port: 8000
        initialDelaySeconds: 5
        periodSeconds: 10
    """
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    from backend.models import SessionLocal

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error(f"/healthz — DB check failed: {e}")
        db_ok = False
    finally:
        db.close()

    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unreachable",
        "version": "0.1.13",
    }
    status_code = 200 if db_ok else 503
    return JSONResponse(content=payload, status_code=status_code)


@app.get("/status", tags=["Health"])
async def get_status():
    """
    Single-call health summary across all observability pillars.
    Returns aggregate counts AND a per-table status grid.
    Suitable for dashboard badges, Slack daily digests, and embedded widgets.
    """
    from datetime import timedelta

    from sqlalchemy import func as sqlfunc

    from backend.models import (
        CheckResult,
        CheckSuppression,
        FreshnessRecord,
        SchemaDiff,
        SessionLocal,
        VolumeRecord,
    )

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff_24h = now - timedelta(hours=24)

        # ---- Collect most-recent record per table for each pillar ----
        # Freshness: latest status per table
        freshness_subq = (
            db.query(
                FreshnessRecord.table_name, sqlfunc.max(FreshnessRecord.checked_at).label("latest")
            )
            .filter(FreshnessRecord.checked_at >= cutoff_24h)
            .group_by(FreshnessRecord.table_name)
            .subquery()
        )
        freshness_latest = (
            db.query(FreshnessRecord)
            .join(
                freshness_subq,
                (FreshnessRecord.table_name == freshness_subq.c.table_name)
                & (FreshnessRecord.checked_at == freshness_subq.c.latest),
            )
            .all()
        )

        # Volume: latest anomaly status per table
        volume_subq = (
            db.query(VolumeRecord.table_name, sqlfunc.max(VolumeRecord.recorded_at).label("latest"))
            .filter(VolumeRecord.recorded_at >= cutoff_24h)
            .group_by(VolumeRecord.table_name)
            .subquery()
        )
        volume_latest = (
            db.query(VolumeRecord)
            .join(
                volume_subq,
                (VolumeRecord.table_name == volume_subq.c.table_name)
                & (VolumeRecord.recorded_at == volume_subq.c.latest),
            )
            .all()
        )

        # Quality: pass/fail counts per table in last 24h
        quality_rows = (
            db.query(
                CheckResult.table_name,
                sqlfunc.count(CheckResult.id).label("total"),
                sqlfunc.sum(CheckResult.passed.cast(sqlfunc.Integer())).label("passed"),
                sqlfunc.max(CheckResult.executed_at).label("latest"),
            )
            .filter(CheckResult.executed_at >= cutoff_24h)
            .group_by(CheckResult.table_name)
            .all()
        )

        # Schema: any drift in last 24h per table
        schema_rows = (
            db.query(
                SchemaDiff.table_name,
                sqlfunc.count(SchemaDiff.id).label("drifts"),
                sqlfunc.max(SchemaDiff.detected_at).label("latest"),
            )
            .filter(SchemaDiff.detected_at >= cutoff_24h)
            .group_by(SchemaDiff.table_name)
            .all()
        )

        # ---- Build per-table index ----
        tables: dict = {}

        for f in freshness_latest:
            t = tables.setdefault(
                f.table_name,
                {
                    "name": f.table_name,
                    "freshness": "ok",
                    "volume": "ok",
                    "quality": "ok",
                    "schema": "ok",
                    "last_checked": None,
                },
            )
            t["freshness"] = f.status  # ok | warn | fail
            t["last_checked"] = f.checked_at.isoformat()

        for v in volume_latest:
            t = tables.setdefault(
                v.table_name,
                {
                    "name": v.table_name,
                    "freshness": "ok",
                    "volume": "ok",
                    "quality": "ok",
                    "schema": "ok",
                    "last_checked": None,
                },
            )
            t["volume"] = "fail" if v.is_anomaly else "ok"
            if not t["last_checked"] or v.recorded_at.isoformat() > t["last_checked"]:
                t["last_checked"] = v.recorded_at.isoformat()

        for q in quality_rows:
            t = tables.setdefault(
                q.table_name,
                {
                    "name": q.table_name,
                    "freshness": "ok",
                    "volume": "ok",
                    "quality": "ok",
                    "schema": "ok",
                    "last_checked": None,
                },
            )
            passed = int(q.passed or 0)
            total = int(q.total or 0)
            rate = (passed / total) if total > 0 else 1.0
            t["quality"] = "ok" if rate == 1.0 else ("warn" if rate >= 0.8 else "fail")
            t["quality_pass_rate"] = round(rate * 100, 1)
            if not t["last_checked"] or q.latest.isoformat() > t["last_checked"]:
                t["last_checked"] = q.latest.isoformat()

        for s in schema_rows:
            t = tables.setdefault(
                s.table_name,
                {
                    "name": s.table_name,
                    "freshness": "ok",
                    "volume": "ok",
                    "quality": "ok",
                    "schema": "ok",
                    "last_checked": None,
                },
            )
            t["schema"] = "fail" if int(s.drifts) > 0 else "ok"
            if not t["last_checked"] or s.latest.isoformat() > t["last_checked"]:
                t["last_checked"] = s.latest.isoformat()

        # ---- Summary counts ----
        def _worst(row):
            for pillar in ("freshness", "volume", "quality", "schema"):
                if row.get(pillar) == "fail":
                    return "fail"
            for pillar in ("freshness", "volume", "quality", "schema"):
                if row.get(pillar) == "warn":
                    return "warn"
            return "ok"

        table_list = sorted(tables.values(), key=lambda x: x["name"])
        statuses = [_worst(t) for t in table_list]
        summary = {
            "healthy": statuses.count("ok"),
            "warn": statuses.count("warn"),
            "fail": statuses.count("fail"),
        }

        # Active suppressions
        active_suppressions = (
            db.query(CheckSuppression).filter(CheckSuppression.suppressed_until >= now).count()
        )

        # Last run timestamps per pillar (global)
        last_freshness = db.query(sqlfunc.max(FreshnessRecord.checked_at)).scalar()
        last_volume = db.query(sqlfunc.max(VolumeRecord.recorded_at)).scalar()
        last_quality = db.query(sqlfunc.max(CheckResult.executed_at)).scalar()
        last_schema = db.query(sqlfunc.max(SchemaDiff.detected_at)).scalar()

        return {
            "generated_at": now.isoformat(),
            "window_hours": 24,
            "summary": summary,
            "tables": table_list,
            "pillars": {
                "freshness": {
                    "last_checked": last_freshness.isoformat() if last_freshness else None
                },
                "volume": {"last_checked": last_volume.isoformat() if last_volume else None},
                "quality": {"last_checked": last_quality.isoformat() if last_quality else None},
                "schema": {"last_detected": last_schema.isoformat() if last_schema else None},
            },
            "suppressions": {"active": active_suppressions},
        }
    finally:
        db.close()


@app.get("/scheduler/jobs", tags=["Scheduler"], dependencies=[Depends(verify_api_key)])
async def scheduler_jobs():
    """
    List all scheduled jobs with their next run time and trigger configuration.
    Useful for operational dashboards and debugging scheduler state.
    """
    jobs = get_scheduler_jobs()
    return {"jobs": jobs, "count": len(jobs)}


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
