"""
ObservaKit — dbt Artifact Watcher

Polls the dbt project's `target/run_results.json` for changes and auto-ingests
results into the ObservaKit metadata store when a new dbt run is detected.

Configured via kit.yml under the `dbt:` block:
    dbt:
      enabled: true
      project_dir: /path/to/dbt/project
      auto_parse_on_run: true
      poll_interval_minutes: 5
      expose_model_freshness: true

No new dependencies required — uses APScheduler polling already in the scheduler.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _last_modified(path: Path) -> float | None:
    """Return mtime of path, or None if it doesn't exist."""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


# Module-level cache: path -> last mtime we processed
_last_seen: dict[str, float] = {}


def poll_dbt_artifacts(db=None) -> dict:
    """
    Called by the scheduler. Checks whether run_results.json is newer than the
    last time we processed it. If so, delegates to parse_artifacts.parse_run_results().

    Returns a summary dict: {"status": "ok"|"skipped"|"error", ...}
    """
    from config.loader import load_config

    try:
        config = load_config("config/kit.yml")
    except FileNotFoundError:
        return {"status": "skipped", "reason": "config/kit.yml not found"}

    dbt_cfg = config.get("dbt", {})
    if not dbt_cfg.get("enabled", False):
        return {"status": "skipped", "reason": "dbt.enabled is false in kit.yml"}

    if not dbt_cfg.get("auto_parse_on_run", True):
        return {"status": "skipped", "reason": "dbt.auto_parse_on_run is false"}

    project_dir = dbt_cfg.get("project_dir", "")
    if not project_dir:
        logger.warning("dbt.project_dir not set in kit.yml — skipping dbt watcher")
        return {"status": "skipped", "reason": "dbt.project_dir not configured"}

    run_results_path = Path(project_dir) / "target" / "run_results.json"
    current_mtime = _last_modified(run_results_path)

    if current_mtime is None:
        return {"status": "skipped", "reason": f"{run_results_path} does not exist"}

    key = str(run_results_path)
    if _last_seen.get(key) == current_mtime:
        return {"status": "skipped", "reason": "run_results.json unchanged since last check"}

    # New run detected — parse it
    logger.info(f"New dbt run detected ({run_results_path}) — ingesting artifacts")
    try:
        from dbt_integration.parse_artifacts import parse_run_results, parse_manifest

        # Ingest run results
        manifest_path = run_results_path.parent / "manifest.json"
        results_ingested = parse_run_results(str(run_results_path))

        # Optionally ingest lineage from manifest
        if manifest_path.exists():
            parse_manifest(str(manifest_path))

        # Optionally expose dbt model freshness into FreshnessRecord
        if dbt_cfg.get("expose_model_freshness", False) and db is not None:
            _ingest_dbt_freshness(str(run_results_path), db)

        _last_seen[key] = current_mtime
        logger.info(f"dbt artifact ingestion complete: {results_ingested} results processed")
        return {"status": "ok", "results_ingested": results_ingested, "path": str(run_results_path)}

    except Exception as e:
        logger.error(f"dbt artifact ingestion failed: {e}")
        return {"status": "error", "error": str(e)}


def _ingest_dbt_freshness(run_results_path: str, db) -> None:
    """
    Parse dbt run results and create FreshnessRecord entries for each model.
    A model that ran successfully at time T is treated as "fresh" at T.
    A failed model is recorded as status='fail'.
    """
    import json
    from backend.models import FreshnessRecord

    try:
        with open(run_results_path) as f:
            run_results = json.load(f)
    except Exception as e:
        logger.error(f"Could not read dbt run_results.json: {e}")
        return

    generated_at_str = run_results.get("metadata", {}).get("generated_at")
    try:
        generated_at = datetime.fromisoformat(generated_at_str.replace("Z", "+00:00"))
    except Exception:
        generated_at = datetime.now(timezone.utc)

    for result in run_results.get("results", []):
        unique_id = result.get("unique_id", "")
        # Only handle model nodes (not tests, seeds, etc.)
        if not unique_id.startswith("model."):
            continue

        node = result.get("node", {})
        table_name = f"{node.get('schema', 'public')}.{node.get('name', unique_id)}"
        status = result.get("status", "error")
        obs_status = "ok" if status in ("success", "pass") else "fail"

        record = FreshnessRecord(
            table_name=table_name,
            timestamp_column="__dbt_run__",
            last_updated_at=generated_at,
            lag_seconds=0.0,
            status=obs_status,
            checked_at=datetime.now(timezone.utc),
        )
        db.add(record)

    db.commit()
    logger.info("dbt freshness records written to FreshnessRecord table")
