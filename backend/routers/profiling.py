"""
ObservaKit — Column Profiling Router
Executes column-level statistics and stores them for monitoring.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.models import ColumnProfile, get_db
from connectors.base import get_warehouse_connector

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/run")
def run_profiling(table_name: str, db: Session = Depends(get_db)):
    """
    Run column-level profiling for a specific table.
    """
    connector = get_warehouse_connector()
    schema = connector.get_schema(table_name)
    
    if not schema:
        raise HTTPException(status_code=404, detail=f"Table {table_name} not found or schema empty")

    row_count = connector.get_row_count(table_name)
    if row_count == 0:
        return {"message": f"Table {table_name} is empty, skipping profiling"}

    profiles = []
    for col in schema:
        col_name = col["name"]
        col_type = col["type"].lower()
        
        # Build profiling query
        stats_query = f"""
            SELECT 
                COUNT(*) FILTER (WHERE {col_name} IS NULL) as null_count,
                COUNT(DISTINCT {col_name}) as distinct_count,
                MIN({col_name})::text as min_val,
                MAX({col_name})::text as max_val
            FROM {table_name}
        """
        
        # Add mean for numeric types
        if any(t in col_type for t in ["int", "decimal", "numeric", "float", "real"]):
            stats_query = stats_query.replace("FROM", f", AVG({col_name}) as mean_val FROM")
        else:
            stats_query = stats_query.replace("FROM", f", NULL as mean_val FROM")

        try:
            results = connector.execute_query(stats_query)
            if results:
                res = results[0]
                null_count = int(res["null_count"])
                profile = ColumnProfile(
                    table_name=table_name,
                    column_name=col_name,
                    null_count=null_count,
                    null_pct=(null_count / row_count) if row_count > 0 else 0,
                    distinct_count=int(res["distinct_count"]),
                    min_value=res["min_val"],
                    max_value=res["max_val"],
                    mean_value=float(res["mean_val"]) if res["mean_val"] is not None else None,
                    profiled_at=datetime.now(timezone.utc)
                )
                db.add(profile)
                profiles.append({
                    "column": col_name,
                    "null_pct": round((null_count / row_count) * 100, 2) if row_count > 0 else 0,
                    "distinct_count": int(res["distinct_count"])
                })
        except Exception as e:
            logger.error(f"Failed to profile column {col_name} in {table_name}: {e}")

    db.commit()
    return {"table": table_name, "columns_profiled": len(profiles), "profiles": profiles}


@router.get("/latest/{table_name}")
def get_latest_profile(table_name: str, db: Session = Depends(get_db)):
    """Get the most recent profile for a table."""
    # Find the latest profiling run timestamp
    latest_run = db.query(ColumnProfile.profiled_at).filter(
        ColumnProfile.table_name == table_name
    ).order_by(ColumnProfile.profiled_at.desc()).first()
    
    if not latest_run:
        raise HTTPException(status_code=404, detail="No profiles found for this table")
    
    records = db.query(ColumnProfile).filter(
        ColumnProfile.table_name == table_name,
        ColumnProfile.profiled_at == latest_run[0]
    ).all()
    
    return records
