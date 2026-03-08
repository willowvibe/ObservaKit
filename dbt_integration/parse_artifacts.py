import json
import logging
import os
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Wait for backend imports dynamically in case of standalone execution
try:
    from backend.models import CheckResult, PipelineRun
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backend.models import CheckResult, PipelineRun

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Try to get DB URL from environment, or use hardcoded default for simple execution
DATABASE_URL = os.getenv("METADATA_DB_URL", "postgresql://observakit:observakit123@localhost:5432/observakit")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def parse_run_results(run_results_path: str, manifest_path: str):
    """Parses dbt run_results.json and manifest.json into the DB."""

    if not os.path.exists(run_results_path):
        logger.error(f"Cannot find run_results.json at {run_results_path}")
        return

    if not os.path.exists(manifest_path):
        logger.error(f"Cannot find manifest.json at {manifest_path}")
        return

    db = SessionLocal()
    try:
        with open(run_results_path, 'r') as f:
            run_results = json.load(f)

        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        invocation_id = run_results.get("metadata", {}).get("invocation_id")
        created_at_str = run_results.get("metadata", {}).get("generated_at")

        # Parse the timestamp with fallback
        try:
            timestamp = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            timestamp = datetime.utcnow()

        # Iterate over results
        for result in run_results.get("results", []):
            unique_id = result.get("unique_id")
            status = result.get("status")
            execution_time = result.get("execution_time", 0.0)

            node_info = manifest.get("nodes", {}).get(unique_id, {})
            if not node_info:
                # Might be a test or macro, check broader dicts if needed
                node_info = manifest.get("sources", {}).get(unique_id, manifest.get("metrics", {}).get(unique_id, {}))

            resource_type = node_info.get("resource_type", "unknown")

            # --- 1. Top-Level Models/Seeds (Pipeline Runs) ---
            if resource_type in ["model", "seed", "snapshot"]:
                run = PipelineRun(
                    pipeline_name="dbt_core",
                    run_id=f"dbt_{invocation_id}_{unique_id}",
                    status=status,
                    duration_seconds=execution_time,
                    timestamp=timestamp
                )
                db.add(run)

            # --- 2. Tests (Quality Checks) ---
            elif resource_type == "test":
                # Sometimes tests are on whole models
                test_table = node_info.get("attached_node", "unknown").split(".")[-1]

                check = CheckResult(
                    table_name=test_table,
                    check_name=str(unique_id),
                    check_type="dbt_test",
                    status="passed" if status == "pass" else "failed",
                    details={"error_message": str(result.get("message", "")), "execution_time": execution_time},
                    timestamp=timestamp
                )
                db.add(check)

        db.commit()
        logger.info(f"Successfully processed dbt artifacts for invocation {invocation_id}")

    except Exception as e:
        logger.error(f"Failed to parse dbt artifacts: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Parse dbt artifacts into ObservaKit metadata DB.")
    parser.add_argument("--run-results", type=str, required=True, help="Path to run_results.json")
    parser.add_argument("--manifest", type=str, required=True, help="Path to manifest.json")

    args = parser.parse_args()
    parse_run_results(args.run_results, args.manifest)
