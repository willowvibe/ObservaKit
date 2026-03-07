"""
ObservaKit — Prefect API Connector
Pulls flow run status and task durations from Prefect.
"""

import os
import logging
from typing import Optional

import httpx

from connectors.base import OrchestratorConnector

logger = logging.getLogger(__name__)


class PrefectConnector(OrchestratorConnector):
    """Prefect API connector."""

    def __init__(self):
        self._api_url = os.getenv("PREFECT_API_URL", "http://localhost:4200/api")

    def list_dags(self) -> list[dict]:
        """List all available flows (Prefect calls them 'flows')."""
        try:
            resp = httpx.post(
                f"{self._api_url}/flows/filter",
                json={"limit": 100},
                timeout=30,
            )
            resp.raise_for_status()
            flows = resp.json()
            return [
                {
                    "dag_id": flow["name"],
                    "flow_id": flow["id"],
                    "description": flow.get("description", ""),
                }
                for flow in flows
            ]
        except Exception as e:
            logger.error(f"Error listing Prefect flows: {e}")
            raise

    def get_dag_runs(self, dag_id: str, limit: int = 25) -> list[dict]:
        """Get recent flow runs for a given flow name."""
        try:
            # First, get the flow ID
            resp = httpx.post(
                f"{self._api_url}/flows/filter",
                json={"flows": {"name": {"any_": [dag_id]}}},
                timeout=30,
            )
            resp.raise_for_status()
            flows = resp.json()

            if not flows:
                return []

            flow_id = flows[0]["id"]

            # Get flow runs
            resp = httpx.post(
                f"{self._api_url}/flow_runs/filter",
                json={
                    "flow_runs": {"flow_id": {"any_": [flow_id]}},
                    "limit": limit,
                    "sort": "START_TIME_DESC",
                },
                timeout=30,
            )
            resp.raise_for_status()
            runs = resp.json()

            return [
                {
                    "dag_id": dag_id,
                    "run_id": run["id"],
                    "state": run.get("state_type", "unknown"),
                    "start_date": run.get("start_time"),
                    "end_date": run.get("end_time"),
                    "duration": run.get("total_run_time"),
                }
                for run in runs
            ]
        except Exception as e:
            logger.error(f"Error getting Prefect flow runs for {dag_id}: {e}")
            raise

    def get_dag_run_status(self, dag_id: str, run_id: str) -> dict:
        """Get the status of a specific flow run."""
        try:
            resp = httpx.get(
                f"{self._api_url}/flow_runs/{run_id}",
                timeout=30,
            )
            resp.raise_for_status()
            run = resp.json()
            return {
                "dag_id": dag_id,
                "run_id": run["id"],
                "state": run.get("state_type", "unknown"),
                "start_date": run.get("start_time"),
                "end_date": run.get("end_time"),
            }
        except Exception as e:
            logger.error(f"Error getting Prefect flow run status: {e}")
            raise

    def get_task_instances(self, dag_id: str, run_id: str) -> list[dict]:
        """Get task runs for a flow run."""
        try:
            resp = httpx.post(
                f"{self._api_url}/task_runs/filter",
                json={
                    "task_runs": {"flow_run_id": {"any_": [run_id]}},
                    "limit": 200,
                },
                timeout=30,
            )
            resp.raise_for_status()
            tasks = resp.json()

            return [
                {
                    "task_id": task["name"],
                    "state": task.get("state_type", "unknown"),
                    "start_date": task.get("start_time"),
                    "end_date": task.get("end_time"),
                    "duration": task.get("total_run_time"),
                }
                for task in tasks
            ]
        except Exception as e:
            logger.error(f"Error getting Prefect task runs: {e}")
            raise
