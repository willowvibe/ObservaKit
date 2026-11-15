"""
ObservaKit — Docker-free smoke test.

Run with: make test-smoke

This module must be imported before backend.models picks a database URL,
so it sets METADATA_DB_TYPE=sqlite before importing the app. That is why
the default test suite ignores tests/smoke and runs it as a separate
pytest invocation.
"""

import logging
import os

import duckdb
import pytest
from fastapi.testclient import TestClient

API_KEY = "smoke-test-key"
AUTH = {"X-API-Key": API_KEY}

KIT_YML = """
warehouse:
  type: duckdb

orchestrator:
  type: airflow
  airflow:
    base_url: http://localhost:9
    username: smoke
    password: smoke

freshness:
  enabled: true
  tables:
    - table: orders
      timestamp_column: updated_at
      warn_after: 1h
      fail_after: 2h

volume:
  enabled: true
  rolling_window_days: 7
  tables:
    - table: orders
      dag_id: load_orders
      anomaly_threshold: 0.3

quality:
  enabled: true
  engine: soda
  checks_dir: checks/
  custom_sql:
    - name: "orders_not_empty"
      query: "SELECT COUNT(*) AS count FROM orders"
      assert: "result > 0"
      table: orders

schema_drift:
  enabled: true
  tables:
    - orders

distribution:
  enabled: false

contracts:
  enabled: false

alerts:
  noise_suppression:
    enabled: false
  routing: []

late_arriving:
  enabled: false
"""


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp("observakit-smoke")
    (root / "config").mkdir()
    (root / "checks").mkdir()
    (root / "config" / "kit.yml").write_text(KIT_YML)

    warehouse = root / "warehouse.duckdb"
    conn = duckdb.connect(str(warehouse))
    conn.execute(
        """
        CREATE TABLE orders (
            id INTEGER,
            customer_id INTEGER,
            status VARCHAR,
            amount DOUBLE,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO orders VALUES
        (1, 1, 'pending', 10.0, now(), now()),
        (2, 1, 'delivered', 25.5, now() - INTERVAL 1 DAY, now() - INTERVAL 1 DAY)
        """
    )
    conn.close()

    os.environ.update(
        {
            "METADATA_DB_TYPE": "sqlite",
            "OBSERVAKIT_API_KEY": API_KEY,
            "WAREHOUSE_TYPE": "duckdb",
            "WAREHOUSE_DB": str(warehouse),
            "FRESHNESS_CHECK_INTERVAL": "999",
            "VOLUME_CHECK_INTERVAL": "999",
            "SCHEMA_CHECK_INTERVAL": "999",
            "QUALITY_CHECK_INTERVAL": "999",
            "FINOPS_CHECK_INTERVAL": "999",
            "MAINTENANCE_PURGE_INTERVAL": "999",
            "LATE_ARRIVING_CHECK_INTERVAL": "999",
        }
    )

    # The temp cwd has no alembic.ini, so the app lifespan logs an expected
    # "falling back to create_all" traceback. Suppress only that record to keep
    # the smoke output clean; the fallback itself still runs.
    class _DropExpectedAlembicFallback(logging.Filter):
        def filter(self, record):
            return "Failed to run Alembic migrations" not in record.getMessage()

    main_logger = logging.getLogger("backend.main")
    suppression = _DropExpectedAlembicFallback()
    main_logger.addFilter(suppression)

    old_cwd = os.getcwd()
    os.chdir(root)
    try:
        from backend.main import app

        with TestClient(app) as test_client:
            yield test_client
    finally:
        os.chdir(old_cwd)
        main_logger.removeFilter(suppression)


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"


def test_ui_config_serves_runtime_key(client):
    response = client.get("/ui/config.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.headers.get("cross-origin-resource-policy") == "same-origin"
    assert f'"{API_KEY}"' in response.text


def test_protected_endpoint_requires_key(client):
    response = client.get("/freshness/")
    assert response.status_code == 403


def test_freshness_poll_persists_result(client):
    response = client.post("/freshness/poll", headers=AUTH)
    assert response.status_code == 200, response.text

    records = client.get("/freshness/", headers=AUTH)
    assert records.status_code == 200
    assert any(row["table"] == "orders" for row in records.json())


def test_custom_sql_check_passes(client):
    response = client.post("/checks/run", headers=AUTH)
    assert response.status_code == 200, response.text

    results = client.get("/checks/results", headers=AUTH)
    assert results.status_code == 200
    assert any(
        row["check_name"] == "orders_not_empty" and row["passed"] for row in results.json()
    )


def test_quality_metrics_are_exported(client):
    client.post("/checks/run", headers=AUTH)
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "observakit_check_results_total{" in metrics.text
    assert "observakit_check_result_info{" in metrics.text
