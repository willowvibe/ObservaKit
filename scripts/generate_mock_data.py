"""
ObservaKit — Comprehensive Demo Data Generator
===============================================
Populates the ObservaKit metadata database with realistic historical data so
you can explore every dashboard tab without connecting to a real data warehouse.

What gets created
-----------------
  Overview tab   : 5 monitored tables with mixed health states (ok / warn / fail)
  Freshness tab  : 7 days of lag records, including a current freshness anomaly
  Quality Checks : 7 days of Soda / GX results with realistic pass / fail rates
  Schema Drift   : 3 historical schema changes across two tables
  Alerts tab     : 50 recent Airflow pipeline run events
  Profiling tab  : Column-level statistics for public.orders and public.customers
  Suppressions   : One active maintenance window suppression

Usage
-----
  # Against the Docker Compose stack (postgres exposed on host port 5433):
  python scripts/generate_mock_data.py

  # Against a local postgres on 5432:
  METADATA_DB_PORT=5432 python scripts/generate_mock_data.py

  # Lite mode — writes to SQLite instead (no Postgres required):
  METADATA_DB_TYPE=sqlite python scripts/generate_mock_data.py

  # After seeding, start the backend and open the dashboard:
  docker-compose up -d
  # Visit http://localhost:8000/ui  or run `make ui-dev`
"""

import os
import random
import sys
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Bootstrap sys.path so we can import backend.models
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------
DB_TYPE = os.getenv("METADATA_DB_TYPE", "postgresql").lower()

if DB_TYPE == "sqlite":
    DATABASE_URL = "sqlite:///./observakit.db"
else:
    DATABASE_URL = (
        f"postgresql://"
        f"{os.getenv('METADATA_DB_USER', 'observakit')}:"
        f"{os.getenv('METADATA_DB_PASSWORD', 'changeme')}@"
        f"{os.getenv('METADATA_DB_HOST', 'localhost')}:"
        f"{os.getenv('METADATA_DB_PORT', '5433')}/"  # 5433 = host-side port in docker-compose
        f"{os.getenv('METADATA_DB_NAME', 'observakit')}"
    )

# ---------------------------------------------------------------------------
# Demo tables — 5 realistic tables across two schemas
# ---------------------------------------------------------------------------
TABLES = [
    "public.orders",
    "public.customers",
    "public.products",
    "analytics.daily_revenue",
    "analytics.user_events",
]

# Freshness SLA thresholds (seconds)
FRESHNESS_WARN_THRESHOLD = 3600  # 1 h
FRESHNESS_FAIL_THRESHOLD = 14400  # 4 h


def _status_for_lag(lag: float) -> str:
    if lag >= FRESHNESS_FAIL_THRESHOLD:
        return "fail"
    if lag >= FRESHNESS_WARN_THRESHOLD:
        return "warn"
    return "ok"


# ---------------------------------------------------------------------------
# Warehouse sample data (optional — creates real tables to profile against)
# ---------------------------------------------------------------------------
WAREHOUSE_URL = (
    f"postgresql://"
    f"{os.getenv('WAREHOUSE_USER', 'observakit')}:"
    f"{os.getenv('WAREHOUSE_PASSWORD', 'changeme')}@"
    f"{os.getenv('WAREHOUSE_HOST', 'localhost')}:"
    f"{os.getenv('WAREHOUSE_PORT', '5433')}/"
    f"{os.getenv('WAREHOUSE_DB', 'observakit')}"
)


