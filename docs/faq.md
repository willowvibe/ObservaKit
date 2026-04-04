# FAQ — ObservaKit

Frequently asked questions about ObservaKit.

---

## General

### What exactly is data observability?

Data observability is knowing the health of your data **at all times**, without manually querying tables or waiting for dasheholders to file bug reports. The five classic pillars are: Freshness, Volume, Quality, Schema, and Lineage. ObservaKit adds Distribution Drift and Data Contracts on top of these.

### How is ObservaKit different from Great Expectations?

Great Expectations is a quality-check library. You write tests, run them, and get pass/fail. ObservaKit is a full observability layer built on top of that: it stores history, detects anomalies over time, monitors freshness and schema separately, integrates with your orchestrator, and routes alerts to the right channel. Think of GX as a linter and ObservaKit as the full CI pipeline.

### How is it different from Monte Carlo / Metaplane?

Monte Carlo and Metaplane are excellent SaaS products that cost $30k–$100k/year. They're the right choice for large enterprise teams. ObservaKit is for **1–5 person data teams at startups** who need the same capabilities without the sales process or the budget. You self-host it, you own your data, and it's free forever.

### Does ObservaKit send my data anywhere?

No. ObservaKit runs entirely in your environment. The only external HTTP calls are to your configured alert channels (Slack, Discord, etc.). Nothing is sent to WillowVibe or any third party.

### What's the performance impact on my warehouse?

ObservaKit runs scheduled `SELECT COUNT(*)`, `SELECT MAX(timestamp)`, and `information_schema` queries. These are read-only and lightweight. For freshness and volume checks on indexed timestamp columns, a typical query takes < 1 second even on multi-billion-row tables. Distribution snapshots on large tables are the most expensive — throttle the schedule or use table sampling if needed.

---

## Setup & Configuration

### Can I run ObservaKit without Docker?

Yes. Run the FastAPI backend directly:
```bash
pip install -e .
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
You'll need a PostgreSQL database for the metadata store (or use SQLite for single-node dev: set `METADATA_DB_TYPE=sqlite`).

### Can I use SQLite instead of PostgreSQL for the metadata store?

Yes, for development or single-node setups:
```dotenv
METADATA_DB_TYPE=sqlite
```
SQLite is not recommended for production because it doesn't handle concurrent writes well (e.g. the scheduler and an incoming webhook firing simultaneously).

### How do I monitor multiple databases?

Currently ObservaKit monitors one warehouse per instance. To monitor two separate databases, run two instances with different `WAREHOUSE_*` env vars and different metadata DB names. Multi-warehouse support within a single instance is on the roadmap.

### Can I change the scheduler intervals?

Yes. Everything in `config/kit.yml`:
```yaml
freshness:
  schedule_minutes: 15    # default: 15 min

volume:
  schedule_minutes: 60    # default: 60 min

schema_drift:
  schedule_minutes: 360   # default: every 6 hours

distribution:
  schedule_minutes: 360   # default: every 6 hours
