"""
ObservaKit — Schema Drift Detection Router
Snapshots information_schema and detects column-level changes.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.models import SchemaDiff, SchemaSnapshot, get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/snapshot")
def take_snapshot(db: Session = Depends(get_db)):
    """
    Snapshot the current schema for all configured tables and detect drift.
    """
    import yaml

    try:
        with open("config/kit.yml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/kit.yml not found")

    schema_config = config.get("schema_drift", {})
    if not schema_config.get("enabled", False):
        return {"message": "Schema drift detection is disabled"}

    tables = schema_config.get("tables", [])
    results = []

    for table_name in tables:
        try:
            from connectors.base import get_warehouse_connector

            connector = get_warehouse_connector()
            current_columns = connector.get_schema(table_name)

            # Get previous snapshot
            prev_snapshot = (
                db.query(SchemaSnapshot)
                .filter(SchemaSnapshot.table_name == table_name)
                .order_by(SchemaSnapshot.snapshot_at.desc())
                .first()
            )

            # Store new snapshot
            new_snapshot = SchemaSnapshot(
                table_name=table_name,
                columns_json=current_columns,
            )
            db.add(new_snapshot)

            # Compute diff if previous snapshot exists
            diffs = []
            if prev_snapshot:
                diffs = _compute_diff(table_name, prev_snapshot.columns_json, current_columns, db)

            results.append({
                "table": table_name,
                "column_count": len(current_columns),
                "changes": len(diffs),
                "diffs": diffs,
            })

            # Alert if changes detected
            if diffs and schema_config.get("alert"):
                _trigger_schema_alert(table_name, diffs, schema_config["alert"], db)

        except Exception as e:
            logger.error(f"Schema snapshot failed for {table_name}: {e}")
            results.append({"table": table_name, "error": str(e)})

    db.commit()
    return {"tables_checked": len(results), "results": results}


@router.get("/diff/{table_name}")
def get_schema_diff(
    table_name: str,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Get recent schema diffs for a table."""
    diffs = (
        db.query(SchemaDiff)
        .filter(SchemaDiff.table_name == table_name)
        .order_by(SchemaDiff.detected_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "change_type": d.change_type,
            "column_name": d.column_name,
            "old_value": d.old_value,
            "new_value": d.new_value,
            "detected_at": d.detected_at.isoformat(),
        }
        for d in diffs
    ]


@router.get("/snapshots/{table_name}")
def get_snapshots(
    table_name: str,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """Get recent schema snapshots for a table."""
    snapshots = (
        db.query(SchemaSnapshot)
        .filter(SchemaSnapshot.table_name == table_name)
        .order_by(SchemaSnapshot.snapshot_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": s.id,
            "table": s.table_name,
            "columns": s.columns_json,
            "snapshot_at": s.snapshot_at.isoformat(),
        }
        for s in snapshots
    ]


def _compute_diff(table_name: str, old_columns: list, new_columns: list, db: Session) -> list:
    """
    Compare two column snapshots and detect changes.
    Returns a list of detected changes.
    """
    old_map = {col["name"]: col for col in old_columns}
    new_map = {col["name"]: col for col in new_columns}

    diffs = []

    # Columns removed
    for name in old_map:
        if name not in new_map:
            diff = SchemaDiff(
                table_name=table_name,
                change_type="removed",
                column_name=name,
                old_value=old_map[name].get("type", ""),
                new_value=None,
            )
            db.add(diff)
            diffs.append({
                "change_type": "removed",
                "column": name,
                "old_type": old_map[name].get("type"),
            })

    # Columns added
    for name in new_map:
        if name not in old_map:
            diff = SchemaDiff(
                table_name=table_name,
                change_type="added",
                column_name=name,
                old_value=None,
                new_value=new_map[name].get("type", ""),
            )
            db.add(diff)
            diffs.append({
                "change_type": "added",
                "column": name,
                "new_type": new_map[name].get("type"),
            })

    # Type changes
    for name in old_map:
        if name in new_map:
            old_type = old_map[name].get("type", "")
            new_type = new_map[name].get("type", "")
            if old_type != new_type:
                diff = SchemaDiff(
                    table_name=table_name,
                    change_type="type_changed",
                    column_name=name,
                    old_value=old_type,
                    new_value=new_type,
                )
                db.add(diff)
                diffs.append({
                    "change_type": "type_changed",
                    "column": name,
                    "old_type": old_type,
                    "new_type": new_type,
                })

    return diffs


def _trigger_schema_alert(table: str, diffs: list, channel: str, db: Session):
    """Dispatch a schema drift alert."""
    from datetime import timedelta

    from alerts.base import get_alert_dispatcher
    from backend.models import AlertLog

    # Deduplication: skip if same table+type was alerted in the last 60 minutes
    recent = db.query(AlertLog).filter(
        AlertLog.table_name == table,
        AlertLog.alert_type == "schema",
        AlertLog.sent_at >= datetime.now(timezone.utc) - timedelta(minutes=60),
    ).first()
    if recent:
        logger.info(f"Skipping duplicate alert for {table} (last sent {recent.sent_at})")
        return

    changes_text = "\n".join(
        f"  - Column `{d['column']}` {d['change_type']}"
        + (
            f": {d.get('old_type', '')} → {d.get('new_type', '')}"
            if d["change_type"] == "type_changed"
            else ""
        )
        for d in diffs
    )
    message = (
        f"⚠️ Schema Drift Detected: {table}\n"
        f"{changes_text}\n"
        f"  Detected at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    success = False
    try:
        dispatcher = get_alert_dispatcher(channel)
        dispatcher.send(message)
        success = True
    except Exception as e:
        logger.error(f"Failed to send schema drift alert: {e}")

    # Log the alert for deduplication and audit
    alert_log = AlertLog(
        alert_type="schema",
        channel=channel,
        table_name=table,
        message=message,
        success=success,
    )
    db.add(alert_log)
