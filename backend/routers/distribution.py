"""
ObservaKit — Distribution Drift Monitor
Tracks column value distributions over time and detects statistical drift.

Why this matters in production:
  - Schema drift catches column additions/removals, but NOT when values change silently.
  - Example: a `status` column still has the same columns, but suddenly 80 % of rows
    are 'cancelled' instead of the usual 5 %. Volume checks won't catch this because
    the total row count looks fine. Distribution drift catches it.
  - Other real cases: country codes suddenly shifting, payment methods changing,
    null-% creeping up on a previously clean column.

Algorithm:
  1. Snapshot the top-N value distribution for categorical columns (value → count / pct).
  2. For numeric columns snapshot a 10-bucket histogram.
  3. Compare the latest snapshot against the previous one using two signals:
       a. Dominant-value shift: any single value whose share changed by > threshold.
       b. Null-% change: null share changes by more than null_drift_threshold.
  4. Store snapshots and diffs in the metadata DB.
  5. Emit Prometheus gauges and fire alerts on significant drift.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import Gauge
from sqlalchemy.orm import Session

from alerts.base import dispatch_alert
from backend.models import DistributionDrift, DistributionSnapshot, get_db
from config.loader import load_config

logger = logging.getLogger(__name__)

router = APIRouter()

# Prometheus
distribution_drift_gauge = Gauge(
    "observakit_distribution_drift",
    "Max value-share change detected for a column (0-1)",
    ["table", "column"],
)

TOP_N = 20           # How many top values to track for categoricals
BUCKET_COUNT = 10    # Histogram buckets for numerics


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.post("/snapshot")
def take_distribution_snapshot(
    table_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Snapshot column distributions for all configured tables (or a specific one).
    Compares against the previous snapshot and records drift if found.
    """
    try:
        config = load_config("config/kit.yml")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/kit.yml not found")

    dist_config = config.get("distribution", {})
    if not dist_config.get("enabled", False):
        return {"message": "Distribution drift monitoring is disabled"}

    tables = dist_config.get("tables", [])
    if table_name:
        tables = [t for t in tables if t.get("table") == table_name]

    if not tables:
        return {"message": "No tables configured for distribution monitoring"}

    from connectors.base import get_warehouse_connector
    connector = get_warehouse_connector()

    results = []
    for table_cfg in tables:
        tname = table_cfg["table"]
        columns = table_cfg.get("columns", [])
        threshold = float(table_cfg.get("drift_threshold", 0.1))  # 10% share shift
        null_threshold = float(table_cfg.get("null_drift_threshold", 0.05))  # 5% null shift

        for col_cfg in columns:
            col_name = col_cfg["name"]
            col_type = col_cfg.get("type", "categorical")  # categorical | numeric

            try:
                if col_type == "numeric":
                    dist_data = _snapshot_numeric(connector, tname, col_name)
                else:
                    dist_data = _snapshot_categorical(connector, tname, col_name, TOP_N)

                # Persist snapshot
                snap = DistributionSnapshot(
                    table_name=tname,
                    column_name=col_name,
                    column_type=col_type,
                    distribution=dist_data,
                    snapshotted_at=datetime.now(timezone.utc),
                )
                db.add(snap)
                db.flush()

                # Compare with previous snapshot
                prev = (
                    db.query(DistributionSnapshot)
                    .filter(
                        DistributionSnapshot.table_name == tname,
                        DistributionSnapshot.column_name == col_name,
                        DistributionSnapshot.id != snap.id,
                    )
                    .order_by(DistributionSnapshot.snapshotted_at.desc())
                    .first()
                )

                drift_result = None
                if prev:
                    drift_result = _detect_drift(
                        prev.distribution, dist_data, col_type, threshold, null_threshold
                    )
                    if drift_result["drifted"]:
                        drift_record = DistributionDrift(
                            table_name=tname,
                            column_name=col_name,
                            drift_type=drift_result["drift_type"],
                            previous_value=str(drift_result.get("previous_value")),
                            current_value=str(drift_result.get("current_value")),
                            change_magnitude=drift_result.get("magnitude"),
                            detected_at=datetime.now(timezone.utc),
                        )
                        db.add(drift_record)

                        distribution_drift_gauge.labels(table=tname, column=col_name).set(
                            drift_result.get("magnitude", 0)
                        )

                        dispatch_alert(
                            alert_type="distribution",
                            table_name=tname,
                            subject=f"📊 Distribution Drift: {tname}.{col_name}",
                            message=(
                                f"Column `{col_name}` in `{tname}` has drifted.\n"
                                f"Type: {drift_result['drift_type']}\n"
                                f"Magnitude: {drift_result.get('magnitude', 0) * 100:.1f}%\n"
                                f"Previous: {drift_result.get('previous_value')}\n"
                                f"Current:  {drift_result.get('current_value')}"
                            ),
                            db=db,
                            severity="warn"
                        )

                results.append({
                    "table": tname,
                    "column": col_name,
                    "type": col_type,
                    "snapshot_taken": True,
                    "drift": drift_result,
                })

            except Exception as e:
                logger.error(f"Distribution snapshot failed for {tname}.{col_name}: {e}")
                results.append({"table": tname, "column": col_name, "error": str(e)})

    db.commit()
    return {"snapshots": len(results), "results": results}


