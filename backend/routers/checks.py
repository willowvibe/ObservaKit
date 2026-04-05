"""
ObservaKit — Quality Checks & Volume Monitor Router
Triggers Soda/GX checks, stores results, and runs volume anomaly detection.
"""

import ast
import glob
import json
import logging
import operator
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import Gauge
from sqlalchemy import func
from sqlalchemy.orm import Session

from alerts.base import dispatch_alert, get_lineage_impact
from backend.models import AlertLog, CheckResult, VolumeRecord, get_db
from config.loader import load_config
from connectors.base import get_warehouse_connector

logger = logging.getLogger(__name__)

router = APIRouter()

# Prometheus gauges
volume_gauge = Gauge(
    "data_volume_rows",
    "Row count for monitored tables",
    ["table", "dag"],
)

volume_deviation_gauge = Gauge(
    "observakit_volume_deviation_pct",
    "Volume deviation fraction from rolling average",
    ["table", "dag"],
)

MIN_HISTORY_FOR_ANOMALY = 3  # Require at least this many past records before firing anomaly

# ---------------------------------------------------------------------------
# Safe assertion evaluator
# ---------------------------------------------------------------------------
_SAFE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _safe_eval_assertion(expression: str, result_value) -> bool:
    """
    Evaluate a simple comparison assertion like 'result == 0' or 'result >= 100'
    without using eval(). Only comparisons between 'result' and a numeric literal
    are supported. Raises ValueError on unsupported expressions.
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid assertion syntax: {expression!r}") from e

    node = tree.body
    if not isinstance(node, ast.Compare):
        raise ValueError(
            f"Assertion must be a simple comparison (e.g. 'result == 0'), got: {expression!r}"
        )
    if len(node.ops) != 1 or len(node.comparators) != 1:
        raise ValueError(
            f"Only single comparisons are supported, got: {expression!r}"
        )

    left = node.left
    op = node.ops[0]
    right = node.comparators[0]

    # Left side must be the name 'result'
    if not (isinstance(left, ast.Name) and left.id == "result"):
        raise ValueError(
            f"Left side of assertion must be 'result', got: {ast.dump(left)!r}"
        )

    # Right side must be a numeric constant (int or float)
    if isinstance(right, ast.Constant) and isinstance(right.value, (int, float)):
        rhs = right.value
    else:
        raise ValueError(
            f"Right side of assertion must be a numeric literal, got: {ast.dump(right)!r}"
        )

    op_fn = _SAFE_OPS.get(type(op))
    if op_fn is None:
        raise ValueError(f"Unsupported comparison operator in assertion: {expression!r}")

    return bool(op_fn(result_value, rhs))


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
    try:
        config = load_config("config/kit.yml")
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

            # Evaluate assertion using a safe restricted evaluator
            passed = False
            try:
                passed = _safe_eval_assertion(assertion, result_value)
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
                    message=f"Table: {table}\nCheck: {name}\nResult: {result_value}\nAssertion: {assertion}{impact_msg}",
                    db=db,
                    severity="fail"
                )

        except Exception as e:
            logger.error(f"Error running custom SQL check {check_cfg.get('name')}: {e}")

    # --- Run Cross-Table Consistency Checks ---
    if not dry_run:
        consistency_results = run_consistency_checks(connector, db)
        all_results.extend(consistency_results)

    if not dry_run:
        db.commit()
    return {"engine": engine_name, "checks_run": len(all_results), "results": all_results, "dry_run": dry_run}


def _run_soda_check(check_file: str, connector) -> list[dict]:
    """
    Execute Soda Core checks via subprocess using Soda's stable JSON output.
    The Python API (scan.get_checks_fail()) accesses private attributes that
    change between Soda versions. The subprocess approach uses the public CLI contract.
    """
    soda_config = connector.get_soda_config()

    # Write a temp datasource config file for this run
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as cfg_file:
        yaml.dump(soda_config, cfg_file)
        cfg_path = cfg_file.name

    try:
        result = subprocess.run(
            ["soda", "scan", "-d", "my_postgres", "-c", cfg_path, check_file, "--json-output"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        # Parse JSON output from stdout
        return _parse_soda_json_output(result.stdout, result.returncode, check_file)

    except FileNotFoundError:
        logger.error("'soda' CLI not found. Install soda-core-postgres with: pip install soda-core-postgres")
        return [{"check_name": "soda_init", "table_name": "unknown", "passed": False,
                 "details": "soda CLI not found — install soda-core-postgres"}]
    except subprocess.TimeoutExpired:
        logger.error(f"Soda scan timed out for {check_file}")
        return [{"check_name": "soda_timeout", "table_name": "unknown", "passed": False,
                 "details": f"Scan timed out after 300s: {check_file}"}]
    finally:
        os.unlink(cfg_path)


def _parse_soda_json_output(stdout: str, returncode: int, check_file: str) -> list[dict]:
    """Parse Soda's --json-output into ObservaKit check result dicts."""
    results = []
    try:
        # Soda prints one JSON object per line in some versions, or a single array
        lines = [line.strip() for line in stdout.splitlines() if line.strip().startswith("{") or line.strip().startswith("[")]
        if not lines:
            # No JSON output — treat as failed scan
            logger.warning(f"No JSON output from soda scan of {check_file} (rc={returncode})")
            return [{"check_name": "soda_scan", "table_name": "unknown",
                     "passed": returncode == 0, "details": "No structured output from soda"}]

        raw = json.loads("\n".join(lines)) if len(lines) == 1 else json.loads(lines[0])

        # Soda JSON schema: {"checks": [{"name": ..., "outcome": "pass"|"fail", "table": ...}]}
        checks = raw.get("checks", []) if isinstance(raw, dict) else raw
        for check in checks:
            outcome = check.get("outcome", "fail").lower()
            results.append({
                "check_name": check.get("name", "unnamed"),
                "table_name": check.get("table", "unknown"),
                "passed": outcome == "pass",
                "metric_value": check.get("measured_value"),
                "details": check.get("definition", ""),
            })
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Could not parse Soda JSON output: {e} — treating as {'pass' if returncode == 0 else 'fail'}")
        results.append({"check_name": "soda_scan", "table_name": "unknown",
                        "passed": returncode == 0, "details": stdout[:500]})

    return results


