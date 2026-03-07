"""
ObservaKit — Airflow REST API Connector
Pulls DAG run status, task durations, and SLA misses from Airflow.
"""

import os
import logging
from typing import Optional

import httpx

from connectors.base import OrchestratorConnector

logger = logging.getLogger(__name__)


class AirflowConnector(OrchestratorConnector):
    """Airflow REST API connector."""

    def __init__(self):
        self._base_url = os.getenv("AIRFLOW_BASE_URL", "http://localhost:8080")
        self._username = os.getenv("AIRFLOW_USERNAME", "admin")
        self._password = os.getenv("AIRFLOW_PASSWORD", "admin")

    @property
    def _auth(self):
        return (self._username, self._password)

    def _api_url(self, path: str) -> str:
        return f"{self._base_url}/api/v1{path}"

    def list_dags(self) -> list[dict]:
        """List all available DAGs."""
        try:
            resp = httpx.get(self._api_url("/dags"), auth=self._auth, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "dag_id": dag["dag_id"],
                    "is_paused": dag.get("is_paused", False),
                    "description": dag.get("description", ""),
                    "schedule_interval": dag.get("schedule_interval", {}).get("value", ""),
                }
                for dag in data.get("dags", [])
            ]
        except Exception as e:
            logger.error(f"Error listing Airflow DAGs: {e}")
            raise

    def get_dag_runs(self, dag_id: str, limit: int = 25) -> list[dict]:
        """Get recent DAG runs."""
        try:
            resp = httpx.get(
                self._api_url(f"/dags/{dag_id}/dagRuns"),
                auth=self._auth,
                params={"limit": limit, "order_by": "-start_date"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "dag_id": run["dag_id"],
                    "run_id": run["dag_run_id"],
                    "state": run["state"],
                    "start_date": run.get("start_date"),
                    "end_date": run.get("end_date"),
                    "duration": self._calc_duration(run.get("start_date"), run.get("end_date")),
                }
                for run in data.get("dag_runs", [])
            ]
        except Exception as e:
            logger.error(f"Error getting Airflow DAG runs for {dag_id}: {e}")
            raise

    def get_dag_run_status(self, dag_id: str, run_id: str) -> dict:
        """Get the status of a specific DAG run."""
        try:
            resp = httpx.get(
                self._api_url(f"/dags/{dag_id}/dagRuns/{run_id}"),
                auth=self._auth,
                timeout=30,
            )
            resp.raise_for_status()
            run = resp.json()
            return {
                "dag_id": run["dag_id"],
                "run_id": run["dag_run_id"],
                "state": run["state"],
                "start_date": run.get("start_date"),
                "end_date": run.get("end_date"),
            }
        except Exception as e:
            logger.error(f"Error getting Airflow DAG run status: {e}")
            raise

    def get_task_instances(self, dag_id: str, run_id: str) -> list[dict]:
        """Get task instances for a DAG run."""
        try:
            resp = httpx.get(
                self._api_url(f"/dags/{dag_id}/dagRuns/{run_id}/taskInstances"),
                auth=self._auth,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "task_id": task["task_id"],
                    "state": task["state"],
                    "start_date": task.get("start_date"),
                    "end_date": task.get("end_date"),
                    "duration": task.get("duration"),
                    "try_number": task.get("try_number", 1),
                }
                for task in data.get("task_instances", [])
            ]
        except Exception as e:
            logger.error(f"Error getting Airflow task instances: {e}")
            raise

    def get_sla_misses(self, dag_id: Optional[str] = None) -> list[dict]:
        """Get SLA misses (Airflow 2.x endpoint)."""
        try:
            params = {}
            if dag_id:
                params["dag_id"] = dag_id
            resp = httpx.get(
                self._api_url("/dags/~/dagRuns/~/taskInstances/~/slaEvents"),
                auth=self._auth,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("sla_misses", [])
        except Exception as e:
            logger.warning(f"SLA misses endpoint not available: {e}")
            return []

    @staticmethod
    def _calc_duration(start: Optional[str], end: Optional[str]) -> Optional[float]:
        """Calculate duration in seconds between two ISO datetime strings."""
        if not start or not end:
            return None
        from datetime import datetime

        try:
            s = datetime.fromisoformat(start.replace("Z", "+00:00"))
            e = datetime.fromisoformat(end.replace("Z", "+00:00"))
            return (e - s).total_seconds()
        except (ValueError, AttributeError):
            return None
