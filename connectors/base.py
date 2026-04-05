"""
ObservaKit — Base Connector Classes
Abstract base classes for warehouse and orchestrator connectors.
"""

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

def resilient_query():
    """
    Decorator for adding exponential backoff retries to warehouse queries.
    Useful for handling intermittent TCP drops or warehouse cold starts.
    """
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
        before_sleep=lambda retry_state: logger.warning(
            f"Transient warehouse error encountered. Retrying (attempt {retry_state.attempt_number})..."
        )
    )


class WarehouseConnector(ABC):
    """Abstract base class for warehouse connectors."""

    @abstractmethod
    def connect(self):
        """Establish connection to the warehouse."""
        ...

    @abstractmethod
    def close(self):
        """Close the warehouse connection."""
        ...

    @abstractmethod
    def get_max_timestamp(self, table: str, column: str) -> Optional[datetime]:
        """Get the max value of a timestamp column in a table."""
        ...

    @abstractmethod
    def get_row_count(self, table: str) -> int:
        """Get the current row count of a table."""
        ...

    @abstractmethod
    def get_schema(self, table: str) -> list[dict]:
        """
        Get the schema of a table from information_schema.
        Returns: [{name, type, nullable, ordinal_position}]
        """
        ...

    @abstractmethod
    def execute_query(self, query: str, params: dict = None) -> list[dict]:
        """Execute a raw SQL query and return results as dicts."""
        ...

    @abstractmethod
    def get_soda_config(self) -> dict:
        """Return configuration for Soda Core."""
        ...

    @abstractmethod
    def get_gx_config(self) -> dict:
        """Return configuration for Great Expectations."""
        ...


class CostConnector(ABC):
    """Abstract base class for tracking compute costs."""

    @abstractmethod
    def get_compute_costs(self, days: int = 7) -> float:
        """Get the compute cost (credits or bytes billed) for the last N days."""
        ...


class OrchestratorConnector(ABC):
    """Abstract base class for orchestrator connectors (Airflow, Prefect)."""

    @abstractmethod
    def get_dag_runs(self, dag_id: str, limit: int = 25) -> list[dict]:
        """Get recent DAG/flow runs."""
        ...

    @abstractmethod
    def get_dag_run_status(self, dag_id: str, run_id: str) -> dict:
        """Get the status of a specific DAG/flow run."""
        ...

    @abstractmethod
    def get_task_instances(self, dag_id: str, run_id: str) -> list[dict]:
        """Get task instances for a DAG/flow run."""
        ...

    @abstractmethod
    def list_dags(self) -> list[dict]:
        """List all available DAGs/flows."""
        ...


def get_warehouse_connector() -> WarehouseConnector:
    """Factory: return the appropriate warehouse connector based on config."""
    warehouse_type = os.getenv("WAREHOUSE_TYPE", "postgres").lower()

    if warehouse_type == "postgres":
        from connectors.postgres import PostgresConnector
        return PostgresConnector()
    elif warehouse_type == "bigquery":
        from connectors.bigquery import BigQueryConnector
        return BigQueryConnector()
    elif warehouse_type == "snowflake":
        from connectors.snowflake import SnowflakeConnector
        return SnowflakeConnector()
    elif warehouse_type in ("mysql", "mariadb"):
        from connectors.mysql import MySQLConnector
        return MySQLConnector()
    elif warehouse_type == "redshift":
        from connectors.redshift import RedshiftConnector
        return RedshiftConnector()
    elif warehouse_type == "duckdb":
        from connectors.duckdb import DuckDBConnector
        return DuckDBConnector()
    elif warehouse_type == "databricks":
        from connectors.databricks import DatabricksConnector
        return DatabricksConnector()
    elif warehouse_type == "trino":
        from connectors.trino import TrinoConnector
        return TrinoConnector()
    else:
        raise ValueError(
            f"Unsupported warehouse type: '{warehouse_type}'. "
            f"Supported: postgres, bigquery, snowflake, mysql, mariadb, redshift, duckdb, databricks, trino"
        )


def get_orchestrator_connector() -> OrchestratorConnector:
    """Factory: return the appropriate orchestrator connector based on config."""
    import yaml

    try:
        with open("config/kit.yml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise RuntimeError("config/kit.yml not found")

    orch_type = config.get("orchestrator", {}).get("type", "airflow")

    if orch_type == "airflow":
        from connectors.airflow import AirflowConnector
        return AirflowConnector()
    elif orch_type == "prefect":
        from connectors.prefect import PrefectConnector
        return PrefectConnector()
    else:
        raise ValueError(f"Unsupported orchestrator type: {orch_type}")
