"""
ObservaKit — Data Observability Starter Kit
FastAPI Backend Service
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from backend.models import Base, engine
from backend.routers import checks, freshness, schema_diff, webhooks
from backend.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — init DB and start scheduler."""
    # Create all tables on startup
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
    version="0.1.0",
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
app.include_router(freshness.router, prefix="/freshness", tags=["Freshness"])
app.include_router(checks.router, prefix="/checks", tags=["Quality Checks"])
app.include_router(schema_diff.router, prefix="/schema", tags=["Schema Drift"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "ObservaKit",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}
