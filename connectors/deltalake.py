"""
ObservaKit — Delta Lake Connector (v0.2.0)

Reads Delta tables using the `deltalake` Python library (the Python wrapper
around delta-rs, the Rust implementation of the Delta Lake protocol).

Supported storage backends:
  - Local filesystem
  - Amazon S3  (s3:// or s3a://)
  - Google Cloud Storage (gs://)
  - Azure Data Lake Storage Gen2 (az:// or abfs://)

Configuration (environment variables):
    DELTA_TABLE_PATH        — URI of the Delta table root, e.g.
                              /data/delta/orders          (local)
                              s3://my-bucket/delta/orders  (S3)
    DELTA_STORAGE_OPTIONS   — JSON string of storage backend credentials, e.g.
                              '{"AWS_ACCESS_KEY_ID": "...", "AWS_SECRET_ACCESS_KEY": "..."}'
                              For GCS: '{"GOOGLE_SERVICE_ACCOUNT_KEY": "..."}'
                              For ADLS: '{"AZURE_STORAGE_ACCOUNT_NAME": "...", "AZURE_STORAGE_ACCESS_KEY": "..."}'
    DELTA_VERSION           — Optional integer; read a specific table version
                              (defaults to the latest snapshot)

Install extra:
    pip install observakit[deltalake]
    # or directly:
    pip install deltalake>=0.17

Notes
-----
- Delta Lake connector uses PyArrow under the hood for schema inspection and
  data reading.  PyArrow is a transitive dependency of `deltalake` so no
  separate install is needed.
- The connector opens the table in read-only mode — it never writes to the
  Delta log.
- Large tables: row-count queries use DeltaTable.to_pyarrow_dataset() and
  PyArrow compute functions to avoid loading all data into memory.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from connectors.base import WarehouseConnector, resilient_query

logger = logging.getLogger(__name__)

# Type aliases kept at module level so they don't pollute the method signatures
_DeltaTable = None  # lazy-imported in __init__


class DeltaLakeConnector(WarehouseConnector):
    """
    Delta Lake warehouse connector.

    Treats a single Delta table directory as the "warehouse" for ObservaKit
    monitoring purposes.  Multiple tables can be monitored by setting the
    table path to the parent directory and passing the table name as a
    sub-path relative to DELTA_TABLE_PATH.

    Alternatively, each connector instance maps to one Delta table path; in
    that case, the `table` argument to get_row_count / get_max_timestamp is
    ignored and the configured path is always used.
    """

    def __init__(self):
        try:
            import deltalake  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Delta Lake connector requires 'deltalake'. "
                "Install with: pip install 'observakit[deltalake]' or pip install deltalake>=0.17"
            ) from exc

        self._base_path = os.getenv("DELTA_TABLE_PATH", "")
        if not self._base_path:
            raise ValueError(
                "DELTA_TABLE_PATH environment variable is required for the Delta Lake connector. "
                "Set it to the root URI of your Delta table, e.g. s3://my-bucket/delta/orders"
            )

        raw_opts = os.getenv("DELTA_STORAGE_OPTIONS", "{}")
        try:
            self._storage_options: dict = json.loads(raw_opts)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"DELTA_STORAGE_OPTIONS must be valid JSON, got: {raw_opts!r}"
            ) from exc

        version_env = os.getenv("DELTA_VERSION", "")
        self._version: Optional[int] = int(version_env) if version_env.strip().isdigit() else None

        # Cache open DeltaTable handles keyed by resolved path
        self._tables: dict = {}

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _resolve_path(self, table: str) -> str:
        """
        Resolve the Delta table path for a given table identifier.

        If `table` is an absolute URI (starts with s3://, gs://, az://, /),
        it is used as-is.  Otherwise it is treated as a sub-path relative to
        DELTA_TABLE_PATH.
        """
        if not table or table in (".", "/"):
            return self._base_path
        # If the table reference looks like an absolute URI, use it directly
        if table.startswith(("s3://", "s3a://", "gs://", "az://", "abfs://", "/")):
            return table
        # Strip schema prefix from base path to build sub-path correctly
        base = self._base_path.rstrip("/")
        return f"{base}/{table.lstrip('/')}"

    def _open_table(self, table: str):
        """Open (or return cached) DeltaTable for the given table identifier."""
        import deltalake

        path = self._resolve_path(table)
        if path not in self._tables:
            kwargs: dict = {}
            if self._storage_options:
                kwargs["storage_options"] = self._storage_options
            if self._version is not None:
                kwargs["version"] = self._version
            self._tables[path] = deltalake.DeltaTable(path, **kwargs)
            logger.debug("Opened Delta table at %s (version=%s)", path, self._version or "latest")
        return self._tables[path]

    # -------------------------------------------------------------------------
    # WarehouseConnector interface
    # -------------------------------------------------------------------------

    def connect(self):
        """Delta Lake is file-based; 'connecting' opens the table handle."""
        # Verify the base path is reachable by opening it
        self._open_table(self._base_path)
        return self

    def close(self):
        """Release cached table handles."""
        self._tables.clear()

    @resilient_query()
    def get_max_timestamp(self, table: str, column: str) -> Optional[datetime]:
        """
        Return the maximum value of a timestamp column in the Delta table.

        Uses PyArrow compute to avoid loading all data into memory.
        """
        import pyarrow.compute as pc

        dt = self._open_table(table)
        dataset = dt.to_pyarrow_dataset()

        try:
            batches = dataset.to_batches(columns=[column])
            max_val = None
            for batch in batches:
                col = batch.column(0)
                if len(col) == 0:
                    continue
                batch_max = pc.max(col).as_py()
                if batch_max is None:
                    continue
                if max_val is None or batch_max > max_val:
                    max_val = batch_max

            if max_val is None:
                return None

            # Normalise to UTC-aware datetime
            if isinstance(max_val, datetime):
                if max_val.tzinfo is None:
                    return max_val.replace(tzinfo=timezone.utc)
                return max_val
            # Handle date objects or strings
            return datetime.fromisoformat(str(max_val)).replace(tzinfo=timezone.utc)

        except Exception as exc:
            logger.error("DeltaLake get_max_timestamp(%s, %s): %s", table, column, exc)
            raise

    @resilient_query()
    def get_row_count(self, table: str) -> int:
        """
        Return the total number of rows in the Delta table.

        Uses the Delta transaction log's file-level statistics when available
        (O(1) metadata read), falling back to a full scan if statistics are
        absent.
        """
        dt = self._open_table(table)

        # Prefer cheap metadata-level count from the transaction log
        try:
            # get_add_actions returns per-file stats; num_records is the row count
            actions = dt.get_add_actions(flatten=True).to_pydict()
            counts = actions.get("num_records", [])
            if counts and all(c is not None for c in counts):
                return int(sum(counts))
        except Exception:
            pass  # fall through to full scan

        # Full scan fallback via PyArrow
        import pyarrow.compute as pc

        dataset = dt.to_pyarrow_dataset()
        total = 0
        for batch in dataset.to_batches(columns=[dataset.schema.names[0]]):
            total += len(batch)
        return total

    @resilient_query()
    def get_schema(self, table: str) -> list[dict]:
        """
        Return column metadata from the Delta table schema (Parquet/Arrow schema).
        """
        dt = self._open_table(table)
        arrow_schema = dt.schema().to_pyarrow()

        result = []
        for i, field in enumerate(arrow_schema):
            result.append(
                {
                    "name": field.name,
                    "type": str(field.type),
                    "nullable": field.nullable,
                    "ordinal_position": i + 1,
                }
            )
        return result

    @resilient_query()
    def execute_query(self, query: str, params: dict = None) -> list[dict]:
        """
        Execute a SQL query against the Delta table via DuckDB.

        Delta Lake doesn't have a native SQL engine; this method registers the
        Delta table as a DuckDB view and executes the query through DuckDB.
        Requires the `duckdb` package to be installed in addition to `deltalake`.
        """
        try:
            import duckdb
        except ImportError as exc:
            raise ImportError(
                "execute_query on a Delta Lake connector requires DuckDB. "
                "Install with: pip install duckdb"
            ) from exc

        dt = self._open_table(self._base_path)
        dataset = dt.to_pyarrow_dataset()

        conn = duckdb.connect(":memory:")
        try:
            # Register the PyArrow dataset as a DuckDB view named "delta_table"
            conn.register("delta_table", dataset)
            # Substitute the table name in the query so existing SQL just works
            normalized_query = query.replace(self._base_path, "delta_table")
            # Replace any schema.table references with the view name
            import re

            normalized_query = re.sub(r"\b\w+\.\w+\b", "delta_table", normalized_query)

            if params:
                result = conn.execute(normalized_query, list(params.values()))
            else:
                result = conn.execute(normalized_query)

            columns = [desc[0] for desc in result.description]
            return [dict(zip(columns, row)) for row in result.fetchall()]
        finally:
            conn.close()

    def get_soda_config(self) -> dict:
        """Soda Core does not natively support Delta Lake; use DuckDB engine."""
        return {
            "data_source observakit": {
                "type": "duckdb",
                "path": ":memory:",
            }
        }

    def get_gx_config(self) -> dict:
        return {
            "backend": "delta_lake",
            "table_path": self._base_path,
        }

    # -------------------------------------------------------------------------
    # Delta-specific helpers
    # -------------------------------------------------------------------------

    def get_table_version(self, table: str) -> int:
        """Return the current version of the Delta table."""
        return self._open_table(table).version()

    def get_table_history(self, table: str, limit: int = 10) -> list[dict]:
        """
        Return the last N entries from the Delta transaction log.

        Each entry contains: version, timestamp, operation, operationParameters.
        """
        dt = self._open_table(table)
        history = dt.history(limit=limit)
        return [
            {
                "version": h.get("version"),
                "timestamp": h.get("timestamp"),
                "operation": h.get("operation"),
                "parameters": h.get("operationParameters", {}),
            }
            for h in history
        ]

    def get_file_stats(self, table: str) -> dict:
        """
        Return summary statistics from the Delta transaction log file manifest.

        Useful for FinOps-style monitoring: tracks total bytes stored and file count.
        """
        dt = self._open_table(table)
        try:
            actions = dt.get_add_actions(flatten=True).to_pydict()
            sizes = actions.get("size_bytes", []) or []
            counts = actions.get("num_records", []) or []
            return {
                "file_count": len(sizes),
                "total_bytes": sum(s for s in sizes if s),
                "total_rows_from_stats": sum(c for c in counts if c),
                "version": dt.version(),
            }
        except Exception as exc:
            logger.warning("Could not retrieve Delta file stats for %s: %s", table, exc)
            return {"file_count": None, "total_bytes": None, "version": None}
