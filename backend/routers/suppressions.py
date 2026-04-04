"""
ObservaKit — Check Suppression Router
Allows muting alerts for a table during planned maintenance windows.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models import CheckSuppression, get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class SuppressRequest(BaseModel):
    table_name: str
    duration_minutes: int
    reason: Optional[str] = None


@router.post("/", status_code=201)
def create_suppression(req: SuppressRequest, db: Session = Depends(get_db)):
    """
    Suppress alerts for a table for a specified duration.

    Example:
        POST /suppress
        {"table_name": "public.orders", "duration_minutes": 60, "reason": "Planned ETL reload"}
    """
    from datetime import timedelta

    suppressed_until = datetime.now(timezone.utc) + timedelta(minutes=req.duration_minutes)

    suppression = CheckSuppression(
        table_name=req.table_name,
        suppressed_until=suppressed_until,
        reason=req.reason,
    )
    db.add(suppression)
    db.commit()
    db.refresh(suppression)

    logger.info(f"Alert suppression created for {req.table_name} until {suppressed_until}")
    return {
        "id": suppression.id,
        "table_name": suppression.table_name,
        "suppressed_until": suppression.suppressed_until.isoformat(),
        "reason": suppression.reason,
        "created_at": suppression.created_at.isoformat(),
    }


@router.get("/")
def list_suppressions(active_only: bool = True, db: Session = Depends(get_db)):
    """List suppression rules, optionally only those still active."""
    query = db.query(CheckSuppression)
    if active_only:
        query = query.filter(CheckSuppression.suppressed_until >= datetime.now(timezone.utc))
    suppressions = query.order_by(CheckSuppression.suppressed_until.desc()).all()

    return [
        {
            "id": s.id,
            "table_name": s.table_name,
            "suppressed_until": s.suppressed_until.isoformat(),
            "reason": s.reason,
            "created_at": s.created_at.isoformat(),
        }
        for s in suppressions
    ]


@router.delete("/{suppression_id}", status_code=204)
def delete_suppression(suppression_id: int, db: Session = Depends(get_db)):
    """Remove a suppression rule early (re-enable alerts for a table immediately)."""
    suppression = db.query(CheckSuppression).filter(CheckSuppression.id == suppression_id).first()
    if not suppression:
        raise HTTPException(status_code=404, detail=f"Suppression {suppression_id} not found")
    db.delete(suppression)
    db.commit()
    logger.info(f"Suppression {suppression_id} for {suppression.table_name} removed early")
    return None
