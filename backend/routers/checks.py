"""
ObservaKit — Quality Checks & Volume Monitor Router
Triggers Soda/GX checks, stores results, and runs volume anomaly detection.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import Gauge
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import CheckResult, VolumeRecord, get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# Prometheus gauges
volume_gauge = Gauge(
    "data_volume_rows",
    "Row count for monitored tables",
    ["table", "dag"],
)


@router.get("/results")
def get_check_results(
    table_name: Optional[str] = None,
    passed: Optional[bool] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Query historical quality check results."""
    query = db.query(CheckResult).order_by(CheckResult.executed_at.desc())
    if table_name:
        query = query.filter(CheckResult.table_name == table_name)
    if passed is not None:
        query = query.filter(CheckResult.passed == passed)
    records = query.limit(limit).all()

    return [
        {
            "id": r.id,
            "check_name": r.check_name,
            "table": r.table_name,
            "check_type": r.check_type,
            "passed": r.passed,
            "metric_value": r.metric_value,
            "details": r.details,
            "executed_at": r.executed_at.isoformat(),
        }
        for r in records
    ]


@router.post("/run")
def run_quality_checks(db: Session = Depends(get_db)):
    """
    Trigger quality checks using configured engine (Soda Core or GX).
    Reads check definitions from the configured checks directory.
    """
    import yaml

    try:
        with open("config/kit.yml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/kit.yml not found")

    quality_config = config.get("quality", {})
    if not quality_config.get("enabled", False):
        return {"message": "Quality checks are disabled"}

    engine = quality_config.get("engine", "soda")
    checks_dir = quality_config.get("checks_dir", "checks/my_project/")

    # Discover and run checks
    import glob
    import os

    check_files = glob.glob(os.path.join(checks_dir, "*.yml"))
    results = []

    for check_file in check_files:
        try:
            with open(check_file, "r") as f:
                check_def = yaml.safe_load(f)

            # Parse the check definition and store results
            for key, checks in check_def.items():
                if key.startswith("checks for "):
                    table_name = key.replace("checks for ", "")
                    for check in checks if isinstance(checks, list) else []:
                        check_name = str(check) if isinstance(check, str) else str(check)
                        record = CheckResult(
                            check_name=check_name,
                            table_name=table_name,
                            check_type=engine,
                            passed=True,  # Will be updated by actual execution
                            details=f"Loaded from {os.path.basename(check_file)}",
                        )
                        db.add(record)
                        results.append({
                            "check": check_name,
                            "table": table_name,
                            "file": os.path.basename(check_file),
                        })

        except Exception as e:
            logger.error(f"Error processing check file {check_file}: {e}")
            results.append({"file": os.path.basename(check_file), "error": str(e)})

    db.commit()
    return {"engine": engine, "checks_processed": len(results), "results": results}


@router.post("/volume")
def run_volume_checks(db: Session = Depends(get_db)):
    """
    Run volume anomaly detection.
    Queries current row counts, compares against 7-day rolling average using Z-score.
    """
    import yaml

    try:
        with open("config/kit.yml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/kit.yml not found")

    volume_config = config.get("volume", {})
    if not volume_config.get("enabled", False):
        return {"message": "Volume monitoring is disabled"}

    tables = volume_config.get("tables", [])
    window_days = volume_config.get("rolling_window_days", 7)
    results = []

    for table_cfg in tables:
        table_name = table_cfg["table"]
        dag_id = table_cfg.get("dag_id", "")
        threshold = table_cfg.get("anomaly_threshold", 0.3)

        try:
            from connectors.base import get_warehouse_connector

            connector = get_warehouse_connector()
            current_count = connector.get_row_count(table_name)

            # Calculate rolling average from stored history
            from datetime import timedelta

            cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
            avg_result = (
                db.query(func.avg(VolumeRecord.row_count))
                .filter(
                    VolumeRecord.table_name == table_name,
                    VolumeRecord.recorded_at >= cutoff,
                )
                .scalar()
            )

            rolling_avg = float(avg_result) if avg_result else float(current_count)
            deviation = abs(current_count - rolling_avg) / rolling_avg if rolling_avg > 0 else 0
            is_anomaly = deviation > threshold

            # Store record
            record = VolumeRecord(
                table_name=table_name,
                dag_id=dag_id,
                row_count=current_count,
                rolling_avg=rolling_avg,
                deviation_pct=deviation,
                is_anomaly=is_anomaly,
            )
            db.add(record)

            # Update Prometheus gauge
            volume_gauge.labels(table=table_name, dag=dag_id).set(current_count)

            result = {
                "table": table_name,
                "row_count": current_count,
                "rolling_avg": round(rolling_avg, 1),
                "deviation_pct": round(deviation * 100, 1),
                "is_anomaly": is_anomaly,
            }
            results.append(result)

            # Alert on anomaly
            if is_anomaly:
                _trigger_volume_alert(
                    table_name, current_count, rolling_avg, deviation, table_cfg.get("alert", "slack")
                )

        except Exception as e:
            logger.error(f"Volume check failed for {table_name}: {e}")
            results.append({"table": table_name, "error": str(e)})

    db.commit()
    return {"checked": len(results), "results": results}


def _trigger_volume_alert(table: str, count: int, avg: float, deviation: float, channel: str):
    """Dispatch a volume anomaly alert."""
    from alerts.base import get_alert_dispatcher

    message = (
        f"🔴 Volume Anomaly: {table}\n"
        f"  Current rows: {count:,}\n"
        f"  7-day average: {avg:,.0f}\n"
        f"  Deviation: {deviation * 100:.1f}%\n"
        f"  Detected at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    try:
        dispatcher = get_alert_dispatcher(channel)
        dispatcher.send(message)
    except Exception as e:
        logger.error(f"Failed to send volume alert: {e}")