```

### How do I add a new warehouse type not in the list?

1. Copy `connectors/postgres.py` as a starting point.
2. Implement the `WarehouseConnector` abstract class (6 methods).
3. Register it in `connectors/base.py`'s `get_warehouse_connector()` factory.
4. Open a PR — we'd love to include it in the official release!

---

## Observability Pillars

### What's the difference between Volume anomaly and a Quality check?

**Volume** tracks total row counts over time using statistical anomaly detection. It answers: "Is there roughly the right amount of data?" It doesn't look at values at all.

**Quality checks** look at the actual data: are there nulls? Duplicate PKs? Out-of-range values? They answer: "Is the data correct?"

Both are necessary. A volume anomaly can tell you a pipeline broke. Quality checks tell you the data that arrived is wrong.

### When should I use Distribution Drift vs Quality Checks?

- Use **Quality Checks** for hard rules that should always be true: "order_id must never be null", "amount must be >= 0".
- Use **Distribution Drift** for soft signals where the historical norm is your reference: "the distribution of `status` values shouldn't change dramatically between runs".

Quality checks are deterministic. Distribution drift is statistical and requires historical data before it becomes meaningful (typically 2+ snapshots).

### What is a Data Contract and when should I use one?

A data contract is a formal YAML file that documents and enforces what a table should look like. Use it when:
- Multiple teams (or services) produce data that analytics/ML depends on.
- You want a single source of truth for "what does this table promise to contain?"
- You're doing a data migration and need to verify the destination matches the source spec.

### How does the dbt integration work?

ObservaKit watches your dbt project directory for `target/run_results.json`. After each `dbt run` or `dbt test`, it reads the file and stores:
- Each model run as a `PipelineRun` record (with duration and status)
- Each test result as a `CheckResult` record

No dbt package installation, no changes to your dbt project, no dbt Cloud required.

---

## Alerts

### How do I route different alert types to different Slack channels?

Use routing rules in `kit.yml`:
```yaml
alerts:
  routing:
    - match:
        alert_type: "schema"
        table_pattern: "payments.*"
      channel: slack
      slack_channel: "#finance-data-alerts"
    - match:
        alert_type: "freshness"
      channel: slack
      slack_channel: "#data-freshness"
    - match:
        alert_type: "contract"
      channel: discord
```

### How do I prevent alert storms during maintenance?

Use suppressions:
```bash
# Via API
curl -X POST http://localhost:8000/suppress \
  -H "X-API-Key: $OBSERVAKIT_API_KEY" \
  -d '{"table_name": "public.orders", "suppress_hours": 4}'

# Via CLI
observakit suppress orders 4h

# Via kit.yml (permanently disable a specific check)
# Set alert: null for that table
```

### Can I integrate with PagerDuty?

Yes — use the generic webhook alert channel and point it at the PagerDuty Events API v2:
```yaml
alerts:
  routing:
    - match:
        alert_type: "quality"
      channel: webhook
      webhook_url: https://events.pagerduty.com/v2/enqueue
```
The webhook payload includes `severity`, `table_name`, `subject`, and `message` fields. You may need a thin middleware to translate the ObservaKit payload to the PagerDuty envelope format. Native PagerDuty integration is planned for v0.3.0.

---

## Security

### How is the API secured?

All API endpoints (except `/healthz`, `/metrics`, and `/`) require an `X-API-Key` header. Set `OBSERVAKIT_API_KEY` in your `.env`. Use a strong random string (e.g. `openssl rand -hex 32`).

CORS is configurable via `CORS_ORIGINS`. For production, set it to only your dashboard domain.

### Can I run ObservaKit in a read-only mode?

The backend itself doesn't write to your warehouse — it only writes to its own metadata DB. The warehouse connection only needs `SELECT` on your target tables and `SELECT` on `information_schema`.

### Should I expose ObservaKit's port publicly?

No. Run it inside your VPC/private network and access it via a VPN or internal load balancer. The API key provides authentication but not encryption — always use TLS in front of it (e.g. an nginx proxy with a certificate).

---

## Operations

### How do I upgrade ObservaKit?

```bash
git pull origin main
docker compose build backend
docker compose up -d backend
# Alembic migrations run automatically on startup
```

### How do I back up the metadata store?

The metadata store is a PostgreSQL database. Back it up like any other Postgres DB:
```bash
docker compose exec postgres pg_dump -U observakit observakit > backup_$(date +%Y%m%d).sql
```

### How do I reset all data and start fresh?

```bash
docker compose down -v   # removes volumes including the metadata DB
docker compose up -d
make demo                # optionally reload mock data
```

### The metadata DB is growing large. How do I purge old data?

Connect to the metadata DB and delete old records:
```sql
-- Delete check results older than 90 days
DELETE FROM check_results WHERE executed_at < NOW() - INTERVAL '90 days';
DELETE FROM volume_records WHERE recorded_at < NOW() - INTERVAL '90 days';
DELETE FROM freshness_records WHERE checked_at < NOW() - INTERVAL '90 days';
-- etc.
```
A scheduled purge task is on the roadmap.