def generate_warehouse_data():
    """Create / refresh sample warehouse tables with injected anomalies."""
    print("🏭  Creating warehouse sample tables…")
    try:
        engine = create_engine(WAREHOUSE_URL)
        with engine.begin() as conn:
            # orders — freshness + volume + quality anomalies
            conn.execute(text("DROP TABLE IF EXISTS public.orders CASCADE;"))
            conn.execute(
                text("""
                CREATE TABLE public.orders (
                    order_id    VARCHAR(50),
                    customer_id VARCHAR(50),
                    amount      DECIMAL(10, 2),
                    status      VARCHAR(20),
                    updated_at  TIMESTAMP
                );
            """)
            )
            now = datetime.now(timezone.utc)
            values = []
            for i in range(1000):
                updated = now - timedelta(minutes=random.randint(180, 240))
                values.append(
                    f"('ORD-{i}','CUST-{i % 100}',{random.uniform(10.0, 500.0):.2f},'completed','{updated.isoformat()}')"
                )
            # Inject quality anomalies
            values[-2] = (
                f"(NULL,'CUST-X',999.99,'completed','{(now - timedelta(minutes=180)).isoformat()}')"
            )
            values[-1] = (
                f"('ORD-999','CUST-Y',450.00,'processing','{(now - timedelta(minutes=180)).isoformat()}')"
            )
            conn.execute(
                text(
                    "INSERT INTO public.orders (order_id,customer_id,amount,status,updated_at) VALUES "
                    + ",".join(values)
                )
            )
            print("     ✓ public.orders (1000 rows, freshness+volume+quality anomalies injected)")

            # customers — healthy table
            conn.execute(text("DROP TABLE IF EXISTS public.customers CASCADE;"))
            conn.execute(
                text("""
                CREATE TABLE public.customers (
                    customer_id VARCHAR(50) PRIMARY KEY,
                    email       VARCHAR(255),
                    country     VARCHAR(50),
                    tier        VARCHAR(20),
                    created_at  TIMESTAMP
                );
            """)
            )
            c_vals = []
            for i in range(500):
                updated = now - timedelta(minutes=random.randint(10, 30))
                tier = random.choice(["free", "pro", "enterprise"])
                country = random.choice(["US", "UK", "DE", "FR", "CA"])
                c_vals.append(
                    f"('CUST-{i}','user{i}@example.com','{country}','{tier}','{updated.isoformat()}')"
                )
            conn.execute(
                text(
                    "INSERT INTO public.customers (customer_id,email,country,tier,created_at) VALUES "
                    + ",".join(c_vals)
                )
            )
            print("     ✓ public.customers (500 rows, healthy)")
    except Exception as exc:
        print(f"     ⚠  Could not create warehouse tables ({exc}); skipping.")


