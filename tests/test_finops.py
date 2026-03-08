from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)

@patch("connectors.base.get_warehouse_connector")
def test_finops_poll(mock_get_connector, client):
    # Mock the warehouse connector and its get_compute_costs method
    mock_connector = mock_get_connector.return_value
    mock_connector.get_compute_costs.return_value = 150.75

    # Mock the environment variable for warehouse type to something other than postgres
    with patch.dict("os.environ", {"WAREHOUSE_TYPE": "snowflake", "OBSERVAKIT_API_KEY": "observakit123"}):
        response = client.post("/finops/poll?days=7", headers={"X-API-Key": "observakit123"})

        assert response.status_code == 200
        data = response.json()
        assert data["warehouse"] == "snowflake"
        assert data["cost_tracked"] == 150.75
        assert data["period_days"] == 7

        # Verify the connector method was called with correct days
        mock_connector.get_compute_costs.assert_called_once_with(days=7)

@patch("connectors.base.get_warehouse_connector")
def test_finops_poll_postgres_skip(mock_get_connector, client):
    # If the warehouse is postgres, it should skip tracking
    with patch.dict("os.environ", {"WAREHOUSE_TYPE": "postgres", "OBSERVAKIT_API_KEY": "observakit123"}):
        response = client.post("/finops/poll?days=7", headers={"X-API-Key": "observakit123"})

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "FinOps tracking not applicable for self-hosted PostgreSQL."

        # Method should NOT be called
        mock_get_connector.return_value.get_compute_costs.assert_not_called()
