"""
ObservaKit — Trino / Presto Connector

Connects to a Trino (formerly PrestoSQL) cluster using trino-python-client.
Commonly used with Iceberg, Hive, Delta Lake, and other federated catalogs.

Configuration (environment variables):
    TRINO_HOST          — Trino coordinator hostname (default: localhost)
    TRINO_PORT          — Trino coordinator port (default: 8080)
    TRINO_USER          — username (default: observakit)
    TRINO_PASSWORD      — password if using LDAP / basic auth (optional)
    TRINO_CATALOG       — default catalog (default: hive)
    TRINO_SCHEMA        — default schema (default: default)
    TRINO_HTTP_SCHEME   — http or https (default: http)

Install extra:
    pip install trino
"""

import logging
import os
from datetime import datetime
from typing import Optional

from connectors.base import WarehouseConnector, resilient_query

logger = logging.getLogger(__name__)


class TrinoConnector(WarehouseConnector):
    """
    Trino / Presto warehouse connector.

    Supports:
    - Trino (recommended — actively maintained fork)
    - Presto (legacy — same wire protocol)
    - All Trino catalogs: Iceberg, Hive, Delta Lake, TPCH, TPCDS, etc.
    """

    def __init__(self):
        try:
            import trino  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Trino connector requires 'trino'. Install with: pip install trino"
            ) from exc

        self._host = os.getenv("TRINO_HOST", "localhost")
        self._port = int(os.getenv("TRINO_PORT", "8080"))
        self._user = os.getenv("TRINO_USER", "observakit")
        self._password = os.getenv("TRINO_PASSWORD", "")
        self._catalog = os.getenv("TRINO_CATALOG", "hive")
        self._schema = os.getenv("TRINO_SCHEMA", "default")
        self._http_scheme = os.getenv("TRINO_HTTP_SCHEME", "http")
        self._conn = None

    def connect(self):
        """Open (or reuse) a Trino connection."""
        import trino

        if self._conn is None:
            auth = None
            if self._password:
                auth = trino.auth.BasicAuthentication(self._user, self._password)

            self._conn = trino.dbapi.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                auth=auth,
                catalog=self._catalog,
                schema=self._schema,
                http_scheme=self._http_scheme,
            )
            logger.debug(
                "Trino connected to %s:%d (catalog=%s, schema=%s)",
                self._host,
                self._port,
                self._catalog,
                self._schema,
            )
        return self._conn

    def close(self):
        """Close the Trino connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    @resilient_query()
    def get_max_timestamp(self, table: str, column: str) -> Optional[datetime]:
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
            logger.error("Trino get_max_timestamp(%s, %s): %s", table, column, exc)
            raise

    @resilient_query()
    def get_row_count(self, table: str) -> int:
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                result = cur.fetchone()
                return int(result[0]) if result else 0
        except Exception as exc:
            logger.error("Trino get_row_count(%s): %s", table, exc)
            raise

    @resilient_query()
    def get_schema(self, table: str) -> list[dict]:
        """
        Return column metadata from information_schema.columns.
        Trino uses three-part naming: catalog.schema.table.
        """
        conn = self.connect()
        try:
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
                    f"""
                    SELECT column_name, data_type, is_nullable, ordinal_position
                    FROM {catalog}.information_schema.columns
                    WHERE table_schema = '{schema}' AND table_name = '{tbl}'
                    ORDER BY ordinal_position
                    """
                )
                rows = cur.fetchall()

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
            logger.error("Trino get_schema(%s): %s", table, exc)
            raise

    @resilient_query()
    def execute_query(self, query: str, params: dict = None) -> list[dict]:
        """
        Execute a raw Trino SQL query.
        Note: Trino's Python client does not support parameterized queries in all
        versions — callers should sanitize inputs before passing to this method.
        """
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                # Trino DBAPI uses positional %s params
                if params:
                    cur.execute(query, list(params.values()))
                else:
                    cur.execute(query)
                columns = [desc[0] for desc in cur.description] if cur.description else []
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            logger.error("Trino execute_query: %s", exc)
            raise

    def get_soda_config(self) -> dict:
        return {
            "data_source observakit": {
                "type": "trino",
                "host": self._host,
                "port": self._port,
                "catalog": self._catalog,
                "schema": self._schema,
                "auth": {
                    "type": "basic",
                    "username": self._user,
                    "password": self._password,
                },
            }
        }

    def get_gx_config(self) -> dict:
        scheme = "trino+https" if self._http_scheme == "https" else "trino"
        auth_part = f"{self._user}:{self._password}@" if self._password else f"{self._user}@"
        return {
            "connection_string": (
                f"{scheme}://{auth_part}{self._host}:{self._port}/{self._catalog}/{self._schema}"
            ),
        }
