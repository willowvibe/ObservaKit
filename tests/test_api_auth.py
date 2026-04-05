"""
Tests for API key authentication middleware.

Verifies that:
  - Requests with a missing X-API-Key header are rejected (403).
  - Requests with the wrong key are rejected (403).
  - Requests with the correct key pass auth (not 401/403).
  - /healthz and / are public endpoints that don't require a key.

The real Postgres DB is not required — we override the DB dependency and
the scheduler startup to make tests fully self-contained.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set env vars BEFORE importing the app
os.environ["OBSERVAKIT_API_KEY"] = "test-secret-key-abc123"
os.environ["METADATA_DB_TYPE"] = "sqlite"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from backend.main import app  # noqa: E402
from backend.models import Base, get_db  # noqa: E402


from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Override the DB dependency to use an in-memory SQLite DB
# ---------------------------------------------------------------------------

_test_engine = create_engine(
    "sqlite:///:memory:", 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
Base.metadata.create_all(bind=_test_engine)
_TestSession = sessionmaker(bind=_test_engine)


def override_get_db():
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module")
def client():
    # Patch out the scheduler and warehouse connector so no real connections happen
    with patch("backend.main.start_scheduler"), \
         patch("backend.main.shutdown_scheduler"), \
         patch("backend.main.command.upgrade"), \
         patch("connectors.base.get_warehouse_connector"):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAPIKeyAuth:
    def test_missing_api_key_returns_403(self, client):
        response = client.get("/freshness/")
        assert response.status_code == 403

    def test_wrong_api_key_returns_403(self, client):
        response = client.get(
            "/freshness/",
            headers={"X-API-Key": "totally-wrong-key"},
        )
        assert response.status_code == 403

    def test_correct_api_key_is_accepted(self, client):
        response = client.get(
            "/freshness/",
            headers={"X-API-Key": "test-secret-key-abc123"},
        )
        # Auth should pass — response may be 200 or 500 depending on data,
        # but must NOT be 401 or 403.
        assert response.status_code not in (401, 403)

    def test_healthz_does_not_require_auth(self, client):
        """/healthz is the readiness probe — must be publicly accessible."""
        response = client.get("/healthz")
        assert response.status_code in (200, 503)

    def test_root_does_not_require_auth(self, client):
        """/ returns service metadata without requiring a key."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("service") == "ObservaKit"
