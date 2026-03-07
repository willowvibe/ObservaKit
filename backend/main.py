"""
ObservaKit — Data Observability Starter Kit
FastAPI Backend Service
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.models import engine, Base
from backend.routers import freshness, checks, schema_diff, webhooks
from backend.scheduler import start_scheduler, shutdown_scheduler


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

# CORS — allow the Grafana frontend and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
