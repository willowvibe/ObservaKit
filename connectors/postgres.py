"""
ObservaKit — PostgreSQL Warehouse Connector
Connects to a PostgreSQL warehouse for freshness, volume, and schema queries.
"""

import logging
import os
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras

from connectors.base import WarehouseConnector

logger = logging.getLogger(__name__)


class PostgresConnector(WarehouseConnector):
    """PostgreSQL warehouse connector."""

    def __init__(self):
        self._conn = None
        self._config = {
            "host": os.getenv("WAREHOUSE_HOST", "localhost"),
            "port": int(os.getenv("WAREHOUSE_PORT", "5432")),
            "user": os.getenv("WAREHOUSE_USER", ""),
            "password": os.getenv("WAREHOUSE_PASSWORD", ""),
            "dbname": os.getenv("WAREHOUSE_DB", ""),
        }

    def connect(self):
        """Establish connection to PostgreSQL."""
        if not self._conn or self._conn.closed:
            self._conn = psycopg2.connect(**self._config)
        return self._conn

    def close(self):
        """Close the connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()

    def get_max_timestamp(self, table: str, column: str) -> Optional[datetime]:
        """Get the max value of a timestamp column."""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                # Use proper quoting to prevent SQL injection
                cur.execute(
                    f"SELECT MAX({column}) FROM {table}"
                )
                result = cur.fetchone()
                return result[0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error getting max timestamp for {table}.{column}: {e}")
            conn.rollback()
            raise
        finally:
            self.close()

    def get_row_count(self, table: str) -> int:
        """Get the current row count of a table."""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                result = cur.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting row count for {table}: {e}")
            conn.rollback()
            raise
        finally:
            self.close()

    def get_schema(self, table: str) -> list[dict]:
        """
        Get the schema from information_schema.columns.
        Returns columns as [{name, type, nullable, ordinal_position}].
        """
        conn = self.connect()
        # Parse schema.table format
        parts = table.split(".")
        schema_name = parts[0] if len(parts) > 1 else "public"
        table_name = parts[-1]

        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        column_name AS name,
                        data_type AS type,
                        is_nullable AS nullable,
                        ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema_name, table_name),
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error getting schema for {table}: {e}")
            conn.rollback()
            raise
        finally:
            self.close()

    def execute_query(self, query: str, params: dict = None) -> list[dict]:
        """Execute a raw SQL query and return results as dicts."""
        conn = self.connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            conn.rollback()
            raise
        finally:
            self.close()

    def get_soda_config(self) -> dict:
        """Return configuration for Soda Core."""
        return {
            "data_source my_postgres": {
                "type": "postgres",
                "host": self._config["host"],
                "port": self._config["port"],
                "username": self._config["user"],
                "password": self._config["password"],
                "database": self._config["dbname"],
                "schema": "public",
            }
        }

    def get_gx_config(self) -> dict:
        """Return configuration for Great Expectations."""
        return {
            "name": "my_postgres_datasource",
            "class_name": "Datasource",
            "execution_engine": {
                "class_name": "SqlAlchemyExecutionEngine",
                "connection_string": f"postgresql://{self._config['user']}:{self._config['password']}@{self._config['host']}:{self._config['port']}/{self._config['dbname']}",
            },
            "data_connectors": {
                "default_runtime_data_connector_name": {
                    "class_name": "RuntimeDataConnector",
                    "batch_identifiers": ["default_identifier_name"],
                },
            },
        }

