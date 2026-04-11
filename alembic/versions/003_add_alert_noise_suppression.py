"""Add alert noise suppression — AlertNoiseRecord table + severity column on AlertLog.

Revision ID: 003_add_alert_noise_suppression
Revises: 81c7c80e0f60
Create Date: 2026-04-11
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_alert_noise_suppression"
down_revision: Union[str, Sequence[str], None] = "81c7c80e0f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add severity column to existing alert_logs table
    op.add_column(
        "alert_logs",
        sa.Column("severity", sa.String(length=20), nullable=True),
    )

    # Create the alert_noise_records table
    op.create_table(
        "alert_noise_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("alert_type", sa.String(length=50), nullable=False),
        sa.Column("count_1h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("count_24h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("count_7d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("noise_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("severity_trend", sa.String(length=20), nullable=False, server_default="stable"),
        sa.Column("is_throttled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_calculated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("table_name", "alert_type", name="uq_noise_table_type"),
    )
    op.create_index(
        "ix_alert_noise_records_table_name",
        "alert_noise_records",
        ["table_name"],
    )
    op.create_index(
        "ix_alert_noise_records_alert_type",
        "alert_noise_records",
        ["alert_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_noise_records_alert_type", table_name="alert_noise_records")
    op.drop_index("ix_alert_noise_records_table_name", table_name="alert_noise_records")
    op.drop_table("alert_noise_records")
    op.drop_column("alert_logs", "severity")
