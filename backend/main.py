"""
ObservaKit — Data Observability Starter Kit
FastAPI Backend Service
"""

import logging
import os
from contextlib import asynccontextmanager

from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from alembic import command
from backend.auth import verify_api_key
from backend.routers import checks, finops, freshness, schema_diff, webhooks
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
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="ObservaKit",
    description=(
        "Data Observability Starter Kit — self-hosted observability layer "
        "providing Freshness, Volume, Quality, Schema Drift, and Pipeline Health monitoring."
    ),
    version="0.1.2",
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
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "ObservaKit",
        "version": "0.1.2",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}
