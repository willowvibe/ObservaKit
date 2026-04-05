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

        is_numeric = any(t in col_type for t in ["int", "decimal", "numeric", "float", "real", "double"])

        # Use portable SQL instead of PostgreSQL-only FILTER clause.
        # CAST(... AS CHAR) works on MySQL; CAST(... AS VARCHAR) on others;
        # use a simple CAST(... AS TEXT) which is broadly supported.
        mean_expr = f"AVG({col_name})" if is_numeric else "NULL"

        stats_query = f"""
            SELECT
                SUM(CASE WHEN {col_name} IS NULL THEN 1 ELSE 0 END) AS null_count,
                COUNT(DISTINCT {col_name}) AS distinct_count,
                CAST(MIN({col_name}) AS VARCHAR) AS min_val,
                CAST(MAX({col_name}) AS VARCHAR) AS max_val,
                {mean_expr} AS mean_val
            FROM {table_name}
        """

        try:
            results = connector.execute_query(stats_query)
            if results:
                res = results[0]
                null_count = int(res["null_count"] or 0)
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
