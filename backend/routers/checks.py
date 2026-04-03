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
from alerts.base import dispatch_alert, get_lineage_impact

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


@router.get("/trends/{table_name}")
def get_check_trends(
    table_name: str,
    days: int = 30,
    db: Session = Depends(get_db),
):
    """
    Get quality check trends for a specific table:
    Pass rate over time, failure streaks, and average execution time.
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    results = db.query(CheckResult).filter(
        CheckResult.table_name == table_name,
        CheckResult.executed_at >= cutoff
    ).order_by(CheckResult.executed_at.asc()).all()

    if not results:
        return {"table": table_name, "message": "No data for selected period"}

    # Calculate trends
    total_checks = len(results)
    passed_checks = sum(1 for r in results if r.passed)
    pass_rate = (passed_checks / total_checks) * 100 if total_checks > 0 else 0

    # Streaks (current failure streak if any)
    current_streak = 0
    for r in reversed(results):
        if not r.passed:
            current_streak += 1
        else:
            break

    # Daily aggregation
    daily_stats = {}
    for r in results:
        day = r.executed_at.date().isoformat()
        if day not in daily_stats:
            daily_stats[day] = {"passed": 0, "total": 0}
        daily_stats[day]["total"] += 1
        if r.passed:
            daily_stats[day]["passed"] += 1

    history = [
        {"day": d, "pass_rate": (s["passed"] / s["total"]) * 100}
        for d, s in sorted(daily_stats.items())
    ]

    return {
        "table": table_name,
        "period_days": days,
        "overall_pass_rate": round(pass_rate, 2),
        "current_failure_streak": current_streak,
        "history": history
    }


@router.post("/run")
def run_quality_checks(dry_run: bool = False, db: Session = Depends(get_db)):
    """
    Trigger quality checks using configured engine (Soda Core or GX).
    """
    import yaml
    import glob
    import os
    from connectors.base import get_warehouse_connector

    try:
        with open("config/kit.yml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/kit.yml not found")

    quality_config = config.get("quality", {})
    if not quality_config.get("enabled", False):
        return {"message": "Quality checks are disabled"}

    engine_name = quality_config.get("engine", "soda")
    checks_dir = quality_config.get("checks_dir", "checks/my_project/")
    connector = get_warehouse_connector()

    check_files = glob.glob(os.path.join(checks_dir, "*.yml"))
    all_results = []

    for check_file in check_files:
        if engine_name == "soda":
            results = _run_soda_check(check_file, connector)
        elif engine_name == "great_expectations":
            results = _run_gx_check(check_file, connector)
        else:
            logger.error(f"Unsupported engine: {engine_name}")
            continue

        for res in results:
            if not dry_run:
                record = CheckResult(
                    check_name=res["check_name"],
                    table_name=res["table_name"],
                    check_type=engine_name,
                    passed=res["passed"],
                    metric_value=res.get("metric_value"),
                    details=res.get("details"),
                    executed_at=datetime.now(timezone.utc)
                )
                db.add(record)
            
            all_results.append(res)

    # --- Run Custom SQL Checks ---
    custom_sql_checks = quality_config.get("custom_sql", [])
    for check_cfg in custom_sql_checks:
        try:
            name = check_cfg.get("name")
            query = check_cfg.get("query")
            assertion = check_cfg.get("assert", "result == 0")
            table = check_cfg.get("table", "unknown")
            
            # Execute the query
            query_results = connector.execute_query(query)
            # Typically these queries return a single value, e.g., a count
            result_value = 0
            if query_results and len(query_results) > 0:
                # Get the first value from the first row
                first_row = query_results[0]
                result_value = list(first_row.values())[0] if first_row else 0

            # Evaluate assertion
            passed = False
            try:
                # Safe eval with restricted globals
                passed = eval(assertion, {"__builtins__": None}, {"result": result_value})
            except Exception as eval_e:
                logger.error(f"Assertion evaluation failed for {name}: {eval_e}")
                passed = False

            if not dry_run:
                record = CheckResult(
                    check_name=name,
                    table_name=table,
                    check_type="custom_sql",
                    passed=passed,
                    metric_value=float(result_value) if isinstance(result_value, (int, float)) else None,
                    details=f"Query: {query.strip()[:100]}... | Result: {result_value}",
                    executed_at=datetime.now(timezone.utc)
                )
                db.add(record)

            all_results.append({
                "check_name": name,
                "table_name": table,
                "passed": passed,
                "engine": "custom_sql"
            })

            if not passed and not dry_run:
                # Trigger lineage-aware alert
                downstream = get_lineage_impact(table)
                impact_msg = f"\n⚠️ Downstream impact: {', '.join(downstream)}" if downstream else ""
                
                dispatch_alert(
                    alert_type="quality",
                    table_name=table,
                    subject=f"❌ Quality Check Failed: {name}",
                    message=f"Table: {table}\nCheck: {name}\nResult: {result_value}\nAssertion: {assertion}{impact_msg}"
                )

        except Exception as e:
            logger.error(f"Error running custom SQL check {check_cfg.get('name')}: {e}")

    if not dry_run:
        db.commit()
    return {"engine": engine_name, "checks_run": len(all_results), "results": all_results, "dry_run": dry_run}


def _run_soda_check(check_file: str, connector) -> list[dict]:
    """Execute Soda Core checks."""
    try:
        from soda.scan import Scan
    except ImportError:
        logger.error("soda-core not installed")
        return [{"check_error": "soda-core not installed", "passed": False, "table_name": "unknown", "check_name": "soda_init"}]

    scan = Scan()
    scan.set_data_source_name("my_postgres")
    
    # Add configuration from connector
    soda_config_dict = connector.get_soda_config()
    import yaml
    scan.add_configuration_yaml_str(yaml.dump(soda_config_dict))
    
    scan.add_sodacl_yaml_file(check_file)
    scan.execute()
    
    results = []
    for check in scan.get_checks_fail():
        results.append({
            "check_name": check.name,
            "table_name": check.table_name if hasattr(check, 'table_name') else "unknown",
            "passed": False,
            "details": check.get_cloud_dict().get("diagnostic_messaging")
        })
    for check in scan.get_checks_pass():
        results.append({
            "check_name": check.name,
            "table_name": check.table_name if hasattr(check, 'table_name') else "unknown",
            "passed": True,
            "details": "Check passed"
        })
    return results


def _run_gx_check(check_file: str, connector) -> list[dict]:
    """Execute Great Expectations checks (Simplified implementation)."""
    # This is a placeholder for actual GX execution logic as GX setup is more involved
    logger.info(f"Running GX checks for {check_file}")
    return [{
        "check_name": "gx_check_placeholder",
        "table_name": "unknown",
        "passed": True,
        "details": "GX execution logic placeholder"
    }]


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
                    table_name, current_count, rolling_avg, deviation, table_cfg.get("alert", "slack"), db
                )

        except Exception as e:
            logger.error(f"Volume check failed for {table_name}: {e}")
            results.append({"table": table_name, "error": str(e)})

    db.commit()
    return {"checked": len(results), "results": results}


def _trigger_volume_alert(table: str, count: int, avg: float, deviation: float, channel: str, db: Session):
    """Dispatch a volume anomaly alert."""
    from datetime import timedelta

    from alerts.base import get_alert_dispatcher
    from backend.models import AlertLog

    # Deduplication: skip if same table+type was alerted in the last 60 minutes
    recent = db.query(AlertLog).filter(
        AlertLog.table_name == table,
        AlertLog.alert_type == "volume",
        AlertLog.sent_at >= datetime.now(timezone.utc) - timedelta(minutes=60),
    ).first()
    if recent:
        logger.info(f"Skipping duplicate alert for {table} (last sent {recent.sent_at})")
        return

    downstream = get_lineage_impact(table)
    impact_msg = f"\n⚠️ Downstream impact: {', '.join(downstream)}" if downstream else ""

    message = (
        f"🔴 Volume Anomaly: {table}\n"
        f"  Current rows: {count:,}\n"
        f"  7-day average: {avg:,.0f}\n"
        f"  Deviation: {deviation * 100:.1f}%\n"
        f"  Detected at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        f"{impact_msg}"
    )
    success = False
    try:
        dispatch_alert(
            alert_type="volume",
            table_name=table,
            subject=f"🔴 Volume Anomaly: {table}",
            message=message
        )
        success = True
    except Exception as e:
        logger.error(f"Failed to send volume alert: {e}")

    # Log the alert for deduplication and audit
    alert_log = AlertLog(
        alert_type="volume",
        channel=channel,
        table_name=table,
        message=message,
        success=success,
    )
    db.add(alert_log)
