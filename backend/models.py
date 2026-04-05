"""
ObservaKit — SQLAlchemy Models & Database Engine
"""

import os
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# ---- Database Connection ----
DB_TYPE = os.getenv("METADATA_DB_TYPE", "postgresql").lower()

if DB_TYPE == "sqlite":
    DATABASE_URL = "sqlite:///./observakit.db"
    # SQLite needs special handling for threading
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
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

class Project(Base):
    """A logical grouping of checks, integrations, and alerts."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    api_keys = relationship("ApiKey", back_populates="project", cascade="all, delete-orphan")


class ApiKey(Base):
    """Database-backed API keys providing RBAC per project."""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    # Store hashed keys, not plain text, for security
    hashed_key = Column(String(255), unique=True, nullable=False)
    role = Column(String(20), default="viewer", nullable=False)  # 'admin' or 'viewer'
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)

    project = relationship("Project", back_populates="api_keys")


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
    row_count = Column(BigInteger, nullable=False)  # BigInteger supports tables with billions of rows
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
    check_type = Column(String(100), nullable=False)  # soda | great_expectations | custom_sql
    passed = Column(Boolean, nullable=False)
    metric_value = Column(Numeric(precision=20, scale=6), nullable=True)  # Numeric avoids float precision loss
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


class ColumnProfile(Base):
    """Stores column-level statistics for data profiling."""

    __tablename__ = "column_profiles"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(255), nullable=False, index=True)
    column_name = Column(String(255), nullable=False)
    null_count = Column(BigInteger)  # BigInteger for large tables
    null_pct = Column(Float)
    distinct_count = Column(BigInteger)  # BigInteger for large tables
    min_value = Column(String(255))  # stored as string for type flexibility
    max_value = Column(String(255))
    mean_value = Column(Float, nullable=True)
    profiled_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class CheckSuppression(Base):
    """Mutes alerts for a specific table during planned maintenance windows."""

    __tablename__ = "check_suppressions"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(255), nullable=False, index=True)
    suppressed_until = Column(DateTime, nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


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


class DistributionSnapshot(Base):
    """Stores column value distribution snapshots for drift detection."""

    __tablename__ = "distribution_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(255), nullable=False, index=True)
    column_name = Column(String(255), nullable=False, index=True)
    column_type = Column(String(50), nullable=False)  # categorical | numeric
    # JSON blob: {"total_rows": N, "null_pct": 0.02, "top_values": [...]} or histogram dict
    distribution = Column(JSON, nullable=False)
    snapshotted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DistributionDrift(Base):
    """Records detected distribution drift events."""

    __tablename__ = "distribution_drifts"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(255), nullable=False, index=True)
    column_name = Column(String(255), nullable=False)
    # null_pct_change | value_share_shift | mean_shift
    drift_type = Column(String(100), nullable=False)
    previous_value = Column(Text, nullable=True)   # Human-readable description of old state
    current_value = Column(Text, nullable=True)    # Human-readable description of new state
    change_magnitude = Column(Float, nullable=True)  # Fraction (0-1); multiply by 100 for %
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ContractValidationResult(Base):
    """Stores the outcome of each data contract validation run."""

    __tablename__ = "contract_validation_results"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(String(255), nullable=False, index=True)
    contract_version = Column(String(50), nullable=True)
    table_name = Column(String(255), nullable=False, index=True)
    passed = Column(Boolean, nullable=False)
    total_rules = Column(Integer, nullable=False, default=0)
    passed_rules = Column(Integer, nullable=False, default=0)
    # Full list of violation dicts: [{"rule": "...", "passed": false, "detail": "..."}]
    violations_json = Column(JSON, nullable=True)
    validated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
