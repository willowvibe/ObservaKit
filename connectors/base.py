"""
ObservaKit — Base Connector Classes
Abstract base classes for warehouse and orchestrator connectors.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional


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
    else:
        raise ValueError(f"Unsupported warehouse type: {warehouse_type}")


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