def _run_gx_check(check_file: str, connector) -> list[dict]:
    """Execute Great Expectations checks.

    NOTE: GX integration is not yet implemented. Configure engine: soda in kit.yml
    or contribute a GX runner to connectors/gx_runner.py.
    """
    logger.warning(
        f"Great Expectations engine selected for {check_file} but is not yet implemented. "
        "Switch to engine: soda in kit.yml or implement GX execution logic."
    )
    return [{
        "check_name": "gx_not_implemented",
        "table_name": "unknown",
        "passed": False,
        "details": (
            "Great Expectations execution is not implemented. "
            "Use engine: soda in kit.yml or add a GX runner."
        ),
    }]


@router.post("/volume")
def run_volume_checks(db: Session = Depends(get_db), connector=None):
    """
    Run volume anomaly detection.
    Queries current row counts, compares against 7-day rolling average.
    Accepts an optional pre-built connector for connection reuse from scheduler.
    """
    try:
        config = load_config("config/kit.yml")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/kit.yml not found")

    volume_config = config.get("volume", {})
    if not volume_config.get("enabled", False):
        return {"message": "Volume monitoring is disabled"}

    tables = volume_config.get("tables", [])
    window_days = volume_config.get("rolling_window_days", 7)
    results = []

    for table_cfg in tables:
        # Per-check enabled flag
        if not table_cfg.get("enabled", True):
            logger.debug("Skipping volume check for %s (enabled: false)", table_cfg.get("table"))
            continue

        table_name = table_cfg["table"]
        dag_id = table_cfg.get("dag_id", "")
        threshold = table_cfg.get("anomaly_threshold", 0.3)

        try:
            _connector = connector or get_warehouse_connector()
            current_count = _connector.get_row_count(table_name)

            # Calculate rolling average from stored history
            cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

            # Count history records to enforce minimum guard
            history_count = (
                db.query(func.count(VolumeRecord.id))
                .filter(
                    VolumeRecord.table_name == table_name,
                    VolumeRecord.recorded_at >= cutoff,
                )
                .scalar()
            )

            avg_result = (
                db.query(func.avg(VolumeRecord.row_count))
                .filter(
                    VolumeRecord.table_name == table_name,
                    VolumeRecord.recorded_at >= cutoff,
                )
                .scalar()
            )

            rolling_avg = float(avg_result) if avg_result else float(current_count)
            if rolling_avg > 0:
                deviation = abs(current_count - rolling_avg) / rolling_avg
            elif current_count > 0:
                # Table was empty historically but now has rows — treat as 100% growth
                deviation = 1.0
            else:
                deviation = 0.0

            # Only flag anomaly if we have enough history
            sufficient_history = history_count >= MIN_HISTORY_FOR_ANOMALY
            is_anomaly = sufficient_history and deviation > threshold

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

            # Update Prometheus gauges
            volume_gauge.labels(table=table_name, dag=dag_id).set(current_count)
            volume_deviation_gauge.labels(table=table_name, dag=dag_id).set(deviation)

            result = {
                "table": table_name,
                "row_count": current_count,
                "rolling_avg": round(rolling_avg, 1),
                "deviation_pct": round(deviation * 100, 1),
                "is_anomaly": is_anomaly,
                "history_points": history_count,
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
    downstream = get_lineage_impact(table)
    impact_msg = f"\n⚠️ Downstream impact: {', '.join(downstream)}" if downstream else ""

    message = (
        f"Volume Anomaly: {table}\n"
        f"  Current rows: {count:,}\n"
        f"  7-day average: {avg:,.0f}\n"
        f"  Deviation: {deviation * 100:.1f}%\n"
        f"  Detected at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        f"{impact_msg}"
    )
    
    dispatch_alert(
        alert_type="volume",
        table_name=table,
        subject=f"🔴 Volume Anomaly: {table}",
        message=message,
        db=db,
        severity="warn"
    )


def run_consistency_checks(connector, db: Session) -> list[dict]:
    """
    Execute cross-table consistency checks defined in kit.yml under 'consistency:'.
    Supports two check types:
      - row_count_match: verifies row counts of two tables match within tolerance
      - sum_match: verifies a column sum matches across two tables within tolerance_pct

    Returns a list of result dicts, each with check_name, passed, and details.
    """
    try:
        config = load_config("config/kit.yml")
    except FileNotFoundError:
        return []

    consistency_checks = config.get("consistency", [])
    if not consistency_checks:
        return []

    results = []
    for check_cfg in consistency_checks:
        name = check_cfg.get("name", "unnamed_consistency_check")
        check_type = check_cfg.get("check", "row_count_match")

        try:
            if check_type == "row_count_match":
                table_a = check_cfg["table_a"]
                table_b = check_cfg["table_b"]
                join_key = check_cfg.get("join_key")
                tolerance = int(check_cfg.get("tolerance", 0))

                if join_key:
                    # Count rows in A not in B
                    q = f"""
                        SELECT COUNT(*) as cnt FROM {table_a} a
                        WHERE NOT EXISTS (
                            SELECT 1 FROM {table_b} b WHERE b.{join_key} = a.{join_key}
                        )
                    """
                    rows = connector.execute_query(q)
                    unmatched = int(rows[0]["cnt"]) if rows else 0
                    passed = unmatched <= tolerance
                    details = f"Unmatched rows: {unmatched} (tolerance: {tolerance})"
                else:
                    count_a_rows = connector.execute_query(f"SELECT COUNT(*) as cnt FROM {table_a}")
                    count_b_rows = connector.execute_query(f"SELECT COUNT(*) as cnt FROM {table_b}")
                    count_a = int(count_a_rows[0]["cnt"]) if count_a_rows else 0
                    count_b = int(count_b_rows[0]["cnt"]) if count_b_rows else 0
                    diff = abs(count_a - count_b)
                    passed = diff <= tolerance
                    details = f"{table_a}={count_a:,} rows, {table_b}={count_b:,} rows, diff={diff:,} (tolerance: {tolerance})"

            elif check_type == "sum_match":
                table_a = check_cfg["table_a"]
                table_b = check_cfg["table_b"]
                col_a = check_cfg["column_a"]
                col_b = check_cfg["column_b"]
                tolerance_pct = float(check_cfg.get("tolerance_pct", 0.0))

                sum_a_rows = connector.execute_query(f"SELECT COALESCE(SUM({col_a}), 0) as total FROM {table_a}")
                sum_b_rows = connector.execute_query(f"SELECT COALESCE(SUM({col_b}), 0) as total FROM {table_b}")
                sum_a = float(sum_a_rows[0]["total"]) if sum_a_rows else 0.0
                sum_b = float(sum_b_rows[0]["total"]) if sum_b_rows else 0.0
                max_val = max(abs(sum_a), abs(sum_b), 1.0)
                actual_pct = abs(sum_a - sum_b) / max_val
                passed = actual_pct <= tolerance_pct
                details = (
                    f"{table_a}.{col_a}={sum_a:,.2f}, {table_b}.{col_b}={sum_b:,.2f}, "
                    f"drift={actual_pct * 100:.3f}% (tolerance: {tolerance_pct * 100:.2f}%)"
                )

            else:
                logger.warning(f"Unknown consistency check type: {check_type}")
                continue

            record = CheckResult(
                check_name=name,
                table_name=check_cfg.get("table_a", "cross-table"),
                check_type="consistency",
                passed=passed,
                details=details,
                executed_at=datetime.now(timezone.utc),
            )
            db.add(record)
            results.append({"check_name": name, "check_type": check_type, "passed": passed, "details": details})

            if not passed:
                dispatch_alert(
                    alert_type="quality",
                    table_name=check_cfg.get("table_a"),
                    subject=f"❌ Consistency Check Failed: {name}",
                    message=f"Consistency check failed: {name}\n{details}",
                    db=db,
                    severity="fail"
                )

        except Exception as e:
            logger.error(f"Consistency check '{name}' failed: {e}")
            results.append({"check_name": name, "passed": False, "details": str(e)})

    return results