@router.get("/drifts/{table_name}")
def get_distribution_drifts(
    table_name: str,
    days: int = 7,
    db: Session = Depends(get_db),
):
    """Return detected distribution drifts for a table in the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    drifts = (
        db.query(DistributionDrift)
        .filter(
            DistributionDrift.table_name == table_name,
            DistributionDrift.detected_at >= cutoff,
        )
        .order_by(DistributionDrift.detected_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "table": d.table_name,
            "column": d.column_name,
            "drift_type": d.drift_type,
            "previous_value": d.previous_value,
            "current_value": d.current_value,
            "change_magnitude_pct": round((d.change_magnitude or 0) * 100, 2),
            "detected_at": d.detected_at.isoformat(),
        }
        for d in drifts
    ]


@router.get("/history/{table_name}/{column_name}")
def get_distribution_history(
    table_name: str,
    column_name: str,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """Return recent distribution snapshots for a specific column — useful for trend charts."""
    snaps = (
        db.query(DistributionSnapshot)
        .filter(
            DistributionSnapshot.table_name == table_name,
            DistributionSnapshot.column_name == column_name,
        )
        .order_by(DistributionSnapshot.snapshotted_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": s.id,
            "table": s.table_name,
            "column": s.column_name,
            "type": s.column_type,
            "distribution": s.distribution,
            "snapshotted_at": s.snapshotted_at.isoformat(),
        }
        for s in snaps
    ]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _snapshot_categorical(connector, table: str, column: str, top_n: int) -> dict:
    """
    Return top-N value distribution for a categorical column.
    Result format:
      {
        "total_rows": 10000,
        "null_count": 200,
        "null_pct": 0.02,
        "top_values": [
          {"value": "active", "count": 8000, "pct": 0.80},
          ...
        ]
      }
    """
    total_rows_result = connector.execute_query(f"SELECT COUNT(*) AS cnt FROM {table}")
    total_rows = int(total_rows_result[0]["cnt"]) if total_rows_result else 0

    null_result = connector.execute_query(
        f"SELECT COUNT(*) AS cnt FROM {table} WHERE {column} IS NULL"
    )
    null_count = int(null_result[0]["cnt"]) if null_result else 0
    null_pct = null_count / total_rows if total_rows > 0 else 0

    top_result = connector.execute_query(
        f"""
        SELECT {column} AS val, COUNT(*) AS cnt
        FROM {table}
        WHERE {column} IS NOT NULL
        GROUP BY {column}
        ORDER BY cnt DESC
        LIMIT {top_n}
        """
    )

    top_values = [
        {
            "value": str(row["val"]),
            "count": int(row["cnt"]),
            "pct": int(row["cnt"]) / total_rows if total_rows > 0 else 0,
        }
        for row in top_result
    ]

    return {
        "total_rows": total_rows,
        "null_count": null_count,
        "null_pct": null_pct,
        "top_values": top_values,
    }


def _snapshot_numeric(connector, table: str, column: str) -> dict:
    """
    Return a histogram + basic stats for a numeric column.
    Uses equal-width bucketing via SQL NTILE equivalent (WIDTH_BUCKET for Postgres/Redshift,
    manual binning for others).
    Result format:
      {
        "total_rows": 10000,
        "null_count": 50,
        "null_pct": 0.005,
        "min": 0.0, "max": 9999.0, "mean": 250.3, "stddev": 120.1,
        "percentiles": {"p25": 100, "p50": 200, "p75": 400, "p95": 800},
        "histogram": [{"bucket": 1, "range_low": 0, "range_high": 999, "count": 3200}, ...]
      }
    """
    stats_result = connector.execute_query(
        f"""
        SELECT
            COUNT(*)          AS total_rows,
            COUNT(*) - COUNT({column}) AS null_count,
            MIN({column})     AS min_val,
            MAX({column})     AS max_val,
            AVG({column})     AS mean_val
        FROM {table}
        """
    )
    row = stats_result[0] if stats_result else {}

    total_rows = int(row.get("total_rows") or 0)
    null_count = int(row.get("null_count") or 0)
    null_pct = null_count / total_rows if total_rows > 0 else 0
    min_val = float(row.get("min_val") or 0)
    max_val = float(row.get("max_val") or 0)
    mean_val = float(row.get("mean_val") or 0)

    # Percentiles via ordered sub-select (portable SQL, no PERCENTILE_CONT needed)
    non_null_rows = total_rows - null_count
    percentiles = {}
    if non_null_rows > 0:
        for pct_name, pct_val in [("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p95", 0.95)]:
            offset = max(0, int(non_null_rows * pct_val) - 1)
            pct_result = connector.execute_query(
                f"""
                SELECT {column} AS val FROM {table}
                WHERE {column} IS NOT NULL
                ORDER BY {column}
                LIMIT 1 OFFSET {offset}
                """
            )
            percentiles[pct_name] = float(pct_result[0]["val"]) if pct_result else None

    # Simple histogram: divide range into BUCKET_COUNT equal-width buckets
    histogram = []
    if max_val > min_val and non_null_rows > 0:
        bucket_width = (max_val - min_val) / BUCKET_COUNT
        for i in range(BUCKET_COUNT):
            low = min_val + i * bucket_width
            high = low + bucket_width
            op = "<=" if i == BUCKET_COUNT - 1 else "<"
            count_result = connector.execute_query(
                f"""
                SELECT COUNT(*) AS cnt FROM {table}
                WHERE {column} >= {low} AND {column} {op} {high}
                """
            )
            histogram.append({
                "bucket": i + 1,
                "range_low": round(low, 4),
                "range_high": round(high, 4),
                "count": int(count_result[0]["cnt"]) if count_result else 0,
            })

    return {
        "total_rows": total_rows,
        "null_count": null_count,
        "null_pct": null_pct,
        "min": min_val,
        "max": max_val,
        "mean": mean_val,
        "percentiles": percentiles,
        "histogram": histogram,
    }


def _detect_drift(
    prev: dict,
    curr: dict,
    col_type: str,
    threshold: float,
    null_threshold: float,
) -> dict:
    """
    Compare two distribution snapshots and return a drift summary.

    Returns:
      {
        "drifted": bool,
        "drift_type": "null_pct_change" | "value_share_shift" | "mean_shift" | None,
        "magnitude": float,   # biggest change, as a fraction (0–1)
        "previous_value": ...,
        "current_value": ...,
      }
    """
    # --- Null % drift (applies to both types) ---
    prev_null = prev.get("null_pct", 0)
    curr_null = curr.get("null_pct", 0)
    null_change = abs(curr_null - prev_null)
    if null_change >= null_threshold:
        return {
            "drifted": True,
            "drift_type": "null_pct_change",
            "magnitude": null_change,
            "previous_value": f"{prev_null * 100:.1f}% nulls",
            "current_value": f"{curr_null * 100:.1f}% nulls",
        }

    if col_type == "categorical":
        # Build value→pct maps
        prev_map = {v["value"]: v["pct"] for v in prev.get("top_values", [])}
        curr_map = {v["value"]: v["pct"] for v in curr.get("top_values", [])}

        all_values = set(prev_map) | set(curr_map)
        max_shift = 0.0
        max_value = None
        for val in all_values:
            shift = abs(curr_map.get(val, 0) - prev_map.get(val, 0))
            if shift > max_shift:
                max_shift = shift
                max_value = val

        if max_shift >= threshold:
            prev_pct = prev_map.get(max_value, 0)
            curr_pct = curr_map.get(max_value, 0)
            return {
                "drifted": True,
                "drift_type": "value_share_shift",
                "magnitude": max_shift,
                "previous_value": f"'{max_value}' = {prev_pct * 100:.1f}%",
                "current_value": f"'{max_value}' = {curr_pct * 100:.1f}%",
            }

    elif col_type == "numeric":
        prev_mean = prev.get("mean", 0) or 0
        curr_mean = curr.get("mean", 0) or 0
        prev_max = prev.get("max", 1) or 1
        # Normalise mean shift by historical max to get a 0-1 magnitude
        mean_shift = abs(curr_mean - prev_mean) / (abs(prev_max) or 1)
        if mean_shift >= threshold:
            return {
                "drifted": True,
                "drift_type": "mean_shift",
                "magnitude": mean_shift,
                "previous_value": f"mean={prev_mean:.2f}",
                "current_value": f"mean={curr_mean:.2f}",
            }

    return {"drifted": False, "drift_type": None, "magnitude": 0}