# ---------------------------------------------------------------------------
# Metadata population
# ---------------------------------------------------------------------------
def generate_metadata():
    print("📊  Populating ObservaKit metadata database…")
    from backend.models import (
        Base,
        CheckResult,
        CheckSuppression,
        ColumnProfile,
        FreshnessRecord,
        PipelineRun,
        SchemaDiff,
        SchemaSnapshot,
        VolumeRecord,
    )

    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False} if DB_TYPE == "sqlite" else {}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    now = datetime.now(timezone.utc)

    # ---- Truncate all demo tables ----------------------------------------
    print("   Clearing existing demo data…")
    for model in [
        VolumeRecord,
        FreshnessRecord,
        CheckResult,
        PipelineRun,
        SchemaDiff,
        SchemaSnapshot,
        ColumnProfile,
        CheckSuppression,
    ]:
        db.query(model).delete()
    db.commit()

    # =========================================================================
    # 1. FRESHNESS — 7 days of lag records + current anomaly on public.orders
    # =========================================================================
    print("   📅 Generating freshness records…")
    for day in range(7, 0, -1):
        ts = now - timedelta(days=day)
        for table in TABLES:
            if table == "public.orders" and day == 1:
                # Today's run — stale (4.5 h lag → fail)
                lag = random.uniform(16200, 18000)
            elif table == "analytics.daily_revenue" and day <= 2:
                # Slightly late on recent days (warn)
                lag = random.uniform(3700, 7000)
            else:
                lag = random.uniform(60, 1500)  # healthy

            db.add(
                FreshnessRecord(
                    table_name=table,
                    timestamp_column="updated_at",
                    last_updated_at=ts - timedelta(seconds=lag),
                    lag_seconds=lag,
                    status=_status_for_lag(lag),
                    checked_at=ts,
                )
            )

    # Add the current (most-recent) freshness check for each table
    current_lags = {
        "public.orders": random.uniform(16200, 18000),  # fail
        "public.customers": random.uniform(60, 600),  # ok
        "public.products": random.uniform(3700, 5400),  # warn
        "analytics.daily_revenue": random.uniform(3700, 7000),  # warn
        "analytics.user_events": random.uniform(60, 900),  # ok
    }
    for table, lag in current_lags.items():
        db.add(
            FreshnessRecord(
                table_name=table,
                timestamp_column="updated_at",
                last_updated_at=now - timedelta(seconds=lag),
                lag_seconds=lag,
                status=_status_for_lag(lag),
                checked_at=now - timedelta(minutes=2),
            )
        )

    # =========================================================================
    # 2. VOLUME — 7 days of row counts + anomaly today on public.orders
    # =========================================================================
    print("   📈 Generating volume records…")
    volume_baselines = {
        "public.orders": (1700, 50),
        "public.customers": (500, 10),
        "public.products": (3200, 80),
        "analytics.daily_revenue": (90, 5),
        "analytics.user_events": (45000, 1200),
    }
    for day in range(7, 0, -1):
        ts = now - timedelta(days=day)
        for table, (baseline, std) in volume_baselines.items():
            if table == "public.orders" and day == 1:
                # Today: 40 % volume drop → anomaly
                row_count = int(baseline * 0.60)
                is_anomaly = True
            else:
                row_count = max(0, int(random.normalvariate(baseline, std)))
                is_anomaly = False

            rolling_avg = float(baseline)
            deviation_pct = abs(row_count - baseline) / baseline

            db.add(
                VolumeRecord(
                    table_name=table,
                    dag_id=f"{table.replace('.', '_')}_etl",
                    row_count=row_count,
                    rolling_avg=rolling_avg,
                    deviation_pct=deviation_pct,
                    is_anomaly=is_anomaly,
                    recorded_at=ts,
                )
            )

    # =========================================================================
    # 3. QUALITY CHECKS — 7 days, realistic pass rates, failures today
    # =========================================================================
    print("   ✅ Generating quality check records…")
    checks_def = {
        "public.orders": [
            ("Orders table must not be empty", "soda", True, "row_count > 0"),
            ("order_id must not be null", "soda", False, "3 null values found in last run"),
            ("order_id must be unique", "soda", False, "2 duplicate order_ids detected"),
            ("amount must be non-negative", "great_expectations", True, None),
            ("status must be in allowed values", "custom_sql", True, None),
        ],
        "public.customers": [
            ("customer_id must not be null", "soda", True, None),
            ("email must not be null", "soda", True, None),
            ("country must be 2-char ISO code", "great_expectations", True, None),
        ],
        "public.products": [
            ("product_id must not be null", "soda", True, None),
            ("price must be positive", "soda", True, None),
            (
                "category must not be null",
                "great_expectations",
                False,
                "12 rows with null category",
            ),
        ],
        "analytics.daily_revenue": [
            ("revenue must be non-negative", "soda", True, None),
            ("No duplicate date entries", "custom_sql", True, None),
        ],
        "analytics.user_events": [
            ("user_id must not be null", "soda", True, None),
            ("event_type must not be null", "soda", True, None),
            ("timestamp must not be null", "great_expectations", True, None),
        ],
    }

    for day in range(7, 0, -1):
        ts = now - timedelta(days=day)
        for table, checks in checks_def.items():
            for check_name, check_type, today_pass, today_detail in checks:
                if day == 1:
                    # Use today's known state
                    passed = today_pass
                    details = today_detail if not passed else None
                else:
                    # Historical: 97 % pass rate
                    passed = random.random() > 0.03
                    details = "Transient failure" if not passed else None

                db.add(
                    CheckResult(
                        check_name=check_name,
                        table_name=table,
                        check_type=check_type,
                        passed=passed,
                        metric_value=0.0 if passed else 1.0,
                        details=details,
                        executed_at=ts + timedelta(minutes=random.randint(0, 55)),
                    )
                )

    # =========================================================================
    # 4. SCHEMA DRIFT — 3 realistic changes across two tables
    # =========================================================================
    print("   🔀 Generating schema diff records…")

    # Snapshot for public.orders
    orders_columns_v1 = [
        {"name": "order_id", "type": "varchar(50)", "nullable": False, "ordinal": 1},
        {"name": "customer_id", "type": "varchar(50)", "nullable": True, "ordinal": 2},
        {"name": "amount", "type": "decimal(10,2)", "nullable": True, "ordinal": 3},
        {"name": "status", "type": "varchar(20)", "nullable": True, "ordinal": 4},
        {"name": "updated_at", "type": "timestamp", "nullable": True, "ordinal": 5},
    ]
    db.add(
        SchemaSnapshot(
            table_name="public.orders",
            columns_json=orders_columns_v1,
            snapshot_at=now - timedelta(days=7),
        )
    )
    db.add(
        SchemaSnapshot(
            table_name="public.orders",
            columns_json=orders_columns_v1
            + [{"name": "discount_code", "type": "varchar(50)", "nullable": True, "ordinal": 6}],
            snapshot_at=now - timedelta(days=3),
        )
    )

    db.add(
        SchemaDiff(
            table_name="public.orders",
            change_type="added",
            column_name="discount_code",
            old_value=None,
            new_value="varchar(50)",
            detected_at=now - timedelta(days=3),
        )
    )
    db.add(
        SchemaDiff(
            table_name="public.orders",
            change_type="type_changed",
            column_name="amount",
            old_value="decimal(10,2)",
            new_value="decimal(14,4)",
            detected_at=now - timedelta(days=1),
        )
    )
    db.add(
        SchemaDiff(
            table_name="public.customers",
            change_type="removed",
            column_name="legacy_segment",
            old_value="text",
            new_value=None,
            detected_at=now - timedelta(hours=6),
        )
    )

    # =========================================================================
    # 5. PIPELINE RUNS (Alerts tab) — 50 Airflow run events, realistic cadence
    # =========================================================================
    print("   🔔 Generating pipeline run events…")
    dag_names = [
        "marketing_etl_daily",
        "orders_sync_hourly",
        "customer_refresh_daily",
        "revenue_aggregation_daily",
        "user_events_streaming",
    ]
    for i in range(50):
        dag = random.choice(dag_names)
        run_time = now - timedelta(hours=i * random.uniform(0.5, 2.5))
        # 8 % failure rate; orders sync had an outage in the last 6 h
        if dag == "orders_sync_hourly" and i < 4:
            state = "failed"
        else:
            state = "failed" if random.random() < 0.08 else "success"
        duration = random.uniform(120, 1800)
        db.add(
            PipelineRun(
                orchestrator="airflow",
                dag_id=dag,
                run_id=f"run_{run_time.strftime('%Y%m%d%H%M')}_{i}",
                state=state,
                start_time=run_time,
                end_time=run_time + timedelta(seconds=duration),
                duration_seconds=duration,
                recorded_at=run_time + timedelta(seconds=duration + 5),
            )
        )

    # =========================================================================
    # 6. COLUMN PROFILING — public.orders + public.customers
    # =========================================================================
    print("   🔬 Generating column profile records…")
    profiled_at = now - timedelta(hours=1)

    orders_profiles = [
        ("order_id", 1000, 0.003, 999, "ORD-0", "ORD-999", None),
        ("customer_id", 1000, 0.000, 100, "CUST-0", "CUST-99", None),
        ("amount", 1000, 0.000, 892, "10.12", "499.87", 255.34),
        ("status", 1000, 0.000, 2, "completed", "processing", None),
        ("updated_at", 1000, 0.000, 987, "2024-01-09", "2024-01-15", None),
    ]
    for col, total, null_pct, distinct, min_v, max_v, mean_v in orders_profiles:
        null_count = int(total * null_pct)
        db.add(
            ColumnProfile(
                table_name="public.orders",
                column_name=col,
                null_count=null_count,
                null_pct=null_pct,
                distinct_count=distinct,
                min_value=min_v,
                max_value=max_v,
                mean_value=mean_v,
                profiled_at=profiled_at,
            )
        )

    customers_profiles = [
        ("customer_id", 500, 0.000, 500, "CUST-0", "CUST-99", None),
        ("email", 500, 0.000, 500, "user0@example.com", "user99@example.com", None),
        ("country", 500, 0.000, 5, "CA", "US", None),
        ("tier", 500, 0.000, 3, "enterprise", "pro", None),
        ("created_at", 500, 0.000, 498, "2024-01-08", "2024-01-15", None),
    ]
    for col, total, null_pct, distinct, min_v, max_v, mean_v in customers_profiles:
        null_count = int(total * null_pct)
        db.add(
            ColumnProfile(
                table_name="public.customers",
                column_name=col,
                null_count=null_count,
                null_pct=null_pct,
                distinct_count=distinct,
                min_value=min_v,
                max_value=max_v,
                mean_value=mean_v,
                profiled_at=profiled_at,
            )
        )

    # =========================================================================
    # 7. SUPPRESSION — one active maintenance window
    # =========================================================================
    print("   🔕 Adding active suppression for analytics.daily_revenue…")
    db.add(
        CheckSuppression(
            table_name="analytics.daily_revenue",
            suppressed_until=now + timedelta(hours=4),
            reason="Planned warehouse maintenance window — batch backfill in progress",
            created_at=now - timedelta(hours=1),
        )
    )

    db.commit()
    db.close()

    print("\n✅  Demo data generation complete!")
    print("=" * 60)
    print("  Tables monitored  : 5")
    print("  Freshness records : 36 (7-day history + current)")
    print("  Volume records    : 35 (7-day history)")
    print("  Check results     : ~105 (7-day history)")
    print("  Schema diffs      : 3")
    print("  Pipeline runs     : 50")
    print("  Column profiles   : 10 (2 tables)")
    print("  Active suppressions: 1")
    print("=" * 60)
    print("\n🚀  Start the backend:  docker-compose up -d")
    print("    Then open:          http://localhost:8000/ui")
    print("    Or run:             make ui-dev  (React dev server)")


if __name__ == "__main__":
    # Try to create warehouse tables first (optional — silently skipped on failure)
    generate_warehouse_data()
    # Always populate the metadata database
    generate_metadata()
