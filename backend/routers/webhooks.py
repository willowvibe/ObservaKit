"""
ObservaKit — Webhooks Router
Receives callbacks from Airflow and Prefect for pipeline health tracking.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.models import AlertLog, PipelineRun, get_db
from config.loader import load_config
from alerts.slack import SlackDispatcher

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/test-alert")
def trigger_test_alert():
    """Trigger a generic test alert to verify webhook configuration."""
    config = load_config()
    dispatcher = SlackDispatcher(config)
    success = dispatcher.send("🔔 *ObservaKit Test Alert*\nIf you are seeing this, your Slack integration is working perfectly!")
    if success:
        return {"status": "success", "message": "Test alert dispatched."}
    else:
        return {"status": "error", "message": "Failed to dispatch test alert."}


@router.get("/airflow")
def get_airflow_logs(limit: int = 50, db: Session = Depends(get_db)):
    """
    Return recent Airflow pipeline run events so the Dashboard Alerts tab
    can display them without requiring a separate AlertLog query.
    Returns shape: { "logs": [...] }
    """
    runs = (
        db.query(PipelineRun)
        .filter(PipelineRun.orchestrator == "airflow")
        .order_by(PipelineRun.recorded_at.desc())
        .limit(limit)
        .all()
    )
    logs = [
        {
            "dag_id": r.dag_id,
            "run_id": r.run_id,
            "state": r.state,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
            "duration_seconds": r.duration_seconds,
            "received_at": r.recorded_at.isoformat(),
        }
        for r in runs
    ]
    return {"logs": logs}


@router.post("/airflow")
async def airflow_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive Airflow task/DAG run callbacks.
    Expected payload:
    {
        "dag_id": "...",
        "run_id": "...",
        "state": "success|failed|running",
        "start_date": "...",
        "end_date": "...",
        "duration": 123.45
    }
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON payload"})

    run = PipelineRun(
        orchestrator="airflow",
        dag_id=payload.get("dag_id", "unknown"),
        run_id=payload.get("run_id", "unknown"),
        state=payload.get("state", "unknown"),
        start_time=_parse_datetime(payload.get("start_date")),
        end_time=_parse_datetime(payload.get("end_date")),
        duration_seconds=payload.get("duration"),
    )
    db.add(run)
    db.commit()

    logger.info(f"Airflow webhook: dag={run.dag_id} state={run.state}")
    return {"status": "received", "dag_id": run.dag_id, "state": run.state}


@router.post("/prefect")
async def prefect_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive Prefect flow run callbacks.
    Expected payload:
    {
        "flow_name": "...",
        "flow_run_id": "...",
        "state": "Completed|Failed|Running",
        "start_time": "...",
        "end_time": "...",
        "total_run_time": 123.45
    }
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON payload"})

    # Normalize Prefect state names
    state_map = {"Completed": "success", "Failed": "failed", "Running": "running"}
    state = state_map.get(payload.get("state", ""), payload.get("state", "unknown"))

    run = PipelineRun(
        orchestrator="prefect",
        dag_id=payload.get("flow_name", "unknown"),
        run_id=payload.get("flow_run_id", "unknown"),
        state=state,
        start_time=_parse_datetime(payload.get("start_time")),
        end_time=_parse_datetime(payload.get("end_time")),
        duration_seconds=payload.get("total_run_time"),
    )
    db.add(run)
    db.commit()

    logger.info(f"Prefect webhook: flow={run.dag_id} state={run.state}")
    return {"status": "received", "flow": run.dag_id, "state": run.state}


@router.get("/runs")
def get_pipeline_runs(
    orchestrator: Optional[str] = None,
    dag_id: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Query pipeline run history."""
    query = db.query(PipelineRun).order_by(PipelineRun.recorded_at.desc())
    if orchestrator:
        query = query.filter(PipelineRun.orchestrator == orchestrator)
    if dag_id:
        query = query.filter(PipelineRun.dag_id == dag_id)
    if state:
        query = query.filter(PipelineRun.state == state)

    runs = query.limit(limit).all()

    return [
        {
            "orchestrator": r.orchestrator,
            "dag_id": r.dag_id,
            "run_id": r.run_id,
            "state": r.state,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
            "duration_seconds": r.duration_seconds,
            "recorded_at": r.recorded_at.isoformat(),
        }
        for r in runs
    ]


def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse an ISO datetime string, returning None on failure."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

