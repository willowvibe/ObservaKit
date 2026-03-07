"""
ObservaKit — SQLAlchemy Models & Database Engine
"""

import os
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    Boolean,
    JSON,
)
from sqlalchemy.orm import declarative_base, sessionmaker

# ---- Database Connection ----
DATABASE_URL = (
    f"postgresql://"
    f"{os.getenv('METADATA_DB_USER', 'observakit')}:"
    f"{os.getenv('METADATA_DB_PASSWORD', 'changeme')}@"
    f"{os.getenv('METADATA_DB_HOST', 'localhost')}:"
    f"{os.getenv('METADATA_DB_PORT', '5432')}/"
    f"{os.getenv('METADATA_DB_NAME', 'observakit')}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency: yields a DB session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# Models
# =============================================================================


class FreshnessRecord(Base):
    """Tracks freshness lag for monitored tables."""

    __tablename__ = "freshness_records"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(255), nullable=False, index=True)
    timestamp_column = Column(String(255), nullable=False)
    last_updated_at = Column(DateTime, nullable=True)
    lag_seconds = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="ok")  # ok | warn | fail
    checked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class VolumeRecord(Base):
    """Tracks row counts per table per run for anomaly detection."""

    __tablename__ = "volume_records"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(255), nullable=False, index=True)
    dag_id = Column(String(255), nullable=True)
    row_count = Column(Integer, nullable=False)
    rolling_avg = Column(Float, nullable=True)
    deviation_pct = Column(Float, nullable=True)
    is_anomaly = Column(Boolean, default=False)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class CheckResult(Base):
    """Stores quality check results from Soda Core or Great Expectations."""

    __tablename__ = "check_results"

    id = Column(Integer, primary_key=True, index=True)
    check_name = Column(String(255), nullable=False)
    table_name = Column(String(255), nullable=False, index=True)
    check_type = Column(String(100), nullable=False)  # soda | great_expectations
    passed = Column(Boolean, nullable=False)
    metric_value = Column(Float, nullable=True)
    details = Column(Text, nullable=True)
    executed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class SchemaSnapshot(Base):
    """Stores information_schema snapshots for drift detection."""

    __tablename__ = "schema_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(255), nullable=False, index=True)
    columns_json = Column(JSON, nullable=False)  # [{name, type, nullable, ordinal}]
    snapshot_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class SchemaDiff(Base):
    """Records detected schema changes."""

    __tablename__ = "schema_diffs"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(255), nullable=False, index=True)
    change_type = Column(String(50), nullable=False)  # added | removed | type_changed | renamed
    column_name = Column(String(255), nullable=False)
    old_value = Column(String(255), nullable=True)
    new_value = Column(String(255), nullable=True)
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class AlertLog(Base):
    """Tracks dispatched alerts for deduplication and audit."""

    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String(50), nullable=False)  # freshness | volume | quality | schema
    channel = Column(String(50), nullable=False)  # slack | email
    table_name = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    success = Column(Boolean, default=True)


class PipelineRun(Base):
    """Stores pipeline run metadata from Airflow/Prefect."""

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True)
    orchestrator = Column(String(50), nullable=False)  # airflow | prefect
    dag_id = Column(String(255), nullable=False, index=True)
    run_id = Column(String(255), nullable=False)
    state = Column(String(50), nullable=False)  # success | failed | running
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
