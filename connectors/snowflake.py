"""
ObservaKit — Snowflake Warehouse Connector
Connects to Snowflake for freshness, volume, and schema queries.
"""

import logging
import os
from datetime import datetime
from typing import Optional

from connectors.base import WarehouseConnector, resilient_query

logger = logging.getLogger(__name__)


class SnowflakeConnector(WarehouseConnector):
    """Snowflake warehouse connector."""

    def __init__(self):
        self._conn = None
        self._config = {
            "account": os.getenv("SNOWFLAKE_ACCOUNT", ""),
            "user": os.getenv("SNOWFLAKE_USER", ""),
            "password": os.getenv("SNOWFLAKE_PASSWORD", ""),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", ""),
            "database": os.getenv("SNOWFLAKE_DATABASE", ""),
            "schema": os.getenv("SNOWFLAKE_SCHEMA", "public"),
        }

    def connect(self):
        """Establish connection to Snowflake."""
        if not self._conn or self._conn.is_closed():
            try:
                import snowflake.connector

                self._conn = snowflake.connector.connect(**self._config)
            except ImportError:
                raise ImportError(
                    "snowflake-connector-python is required. Install with: "
                    "pip install snowflake-connector-python"
                )
        return self._conn

    def close(self):
        """Close the Snowflake connection."""
        if self._conn and not self._conn.is_closed():
            self._conn.close()

    @resilient_query()
    def get_max_timestamp(self, table: str, column: str) -> Optional[datetime]:
        """Get the max value of a timestamp column."""
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT MAX({column}) FROM {table}")
            result = cur.fetchone()
            return result[0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Snowflake error getting max timestamp for {table}.{column}: {e}")
            # Close on error so the next connect() gets a fresh connection
            self.close()
            raise

    @resilient_query()
    def get_row_count(self, table: str) -> int:
        """Get the current row count of a table."""
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            result = cur.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Snowflake error getting row count for {table}: {e}")
            self.close()
            raise

    @resilient_query()
    def get_schema(self, table: str) -> list[dict]:
        """Get schema from INFORMATION_SCHEMA.COLUMNS."""
        conn = self.connect()
        parts = table.split(".")
        schema_name = parts[0] if len(parts) > 1 else self._config["schema"]
        table_name = parts[-1]

        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COLUMN_NAME AS name,
                    DATA_TYPE AS type,
                    IS_NULLABLE AS nullable,
                    ORDINAL_POSITION AS ordinal_position
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                (schema_name.upper(), table_name.upper()),
            )
            columns = cur.description
            return [
                dict(zip([col[0].lower() for col in columns], row))
                for row in cur.fetchall()
            ]
        except Exception as e:
            logger.error(f"Snowflake error getting schema for {table}: {e}")
            self.close()
            raise

    @resilient_query()
    def execute_query(self, query: str, params: dict = None) -> list[dict]:
        """Execute a raw SQL query."""
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            columns = cur.description
            return [
                dict(zip([col[0].lower() for col in columns], row))
                for row in cur.fetchall()
            ]
        except Exception as e:
            logger.error(f"Snowflake error executing query: {e}")
            self.close()
            raise

    @resilient_query()
    def get_compute_costs(self, days: int = 7) -> float:
        """Get compute credits used over the last N days."""
        conn = self.connect()
        query = f"""
            SELECT SUM(CREDITS_USED) as total_credits
            FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
            WHERE START_TIME >= DATEADD(day, -{days}, CURRENT_TIMESTAMP())
        """
        try:
            cur = conn.cursor()
            cur.execute(query)
            result = cur.fetchone()
            return float(result[0]) if result and result[0] else 0.0
        except Exception as e:
            logger.error(f"Snowflake error getting compute costs: {e}")
            self.close()
            return 0.0

    def get_soda_config(self) -> dict:
        """Return configuration for Soda Core."""
        return {
            "data_source warehouse": {
                "type": "snowflake",
                "connection": {
                    "username": self._config["user"],
                    "password": self._config["password"],
                    "account": self._config["account"],
                    "database": self._config["database"],
                    "warehouse": self._config["warehouse"],
                }
            }
        }

    def get_gx_config(self) -> dict:
        """Return configuration for Great Expectations."""
        return {}  # Placeholder for Snowflake GX config
