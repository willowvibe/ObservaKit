"""
ObservaKit — Test fixtures and configuration.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def mock_postgres_connector():
    """Mock PostgreSQL warehouse connector."""
    connector = MagicMock()
    connector.get_max_timestamp.return_value = None
    connector.get_row_count.return_value = 1000
    connector.get_schema.return_value = [
        {"name": "id", "type": "integer", "nullable": "NO", "ordinal_position": 1},
        {"name": "name", "type": "character varying", "nullable": "YES", "ordinal_position": 2},
        {"name": "amount", "type": "numeric", "nullable": "YES", "ordinal_position": 3},
        {
            "name": "created_at",
            "type": "timestamp with time zone",
            "nullable": "YES",
            "ordinal_position": 4,
        },
    ]
    return connector


@pytest.fixture
def mock_airflow_connector():
    """Mock Airflow orchestrator connector."""
    connector = MagicMock()
    connector.list_dags.return_value = [
        {"dag_id": "load_orders", "is_paused": False, "description": "Load orders"},
    ]
    connector.get_dag_runs.return_value = [
        {
            "dag_id": "load_orders",
            "run_id": "run_1",
            "state": "success",
            "start_date": "2026-03-07T10:00:00Z",
            "end_date": "2026-03-07T10:05:00Z",
            "duration": 300,
        },
    ]
    return connector


@pytest.fixture
def sample_config():
    """Sample kit.yml configuration."""
    return {
        "warehouse": {"type": "postgres"},
        "freshness": {
            "enabled": True,
            "schedule_minutes": 15,
            "tables": [
                {
                    "table": "public.orders",
                    "timestamp_column": "updated_at",
                    "warn_after": "1h",
                    "fail_after": "2h",
                    "alert": "slack",
                }
            ],
        },
        "volume": {
            "enabled": True,
            "rolling_window_days": 7,
            "tables": [
                {
                    "table": "public.orders",
                    "dag_id": "load_orders",
                    "anomaly_threshold": 0.3,
                    "alert": "slack",
                }
            ],
        },
        "schema_drift": {
            "enabled": True,
            "tables": ["public.orders"],
            "alert": "slack",
        },
        "quality": {
            "enabled": True,
            "engine": "soda",
            "checks_dir": "checks/examples/",
        },
    }
