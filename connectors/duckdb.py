"""
ObservaKit — DuckDB Warehouse Connector

DuckDB is an embedded analytical database popular for local/laptop pipelines,
dbt-core local development, and reading Parquet / Iceberg files directly.

Configuration (environment variables):
    WAREHOUSE_DB      — path to the .duckdb file, or ":memory:" for in-memory
                        (default: ":memory:")
    WAREHOUSE_READ_ONLY — set to "true" to open the file in read-only mode

Install extra:
    pip install duckdb
"""

import logging
import os
from datetime import datetime
from typing import Optional

from backend.security import is_safe_identifier, is_safe_table_reference
from connectors.base import WarehouseConnector, resilient_query

logger = logging.getLogger(__name__)


class DuckDBConnector(WarehouseConnector):
    """
    DuckDB warehouse connector.

    Supports:
    - Local .duckdb files
    - In-memory databases (useful for testing)
    - Reading Parquet / CSV files via DuckDB's SQL interface
    """

    def __init__(self):
        try:
            import duckdb  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "DuckDB connector requires 'duckdb'. Install with: pip install duckdb"
            ) from exc

        self._db_path = os.getenv("WAREHOUSE_DB", ":memory:")
        self._read_only = os.getenv("WAREHOUSE_READ_ONLY", "false").lower() == "true"
        self._conn = None

    def connect(self):
        """Open (or reuse) a DuckDB connection."""
        import duckdb

        if self._conn is None:
            self._conn = duckdb.connect(self._db_path, read_only=self._read_only)
            logger.debug("DuckDB connected to %s (read_only=%s)", self._db_path, self._read_only)
        return self._conn

    def close(self):
        """Close the DuckDB connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @resilient_query()
    def get_max_timestamp(self, table: str, column: str) -> Optional[datetime]:
        if not is_safe_table_reference(table) or not is_safe_identifier(column):
            raise ValueError(f"Invalid table/column reference: table={table}, column={column}")
        conn = self.connect()
        try:
            result = conn.execute(f"SELECT MAX({column}) FROM {table}").fetchone()
            val = result[0] if result else None
            if val is None:
                return None
            # DuckDB can return datetime or string depending on column type
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(str(val))
        except Exception as exc:
            logger.error("DuckDB get_max_timestamp(%s, %s): %s", table, column, exc)
            raise

    @resilient_query()
    def get_row_count(self, table: str) -> int:
        if not is_safe_table_reference(table):
            raise ValueError(f"Invalid table reference: {table}")
        conn = self.connect()
        try:
            result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(result[0]) if result else 0
        except Exception as exc:
            logger.error("DuckDB get_row_count(%s): %s", table, exc)
            raise

    @resilient_query()
    def get_schema(self, table: str) -> list[dict]:
        """
        Return column metadata for a DuckDB table using PRAGMA table_info().
        Falls back to information_schema when the table is not a base table.
        """
        if not is_safe_table_reference(table):
            raise ValueError(f"Invalid table reference: {table}")
        conn = self.connect()
        try:
            rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
            if rows:
                # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
                return [
                    {
                        "name": r[1],
                        "type": r[2],
                        "nullable": "NO" if r[3] else "YES",
                        "ordinal_position": r[0] + 1,
                    }
                    for r in rows
                ]
            # Fallback: information_schema (works for views / virtual tables)
            schema, tbl = ("main", table) if "." not in table else table.split(".", 1)
            # Validate schema and table names
            if not is_safe_identifier(schema) or not is_safe_identifier(tbl):
                raise ValueError(f"Invalid identifier in table reference: {table}")
            rows = conn.execute(
                """
                SELECT column_name, data_type, is_nullable, ordinal_position
                FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
                ORDER BY ordinal_position
                """,
                [schema, tbl],
            ).fetchall()
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
            logger.error("DuckDB get_schema(%s): %s", table, exc)
            raise

    @resilient_query()
    def execute_query(self, query: str, params: dict = None) -> list[dict]:
        conn = self.connect()
        try:
            if params:
                result = conn.execute(query, list(params.values()))
            else:
                result = conn.execute(query)
            columns = [desc[0] for desc in result.description]
            return [dict(zip(columns, row)) for row in result.fetchall()]
        except Exception as exc:
            logger.error("DuckDB execute_query: %s", exc)
            raise

    def get_soda_config(self) -> dict:
        return {
            "data_source observakit": {
                "type": "duckdb",
                "path": self._db_path,
            }
        }

    def get_gx_config(self) -> dict:
        return {
            "connection_string": f"duckdb:///{self._db_path}",
        }
