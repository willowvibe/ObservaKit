"""
ObservaKit — Connector Tests
"""

from unittest.mock import patch

import pytest

from connectors.base import get_warehouse_connector


class TestWarehouseConnectorFactory:
    """Test the warehouse connector factory."""

    @patch.dict("os.environ", {"WAREHOUSE_TYPE": "postgres"})
    def test_postgres_connector(self):
        connector = get_warehouse_connector()
        from connectors.postgres import PostgresConnector

        assert isinstance(connector, PostgresConnector)

    @patch.dict("os.environ", {"WAREHOUSE_TYPE": "bigquery"})
    def test_bigquery_connector(self):
        connector = get_warehouse_connector()
        from connectors.bigquery import BigQueryConnector

        assert isinstance(connector, BigQueryConnector)

    @patch.dict("os.environ", {"WAREHOUSE_TYPE": "snowflake"})
    def test_snowflake_connector(self):
        connector = get_warehouse_connector()
        from connectors.snowflake import SnowflakeConnector

        assert isinstance(connector, SnowflakeConnector)

    @patch.dict("os.environ", {"WAREHOUSE_TYPE": "unsupported"})
    def test_unsupported_connector_raises(self):
        with pytest.raises(ValueError, match="Unsupported warehouse type"):
            get_warehouse_connector()


class TestMockPostgresConnector:
    """Test PostgreSQL connector methods with mock."""

    def test_get_schema_returns_list(self, mock_postgres_connector):
        schema = mock_postgres_connector.get_schema("public.orders")
        assert isinstance(schema, list)
        assert len(schema) == 4
        assert schema[0]["name"] == "id"

    def test_get_row_count(self, mock_postgres_connector):
        count = mock_postgres_connector.get_row_count("public.orders")
        assert count == 1000

    def test_get_max_timestamp(self, mock_postgres_connector):
        result = mock_postgres_connector.get_max_timestamp("public.orders", "updated_at")
        assert result is None  # Default mock returns None


class TestMockAirflowConnector:
    """Test Airflow connector methods with mock."""

    def test_list_dags(self, mock_airflow_connector):
        dags = mock_airflow_connector.list_dags()
        assert len(dags) == 1
        assert dags[0]["dag_id"] == "load_orders"

    def test_get_dag_runs(self, mock_airflow_connector):
        runs = mock_airflow_connector.get_dag_runs("load_orders")
        assert len(runs) == 1
        assert runs[0]["state"] == "success"
        assert runs[0]["duration"] == 300
