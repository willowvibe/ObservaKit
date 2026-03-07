"""
ObservaKit — Schema Drift Detection Tests
"""

import pytest
from datetime import datetime, timezone

from backend.models import SchemaSnapshot, SchemaDiff
from backend.routers.schema_diff import _compute_diff


class TestSchemaDiff:
    """Test schema diff computation."""

    def test_no_changes(self, db_session):
        old_cols = [
            {"name": "id", "type": "integer", "nullable": "NO"},
            {"name": "name", "type": "varchar", "nullable": "YES"},
        ]
        new_cols = [
            {"name": "id", "type": "integer", "nullable": "NO"},
            {"name": "name", "type": "varchar", "nullable": "YES"},
        ]
        diffs = _compute_diff("public.test", old_cols, new_cols, db_session)
        assert len(diffs) == 0

    def test_column_added(self, db_session):
        old_cols = [
            {"name": "id", "type": "integer"},
        ]
        new_cols = [
            {"name": "id", "type": "integer"},
            {"name": "email", "type": "varchar"},
        ]
        diffs = _compute_diff("public.test", old_cols, new_cols, db_session)
        assert len(diffs) == 1
        assert diffs[0]["change_type"] == "added"
        assert diffs[0]["column"] == "email"

    def test_column_removed(self, db_session):
        old_cols = [
            {"name": "id", "type": "integer"},
            {"name": "legacy_field", "type": "text"},
        ]
        new_cols = [
            {"name": "id", "type": "integer"},
        ]
        diffs = _compute_diff("public.test", old_cols, new_cols, db_session)
        assert len(diffs) == 1
        assert diffs[0]["change_type"] == "removed"
        assert diffs[0]["column"] == "legacy_field"

    def test_type_changed(self, db_session):
        old_cols = [
            {"name": "customer_id", "type": "integer"},
        ]
        new_cols = [
            {"name": "customer_id", "type": "varchar"},
        ]
        diffs = _compute_diff("public.test", old_cols, new_cols, db_session)
        assert len(diffs) == 1
        assert diffs[0]["change_type"] == "type_changed"
        assert diffs[0]["old_type"] == "integer"
        assert diffs[0]["new_type"] == "varchar"

    def test_multiple_changes(self, db_session):
        old_cols = [
            {"name": "id", "type": "integer"},
            {"name": "old_col", "type": "text"},
            {"name": "price", "type": "integer"},
        ]
        new_cols = [
            {"name": "id", "type": "integer"},
            {"name": "new_col", "type": "varchar"},
            {"name": "price", "type": "numeric"},
        ]
        diffs = _compute_diff("public.test", old_cols, new_cols, db_session)
        # old_col removed, new_col added, price type changed
        assert len(diffs) == 3
        change_types = {d["change_type"] for d in diffs}
        assert change_types == {"added", "removed", "type_changed"}


class TestSchemaSnapshotModel:
    """Test the SchemaSnapshot model."""

    def test_create_snapshot(self, db_session):
        snapshot = SchemaSnapshot(
            table_name="public.orders",
            columns_json=[
                {"name": "id", "type": "integer"},
                {"name": "amount", "type": "numeric"},
            ],
        )
        db_session.add(snapshot)
        db_session.commit()

        result = db_session.query(SchemaSnapshot).first()
        assert result is not None
        assert result.table_name == "public.orders"
        assert len(result.columns_json) == 2

    def test_diff_stored_in_db(self, db_session):
        old_cols = [{"name": "id", "type": "integer"}]
        new_cols = [{"name": "id", "type": "integer"}, {"name": "email", "type": "varchar"}]

        _compute_diff("public.users", old_cols, new_cols, db_session)
        db_session.commit()

        stored = db_session.query(SchemaDiff).filter(SchemaDiff.table_name == "public.users").all()
        assert len(stored) == 1
        assert stored[0].change_type == "added"
        assert stored[0].column_name == "email"
