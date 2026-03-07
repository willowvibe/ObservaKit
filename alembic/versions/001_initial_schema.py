"""
Initial schema — creates all ObservaKit metadata tables.

Revision ID: 001_initial_schema
Revises: (none)
Create Date: 2026-03-08
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- freshness_records ----
    op.create_table(
        "freshness_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(255), nullable=False, index=True),
        sa.Column("timestamp_column", sa.String(255), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(), nullable=True),
        sa.Column("lag_seconds", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
    )

    # ---- volume_records ----
    op.create_table(
        "volume_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(255), nullable=False, index=True),
        sa.Column("dag_id", sa.String(255), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("rolling_avg", sa.Float(), nullable=True),
        sa.Column("deviation_pct", sa.Float(), nullable=True),
        sa.Column("is_anomaly", sa.Boolean(), server_default="false"),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
    )

    # ---- check_results ----
    op.create_table(
        "check_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("check_name", sa.String(255), nullable=False),
        sa.Column("table_name", sa.String(255), nullable=False, index=True),
        sa.Column("check_type", sa.String(100), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=False),
    )

    # ---- schema_snapshots ----
    op.create_table(
        "schema_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(255), nullable=False, index=True),
        sa.Column("columns_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(), nullable=False),
    )

    # ---- schema_diffs ----
    op.create_table(
        "schema_diffs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(255), nullable=False, index=True),
        sa.Column(
            "change_type", sa.String(50), nullable=False
        ),  # added | removed | type_changed | renamed
        sa.Column("column_name", sa.String(255), nullable=False),
        sa.Column("old_value", sa.String(255), nullable=True),
        sa.Column("new_value", sa.String(255), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
    )

    # ---- alert_logs ----
    op.create_table(
        "alert_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("table_name", sa.String(255), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("success", sa.Boolean(), server_default="true"),
    )

    # ---- pipeline_runs ----
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("orchestrator", sa.String(50), nullable=False),
        sa.Column("dag_id", sa.String(255), nullable=False, index=True),
        sa.Column("run_id", sa.String(255), nullable=False),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pipeline_runs")
    op.drop_table("alert_logs")
    op.drop_table("schema_diffs")
    op.drop_table("schema_snapshots")
    op.drop_table("check_results")
    op.drop_table("volume_records")
    op.drop_table("freshness_records")
