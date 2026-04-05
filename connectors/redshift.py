"""
ObservaKit — Amazon Redshift Warehouse Connector

Redshift is wire-compatible with PostgreSQL but has important differences:
  - information_schema is available but SVV_COLUMNS is more reliable for late-binding views.
  - SVCS_QUERY_SUMMARY can give query-level byte scan counts for FinOps.
  - Some psycopg2 features (server-side cursors, LISTEN/NOTIFY) don't work.
  - Connection strings use port 5439 by default.
  - IAM auth is supported via redshift_connector; we default to password auth here.

Install: pip install observakit[redshift]  →  redshift-connector>=2.1.0
"""

import logging
import os
from datetime import datetime
from typing import Optional

from connectors.base import WarehouseConnector, resilient_query

logger = logging.getLogger(__name__)


class RedshiftConnector(WarehouseConnector):
    """Amazon Redshift warehouse connector (via redshift-connector)."""

    def __init__(self):
        self._conn = None
        self._config = {
            "host": os.getenv("WAREHOUSE_HOST", ""),
            "port": int(os.getenv("WAREHOUSE_PORT", "5439")),
            "user": os.getenv("WAREHOUSE_USER", ""),
            "password": os.getenv("WAREHOUSE_PASSWORD", ""),
            "database": os.getenv("WAREHOUSE_DB", "dev"),
            # Optional IAM role auth (set WAREHOUSE_IAM_ROLE to enable)
            # When set, user/password are ignored and temporary credentials are fetched.
            "iam": os.getenv("WAREHOUSE_IAM_ROLE", "") != "",
        }
        self._iam_role = os.getenv("WAREHOUSE_IAM_ROLE", "")

    def connect(self):
        """Establish a redshift_connector connection."""
        try:
            import redshift_connector
        except ImportError:
            raise RuntimeError(
                "redshift-connector is not installed. Run: pip install 'observakit[redshift]'"
            )

        if self._conn is None or self._conn.is_closed():
            if self._config["iam"]:
                self._conn = redshift_connector.connect(
                    iam=True,
                    host=self._config["host"],
                    port=self._config["port"],
                    database=self._config["database"],
                    cluster_identifier=os.getenv("WAREHOUSE_CLUSTER_ID", ""),
                    profile=os.getenv("AWS_PROFILE", "default"),
                )
            else:
                self._conn = redshift_connector.connect(
                    host=self._config["host"],
                    port=self._config["port"],
                    user=self._config["user"],
                    password=self._config["password"],
                    database=self._config["database"],
                )
        return self._conn

    def close(self):
        if self._conn and not self._conn.is_closed():
            self._conn.close()

    @resilient_query()
    def get_max_timestamp(self, table: str, column: str) -> Optional[datetime]:
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT MAX({column}) FROM {table}")
                result = cur.fetchone()
                return result[0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error getting max timestamp for {table}.{column}: {e}")
            conn.rollback()
            raise

    @resilient_query()
    def get_row_count(self, table: str) -> int:
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

    @resilient_query()
    def get_schema(self, table: str) -> list[dict]:
        """
        Use SVV_COLUMNS which works for regular tables, late-binding views,
        and external tables (Redshift Spectrum).
        Falls back to information_schema for older clusters.
        """
        conn = self.connect()
        parts = table.split(".")
        schema_name = parts[0] if len(parts) > 1 else "public"
        table_name = parts[-1]

        try:
            with conn.cursor() as cur:
                # SVV_COLUMNS: preferred for Redshift — covers Spectrum + late-binding views
                cur.execute(
                    """
                    SELECT
                        column_name      AS name,
                        data_type        AS type,
                        is_nullable      AS nullable,
                        ordinal_position
                    FROM svv_columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema_name, table_name),
                )
                rows = cur.fetchall()
                columns = cur.description
                return [
                    dict(zip([col[0] for col in columns], row))
                    for row in rows
                ]
        except Exception:
            # Fallback to information_schema for clusters without SVV_COLUMNS access
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            column_name      AS name,
                            data_type        AS type,
                            is_nullable      AS nullable,
                            ordinal_position
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position
                        """,
                        (schema_name, table_name),
                    )
                    rows = cur.fetchall()
                    col_names = [col[0] for col in cur.description]
                    return [dict(zip(col_names, row)) for row in rows]
            except Exception as e:
                logger.error(f"Error getting schema for {table}: {e}")
                conn.rollback()
                raise

    @resilient_query()
    def execute_query(self, query: str, params=None) -> list[dict]:
        """Execute a raw SQL query and return results as list of dicts."""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                if not rows:
                    return []
                col_names = [col[0] for col in cur.description]
                return [dict(zip(col_names, row)) for row in rows]
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            conn.rollback()
            raise

    @resilient_query()
    def get_query_bytes_scanned(self, hours: int = 24) -> list[dict]:
        """
        FinOps helper: return total bytes scanned per user/query label in the last N hours.
        Uses STL_SCAN which is Redshift-specific.
        """
        query = f"""
            SELECT
                userid,
                SUM(rows)          AS total_rows_scanned,
                SUM(bytes)         AS total_bytes_scanned
            FROM stl_scan
            WHERE starttime >= DATEADD(hour, -{hours}, GETDATE())
            GROUP BY userid
            ORDER BY total_bytes_scanned DESC
            LIMIT 20
        """
        try:
            return self.execute_query(query)
        except Exception as e:
            logger.warning(f"Could not fetch Redshift scan stats: {e}")
            return []

    def get_soda_config(self) -> dict:
        return {
            "data_source my_redshift": {
                "type": "redshift",
                "host": self._config["host"],
                "port": self._config["port"],
                "username": self._config["user"],
                "password": self._config["password"],
                "database": self._config["database"],
                "schema": "public",
            }
        }

    def get_gx_config(self) -> dict:
        return {
            "name": "my_redshift_datasource",
            "class_name": "Datasource",
            "execution_engine": {
                "class_name": "SqlAlchemyExecutionEngine",
                "connection_string": (
                    f"redshift+redshift_connector://{self._config['user']}:{self._config['password']}"
                    f"@{self._config['host']}:{self._config['port']}/{self._config['database']}"
                ),
            },
        }
