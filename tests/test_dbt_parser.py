import json
from unittest.mock import MagicMock, patch

from backend.models import CheckResult, PipelineRun
from dbt_integration.parse_artifacts import parse_run_results


def test_dbt_parser_success(tmp_path):
    # Create dummy dbt artifacts
    run_results_data = {
        "metadata": {"invocation_id": "test_inv_123", "generated_at": "2023-10-27T10:00:00Z"},
        "results": [
            {"unique_id": "model.my_project.my_model", "status": "success", "execution_time": 1.5},
            {
                "unique_id": "test.my_project.not_null_my_model_id",
                "status": "fail",
                "execution_time": 0.5,
                "message": "Got 5 results, expected 0.",
            },
        ],
    }

    manifest_data = {
        "nodes": {
            "model.my_project.my_model": {
                "resource_type": "model",
                "name": "my_model",
                "alias": "my_model_table",
            },
            "test.my_project.not_null_my_model_id": {
                "resource_type": "test",
                "column_name": "id",
                "attached_node": "model.my_project.my_model",
            },
        }
    }

    run_results_path = tmp_path / "run_results.json"
    manifest_path = tmp_path / "manifest.json"

    with open(run_results_path, "w") as f:
        json.dump(run_results_data, f)

    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)

    # Mock the DB session
    mock_db = MagicMock()

    with patch("dbt_integration.parse_artifacts.SessionLocal", return_value=mock_db):
        parse_run_results(str(run_results_path), str(manifest_path))

        # Verify 2 records were added
        assert mock_db.add.call_count == 2

        added_objects = [call[0][0] for call in mock_db.add.call_args_list]

        # Verify PipelineRun
        pipeline_run = next((obj for obj in added_objects if isinstance(obj, PipelineRun)), None)
        assert pipeline_run is not None
        assert pipeline_run.orchestrator == "dbt_core"
        assert pipeline_run.dag_id == "dbt_run"
        assert pipeline_run.run_id == "dbt_test_inv_123_model.my_project.my_model"
        assert pipeline_run.state == "success"
        assert pipeline_run.duration_seconds == 1.5

        # Verify CheckResult
        check_result = next((obj for obj in added_objects if isinstance(obj, CheckResult)), None)
        assert check_result is not None
        assert check_result.table_name == "my_model"
        assert check_result.check_type == "dbt_test"
        assert check_result.passed is False
