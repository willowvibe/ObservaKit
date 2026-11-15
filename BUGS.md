# Bug Log

## BUG-001 — Freshness polling crashes on timezone-naive warehouse timestamps

**Severity:** High — freshness checks produce no records and no alerts for any
warehouse whose `MAX(timestamp_column)` returns a naive `datetime`, including
DuckDB `TIMESTAMP` columns, MySQL `DATETIME`, and Postgres
`TIMESTAMP WITHOUT TIME ZONE`.

**Status:** Fixed in `backend/routers/freshness.py`.

### Reproduction

1. Point ObservaKit at a DuckDB warehouse and insert a row whose
   `updated_at` column is a plain `TIMESTAMP`:

   ```python
   import duckdb

   conn = duckdb.connect("warehouse.duckdb")
   conn.execute(
       "CREATE TABLE orders (id INTEGER, updated_at TIMESTAMP)"
   )
   conn.execute("INSERT INTO orders VALUES (1, now())")
   conn.close()
   ```

2. Configure `kit.yml` with `freshness.enabled: true` and the `orders` table.
3. Call `POST /freshness/poll` with a valid API key.

**Observed:** HTTP 200 with an error entry and no `freshness_records` row:

```text
Freshness check failed for orders:
can't subtract offset-naive and offset-aware datetimes
```

**Expected:** A freshness record is stored with the computed lag and status.

### Root cause

`backend/routers/freshness.py` subtracts the warehouse timestamp from
`datetime.now(timezone.utc)`. DuckDB (and other connectors) return a naive
`datetime` for `TIMESTAMP` columns, so Python raises `TypeError` before the
record is written. The same normalization already existed in
`backend/routers/checks.py` and `backend/routers/late_arriving.py`; freshness
was missing it.

### Fix

Naive warehouse timestamps are treated as UTC before the subtraction, matching
the existing convention elsewhere in the codebase.

### Verification

`tests/smoke/test_smoke.py::test_freshness_poll_persists_result` now passes
against a temporary DuckDB warehouse, and the full suite remains green.
