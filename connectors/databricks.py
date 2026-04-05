"""
ObservaKit — Databricks Lakehouse Connector

Connects to Databricks SQL via the Databricks SQL Connector for Python.
Supports Unity Catalog and legacy Hive metastore table references.

Configuration (environment variables):
    DATABRICKS_SERVER_HOSTNAME  — e.g. adb-XXXXX.azuredatabricks.net
    DATABRICKS_HTTP_PATH        — e.g. /sql/1.0/warehouses/XXXXXXXX
    DATABRICKS_TOKEN            — personal access token or M2M OAuth token
    DATABRICKS_CATALOG          — Unity Catalog catalog name (default: hive_metastore)
    DATABRICKS_SCHEMA           — default schema / database (default: default)

Install extra:
    pip install databricks-sql-connector
"""

import logging
import os
from datetime import datetime
from typing import Optional

from connectors.base import WarehouseConnector, resilient_query
from backend.security import is_safe_identifier, is_safe_table_reference

logger = logging.getLogger(__name__)


class DatabricksConnector(WarehouseConnector):
    """
    Databricks Lakehouse connector.

    Uses the official Databricks SQL Connector which supports:
    - Databricks SQL Warehouses (Serverless & Classic)
    - Delta Lake tables
    - Unity Catalog (three-part names: catalog.schema.table)
    """

    def __init__(self):
        try:
            import databricks.sql  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Databricks connector requires 'databricks-sql-connector'. "
                "Install with: pip install databricks-sql-connector"
            ) from exc

        self._server_hostname = os.getenv("DATABRICKS_SERVER_HOSTNAME", "")
        self._http_path = os.getenv("DATABRICKS_HTTP_PATH", "")
        self._token = os.getenv("DATABRICKS_TOKEN", "")
        self._catalog = os.getenv("DATABRICKS_CATALOG", "hive_metastore")
        self._schema = os.getenv("DATABRICKS_SCHEMA", "default")
        self._conn = None

        if not self._server_hostname or not self._http_path or not self._token:
            raise ValueError(
                "Databricks connector requires DATABRICKS_SERVER_HOSTNAME, "
                "DATABRICKS_HTTP_PATH, and DATABRICKS_TOKEN."
            )

    def connect(self):
        """Open (or reuse) a Databricks SQL connection."""
        import databricks.sql

        if self._conn is None:
            self._conn = databricks.sql.connect(
                server_hostname=self._server_hostname,
                http_path=self._http_path,
                access_token=self._token,
                catalog=self._catalog,
                schema=self._schema,
            )
            logger.debug(
                "Databricks connected to %s (catalog=%s, schema=%s)",
                self._server_hostname,
                self._catalog,
                self._schema,
            )
        return self._conn

    def close(self):
        """Close the Databricks connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    @resilient_query()
    def get_max_timestamp(self, table: str, column: str) -> Optional[datetime]:
        if not is_safe_table_reference(table) or not is_safe_identifier(column):
            raise ValueError(f"Invalid table/column reference: table={table}, column={column}")
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT MAX({column}) FROM {table}")
                result = cur.fetchone()
                val = result[0] if result else None
                if val is None:
                    return None
                if isinstance(val, datetime):
                    return val
                return datetime.fromisoformat(str(val))
        except Exception as exc:
            logger.error("Databricks get_max_timestamp(%s, %s): %s", table, column, exc)
            raise

    @resilient_query()
    def get_row_count(self, table: str) -> int:
        if not is_safe_table_reference(table):
            raise ValueError(f"Invalid table reference: {table}")
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                result = cur.fetchone()
                return int(result[0]) if result else 0
        except Exception as exc:
            logger.error("Databricks get_row_count(%s): %s", table, exc)
            raise

    @resilient_query()
    def get_schema(self, table: str) -> list[dict]:
        """
        Return column metadata using DESCRIBE TABLE.
        Falls back to information_schema for Unity Catalog tables.
        """
        conn = self.connect()
        try:
            # Parse three-part name: catalog.schema.table or schema.table or table
            parts = table.split(".")
            if len(parts) == 3:
                catalog, schema, tbl = parts
            elif len(parts) == 2:
                catalog = self._catalog
                schema, tbl = parts
            else:
                catalog = self._catalog
                schema = self._schema
                tbl = table

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable, ordinal_position
                    FROM information_schema.columns
                    WHERE table_catalog = ? AND table_schema = ? AND table_name = ?
                    ORDER BY ordinal_position
                    """,
                    (catalog, schema, tbl),
                )
                rows = cur.fetchall()

            if not rows:
                # Fallback: DESCRIBE TABLE (works for older metastore tables)
                # Validate the table reference before using it in DESCRIBE
                if not is_safe_table_reference(table):
                    raise ValueError(f"Invalid table reference: {table}")
                with conn.cursor() as cur:
                    cur.execute(f"DESCRIBE TABLE {table}")
                    rows = cur.fetchall()
                    return [
                        {
                            "name": r[0],
                            "type": r[1],
                            "nullable": "YES",
                            "ordinal_position": i + 1,
                        }
                        for i, r in enumerate(rows)
                        if r[0] and not r[0].startswith("#")
                    ]

            return [
                {
                    "name": r[0],
                    "type": r[1],
                    "nullable": r[2],
                    "ordinal_position": r[3],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("Databricks get_schema(%s): %s", table, exc)
            raise

    @resilient_query()
    def execute_query(self, query: str, params: dict = None) -> list[dict]:
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                if params:
                    cur.execute(query, list(params.values()))
                else:
                    cur.execute(query)
                columns = [desc[0] for desc in cur.description] if cur.description else []
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            logger.error("Databricks execute_query: %s", exc)
            raise

    def get_soda_config(self) -> dict:
        return {
            "data_source observakit": {
                "type": "spark",
                "host": self._server_hostname,
                "http_path": self._http_path,
                "token": self._token,
                "catalog": self._catalog,
                "schema": self._schema,
            }
        }

    def get_gx_config(self) -> dict:
        return {
            "connection_string": (
                f"databricks://token:{self._token}@{self._server_hostname}"
                f"?http_path={self._http_path}&catalog={self._catalog}&schema={self._schema}"
            ),
        }
