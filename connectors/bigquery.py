"""
ObservaKit — BigQuery Warehouse Connector
Connects to Google BigQuery for freshness, volume, and schema queries.
"""

import os
import logging
from datetime import datetime
from typing import Optional

from connectors.base import WarehouseConnector

logger = logging.getLogger(__name__)


class BigQueryConnector(WarehouseConnector):
    """Google BigQuery warehouse connector."""

    def __init__(self):
        self._client = None
        self._project = os.getenv("BIGQUERY_PROJECT", "")
        self._dataset = os.getenv("BIGQUERY_DATASET", "")
        self._credentials_path = os.getenv("BIGQUERY_CREDENTIALS_PATH", "")

    def connect(self):
        """Establish connection to BigQuery."""
        if not self._client:
            try:
                from google.cloud import bigquery

                if self._credentials_path:
                    self._client = bigquery.Client.from_service_account_json(
                        self._credentials_path, project=self._project
                    )
                else:
                    self._client = bigquery.Client(project=self._project)
            except ImportError:
                raise ImportError(
                    "google-cloud-bigquery is required. Install with: "
                    "pip install google-cloud-bigquery"
                )
        return self._client

    def close(self):
        """Close the BigQuery client."""
        if self._client:
            self._client.close()
            self._client = None

    def get_max_timestamp(self, table: str, column: str) -> Optional[datetime]:
        """Get the max value of a timestamp column."""
        client = self.connect()
        full_table = f"{self._project}.{self._dataset}.{table.split('.')[-1]}"
        query = f"SELECT MAX(`{column}`) as max_ts FROM `{full_table}`"

        try:
            result = client.query(query).result()
            for row in result:
                return row.max_ts
            return None
        except Exception as e:
            logger.error(f"BigQuery error getting max timestamp for {table}.{column}: {e}")
            raise

    def get_row_count(self, table: str) -> int:
        """Get the current row count of a table."""
        client = self.connect()
        full_table = f"{self._project}.{self._dataset}.{table.split('.')[-1]}"
        query = f"SELECT COUNT(*) as cnt FROM `{full_table}`"

        try:
            result = client.query(query).result()
            for row in result:
                return row.cnt
            return 0
        except Exception as e:
            logger.error(f"BigQuery error getting row count for {table}: {e}")
            raise

    def get_schema(self, table: str) -> list[dict]:
        """Get schema from INFORMATION_SCHEMA.COLUMNS."""
        client = self.connect()
        table_name = table.split(".")[-1]
        query = f"""
            SELECT
                column_name AS name,
                data_type AS type,
                is_nullable AS nullable,
                ordinal_position
            FROM `{self._project}.{self._dataset}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{table_name}'
            ORDER BY ordinal_position
        """

        try:
            result = client.query(query).result()
            return [dict(row) for row in result]
        except Exception as e:
            logger.error(f"BigQuery error getting schema for {table}: {e}")
            raise

    def execute_query(self, query: str, params: dict = None) -> list[dict]:
        """Execute a raw SQL query."""
        client = self.connect()
        try:
            job_config = None
            if params:
                from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

                job_config = QueryJobConfig(
                    query_parameters=[
                        ScalarQueryParameter(k, "STRING", v) for k, v in params.items()
                    ]
                )
            result = client.query(query, job_config=job_config).result()
            return [dict(row) for row in result]
        except Exception as e:
            logger.error(f"BigQuery error executing query: {e}")
            raise
