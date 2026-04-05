"""
ObservaKit — MySQL / MariaDB Warehouse Connector

Supports MySQL 5.7+ and MariaDB 10.3+.
Uses PyMySQL (pure-Python, no native libs required) so it works in Docker
without any extra OS packages.

Install: pip install observakit[mysql]  →  PyMySQL>=1.1.0
"""

import logging
import os
from datetime import datetime
from typing import Optional

from connectors.base import WarehouseConnector, resilient_query

logger = logging.getLogger(__name__)


class MySQLConnector(WarehouseConnector):
    """MySQL / MariaDB warehouse connector (via PyMySQL)."""

    def __init__(self):
        self._conn = None
        self._config = {
            "host": os.getenv("WAREHOUSE_HOST", "localhost"),
            "port": int(os.getenv("WAREHOUSE_PORT", "3306")),
            "user": os.getenv("WAREHOUSE_USER", ""),
            "password": os.getenv("WAREHOUSE_PASSWORD", ""),
            "database": os.getenv("WAREHOUSE_DB", ""),
            # PyMySQL-specific settings for production reliability
            "charset": "utf8mb4",
            "autocommit": True,
            "connect_timeout": 10,
        }

    def connect(self):
        """Establish (or re-use) a PyMySQL connection."""
        try:
            import pymysql
            import pymysql.cursors
        except ImportError:
            raise RuntimeError("PyMySQL is not installed. Run: pip install 'observakit[mysql]'")

        if self._conn is None or not self._conn.open:
            self._conn = pymysql.connect(**self._config)
        return self._conn

    def close(self):
        if self._conn and self._conn.open:
            self._conn.close()

    @resilient_query()
    def get_max_timestamp(self, table: str, column: str) -> Optional[datetime]:
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                # MySQL uses backtick quoting; split schema.table if provided
                cur.execute(f"SELECT MAX(`{column}`) FROM {_quote_table(table)}")
                result = cur.fetchone()
                return result[0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error getting max timestamp for {table}.{column}: {e}")
            raise

    @resilient_query()
    def get_row_count(self, table: str) -> int:
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {_quote_table(table)}")
                result = cur.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting row count for {table}: {e}")
            raise

    @resilient_query()
    def get_schema(self, table: str) -> list[dict]:
        """
        Returns columns from information_schema.
        MySQL stores schema in TABLE_SCHEMA / TABLE_NAME (uppercase).
        """
        conn = self.connect()
        parts = table.split(".")
        db_name = parts[0] if len(parts) > 1 else self._config["database"]
        table_name = parts[-1]

        try:
            import pymysql.cursors

            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        COLUMN_NAME      AS `name`,
                        DATA_TYPE        AS `type`,
                        IS_NULLABLE      AS `nullable`,
                        ORDINAL_POSITION AS ordinal_position
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (db_name, table_name),
                )
                return list(cur.fetchall())
        except Exception as e:
            logger.error(f"Error getting schema for {table}: {e}")
            raise

    @resilient_query()
    def execute_query(self, query: str, params: dict = None) -> list[dict]:
        """Execute a raw SQL query and return results as dicts."""
        import pymysql.cursors

        conn = self.connect()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(query, params)
                return list(cur.fetchall())
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            raise

    def get_soda_config(self) -> dict:
        return {
            "data_source my_mysql": {
                "type": "mysql",
                "host": self._config["host"],
                "port": self._config["port"],
                "username": self._config["user"],
                "password": self._config["password"],
                "database": self._config["database"],
            }
        }

    def get_gx_config(self) -> dict:
        return {
            "name": "my_mysql_datasource",
            "class_name": "Datasource",
            "execution_engine": {
                "class_name": "SqlAlchemyExecutionEngine",
                "connection_string": (
                    f"mysql+pymysql://{self._config['user']}:{self._config['password']}"
                    f"@{self._config['host']}:{self._config['port']}/{self._config['database']}"
                ),
            },
        }


def _quote_table(table: str) -> str:
    """Convert schema.table or just table into a MySQL-safe reference."""
    parts = table.split(".")
    return ".".join(f"`{p}`" for p in parts)
