"""
Migration 002 — BigInteger/Numeric column types, column_profiles table, check_suppressions table.

Changes:
  - volume_records.row_count: Integer -> BigInteger (supports 10B+ row tables)
  - check_results.metric_value: Float -> Numeric(20,6) (avoids float precision loss)
  - column_profiles.null_count, distinct_count: Integer -> BigInteger
  - NEW: column_profiles table (added in v0.1.7)
  - NEW: check_suppressions table for alert muting

Revision ID: 002_biginteger_numeric_columns
Revises: 001_initial_schema
Create Date: 2026-04-04
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "002_biginteger_numeric_columns"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Alter volume_records.row_count to BigInteger ----
    op.alter_column(
        "volume_records",
        "row_count",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )

    # ---- Alter check_results.metric_value to Numeric ----
    op.alter_column(
        "check_results",
        "metric_value",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=20, scale=6),
        existing_nullable=True,
    )

    # ---- Create column_profiles table ----
    op.create_table(
        "column_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(255), nullable=False, index=True),
        sa.Column("column_name", sa.String(255), nullable=False),
        sa.Column("null_count", sa.BigInteger(), nullable=True),
        sa.Column("null_pct", sa.Float(), nullable=True),
        sa.Column("distinct_count", sa.BigInteger(), nullable=True),
        sa.Column("min_value", sa.String(255), nullable=True),
        sa.Column("max_value", sa.String(255), nullable=True),
        sa.Column("mean_value", sa.Float(), nullable=True),
        sa.Column("profiled_at", sa.DateTime(), nullable=False),
    )

    # ---- Create check_suppressions table ----
    op.create_table(
        "check_suppressions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(255), nullable=False, index=True),
        sa.Column("suppressed_until", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("check_suppressions")
    op.drop_table("column_profiles")

    op.alter_column(
        "check_results",
        "metric_value",
        existing_type=sa.Numeric(precision=20, scale=6),
        type_=sa.Float(),
        existing_nullable=True,
    )

    op.alter_column(
        "volume_records",
        "row_count",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
