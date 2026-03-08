import os
import random
import sys
from datetime import datetime, timedelta, timezone

# Add the project root to sys.path so we can import backend.models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 1. Setup metadata DB connection (the one that powers ObservaKit)
# By default, use localhost:5433 since that's what docker-compose exposes for the host
METADATA_URL = (
    f"postgresql://"
    f"{os.getenv('METADATA_DB_USER', 'observakit')}:"
    f"{os.getenv('METADATA_DB_PASSWORD', 'changeme')}@"
    f"{os.getenv('METADATA_DB_HOST', 'localhost')}:"
    f"{os.getenv('METADATA_DB_PORT', '5433')}/"
    f"{os.getenv('METADATA_DB_NAME', 'observakit')}"
)

# 2. Setup warehouse DB connection (the one we monitor)
WAREHOUSE_URL = (
    f"postgresql://"
    f"{os.getenv('WAREHOUSE_USER', 'observakit')}:"
    f"{os.getenv('WAREHOUSE_PASSWORD', 'changeme')}@"
    f"{os.getenv('WAREHOUSE_HOST', 'localhost')}:"
    f"{os.getenv('WAREHOUSE_PORT', '5433')}/"
    f"{os.getenv('WAREHOUSE_DB', 'observakit')}"
)

def generate_warehouse_data():
    print("🚀 Generating target warehouse data (public.orders)...")
    engine = create_engine(WAREHOUSE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS public.orders CASCADE;"))
        conn.execute(text("""
            CREATE TABLE public.orders (
                order_id VARCHAR(50),
                customer_id VARCHAR(50),
                amount DECIMAL(10, 2),
                status VARCHAR(20),
                updated_at TIMESTAMP
            );
        """))

        print("   - Injecting Volume Anomaly (Current row count drops by 40% from ~1700 to 1000)...")
        print("   - Injecting Freshness Anomaly (max updated_at is > 3 hours old)...")
        
        values = []
        now = datetime.now(timezone.utc)
        for i in range(1000):
            # 3 to 4 hours ago for freshness anomaly
            updated = now - timedelta(minutes=random.randint(180, 240)) 
            values.append(f"('ORD-{i}', 'CUST-{i%100}', {random.uniform(10.0, 500.0):.2f}, 'completed', '{updated.isoformat()}')")
        
        print("   - Injecting Quality Anomalies (NULL and duplicate order_id)...")
        # NULL primary key
        values[-2] = f"(NULL, 'CUST-X', 999.99, 'completed', '{(now - timedelta(minutes=180)).isoformat()}')"
        # Duplicate primary key
        values[-1] = f"('ORD-999', 'CUST-Y', 450.00, 'processing', '{(now - timedelta(minutes=180)).isoformat()}')"

        insert_query = f"INSERT INTO public.orders (order_id, customer_id, amount, status, updated_at) VALUES {','.join(values)};"
        conn.execute(text(insert_query))


def generate_metadata_history():
    print("🚀 Generating ObservaKit historical metadata (7 days)...")
    from backend.models import (
        Base, VolumeRecord, FreshnessRecord, CheckResult, PipelineRun
    )
    engine = create_engine(METADATA_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    now = datetime.now(timezone.utc)

    # Truncate existing to avoid duplicates in demo mode
    db.query(VolumeRecord).delete()
    db.query(FreshnessRecord).delete()
    db.query(CheckResult).delete()
    db.query(PipelineRun).delete()

    print("   - Populating 7 days of Pipeline Runs, Volume Stats, and Quality Checks...")
    for day_offset in range(7, 0, -1):
        record_date = now - timedelta(days=day_offset)
        
        # 1. Pipeline Runs (DAG successes and occasional failures)
        for hour in range(24):
            run_time = record_date.replace(hour=hour, minute=0, second=0)
            state = "success" if random.random() > 0.05 else "failed" # 5% failure rate
            db.add(PipelineRun(
                orchestrator="airflow",
                dag_id="marketing_etl_daily",
                run_id=f"run_{run_time.strftime('%Y%m%d%H')}",
                state=state,
                start_time=run_time,
                end_time=run_time + timedelta(minutes=random.randint(5, 25)),
                duration_seconds=random.uniform(300, 1500),
                recorded_at=run_time + timedelta(minutes=30)
            ))

        # 2. Volume Records (average ~1700 rows historically)
        row_count = int(random.normalvariate(1700, 50))
        db.add(VolumeRecord(
            table_name="public.orders",
            dag_id="marketing_etl_daily",
            row_count=row_count,
            rolling_avg=1700.0,
            deviation_pct=abs(row_count - 1700) / 1700.0,
            is_anomaly=False,
            recorded_at=record_date
        ))

        # 3. Check Results (mostly passing historically)
        for check in ["Orders table must not be empty", "order_id must not be null", "order_id must be unique", "Order amount must be non-negative"]:
            passed = random.random() > 0.02 # 98% pass rate historically
            db.add(CheckResult(
                check_name=check,
                table_name="public.orders",
                check_type="soda",
                passed=passed,
                metric_value=0.0 if passed else 1.0,
                executed_at=record_date
            ))

    db.commit()
    db.close()
    print("✅ Mock data generation complete!")
    print("Next step: Run 'docker-compose up -d' and 'make run-checks' to see metrics!")


if __name__ == '__main__':
    generate_warehouse_data()
    generate_metadata_history()
