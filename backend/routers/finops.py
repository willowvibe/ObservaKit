"""
ObservaKit — FinOps Router
Polls warehouse for compute costs (e.g., Snowflake credits, BigQuery bytes billed)
and exposes them as Prometheus metrics.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import Gauge
from sqlalchemy.orm import Session

from backend.auth import verify_api_key
from backend.models import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

finops_cost_gauge = Gauge(
    "observakit_finops_costs",
    "Compute cost (credits/bytes) over the last N days",
    ["warehouse"]
)

@router.post("/poll", dependencies=[Depends(verify_api_key)])
def poll_finops_costs(days: int = 7, db: Session = Depends(get_db)):
    """
    Trigger a cost check for the active warehouse.
    """
    import os

    from connectors.base import get_warehouse_connector

    warehouse_type = os.getenv("WAREHOUSE_TYPE", "postgres").lower()

    # Postgres doesn't have Serverless compute costs, so skip tracking
    if warehouse_type == "postgres":
        return {"message": "FinOps tracking not applicable for self-hosted PostgreSQL."}

    try:
        connector = get_warehouse_connector()
        cost = connector.get_compute_costs(days=days)
        finops_cost_gauge.labels(warehouse=warehouse_type).set(cost)

        return {
            "warehouse": warehouse_type,
            "cost_tracked": cost,
            "period_days": days
        }
    except Exception as e:
        logger.error(f"Failed to poll FinOps costs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
