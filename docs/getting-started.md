# Getting Started with ObservaKit

This guide takes you from zero to a fully running observability layer in about 15 minutes.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Docker + Docker Compose v2 | `docker compose version` should show v2.x |
| Python 3.10+ | Only needed if you want the CLI or dev mode |
| A supported warehouse | PostgreSQL, MySQL, Snowflake, BigQuery, Redshift, DuckDB, Databricks, or Trino |

---

## Step 1 — Clone and configure

```bash
git clone https://github.com/willowvibe/ObservaKit.git
cd ObservaKit
pip install -e .
observakit init
```

The interactive wizard will help you:
1. Create your `.env` file with warehouse credentials
2. Select your warehouse type (Postgres, BigQuery, Snowflake, etc.)
3. Configure your first alert channel (Slack, Teams, PagerDuty)
4. Verify your connection immediately

Open `.env` and set at minimum:

```dotenv
# The warehouse you want to observe
WAREHOUSE_TYPE=postgres
WAREHOUSE_HOST=your-db-host
WAREHOUSE_PORT=5432
WAREHOUSE_USER=your-user
WAREHOUSE_PASSWORD=your-password
WAREHOUSE_DB=your-database

# A random string to protect the API
OBSERVAKIT_API_KEY=change-me-to-a-long-random-string

# Where to send alerts (optional for first run)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

> **Note**: ObservaKit connects to your warehouse **read-only** for most operations (freshness, volume, schema checks). It only needs a user with `SELECT` on `information_schema` and your monitored tables.

### 1.1 — Validate Configuration

Before starting the containers, ensure your `kit.yml` is syntactically correct:

```bash
observakit validate-config
# → ✅ Configuration valid (found 12 table monitors)
```

---

## Step 2 — Start the service

**Lite mode** (recommended first run — Backend + Metadata DB only):
```bash
docker compose -f docker-compose.lite.yml up -d
```

**Full stack** (adds Prometheus metrics + Grafana dashboards):
```bash
docker compose up -d
```

Check it's running:
```bash
curl http://localhost:8000/healthz
# → {"status": "ok", "database": "ok", "version": "0.1.10"}
```

---

## Step 3 — Try the demo (no warehouse needed)

This generates 7 days of simulated history with injected anomalies so you can see the UI immediately:

```bash
make demo
```

Then open:
- **Dashboard**: http://localhost:8000/ui
- **API**: http://localhost:8000/docs

You'll see a health grid with freshness violations, volume anomalies, and schema drift — all simulated.

---

## Step 4 — Configure your first table

Edit `config/kit.yml`. At minimum, add your table to the freshness and volume monitors:

```yaml
warehouse:
  type: postgres   # or mysql | snowflake | bigquery | redshift
  config_file: config/warehouses/postgres.yml

freshness:
  enabled: true
  tables:
    - table: public.orders      # use schema.table format
      timestamp_column: updated_at
      warn_after: 1h
      fail_after: 2h
      alert: slack

volume:
  enabled: true
  tables:
    - table: public.orders
      anomaly_threshold: 0.3    # alert if row count deviates >30% from 7-day avg
      alert: slack
```

> The freshness and volume monitors run on a schedule (every 15 and 60 minutes by default). They also run immediately when you call `POST /freshness/poll` or `POST /checks/volume`.

---

## Step 5 — Add quality checks

Copy a template and edit it:

```bash
cp checks/templates/soda/no_nulls_on_pk.yml checks/my_project/orders.yml
```

Edit `checks/my_project/orders.yml`:

```yaml
checks for public.orders:
  - row_count > 0
  - missing_count(order_id) = 0       # no null PKs
  - duplicate_count(order_id) = 0     # PK must be unique
  - min(amount) >= 0                   # no negative revenue
  - invalid_count(status) = 0:
      valid values: [pending, confirmed, shipped, delivered, cancelled]
```

Trigger manually:
```bash
curl -X POST http://localhost:8000/checks/run \
  -H "X-API-Key: $OBSERVAKIT_API_KEY"
```

---

## Step 6 — Set up schema drift

Add your tables to schema monitoring in `kit.yml`:

```yaml
schema_drift:
  enabled: true
  tables:
    - public.orders
    - public.customers
    - public.payments
```

Take the first snapshot:
```bash
curl -X POST http://localhost:8000/schema/snapshot \
  -H "X-API-Key: $OBSERVAKIT_API_KEY"
```

From now on, every snapshot run compares against the previous one. If a column is added, removed, or its type changes, you get an alert.

---

## Step 7 — Enable distribution drift (optional but recommended)

Add to `kit.yml`:

```yaml
distribution:
  enabled: true
  tables:
    - table: public.orders
      drift_threshold: 0.10
      columns:
        - name: status
          type: categorical
        - name: amount
          type: numeric
```

This catches the "silent killer" scenario: the schema looks fine, the row count looks fine, but the distribution of values has shifted.

---

## Step 8 — Add a data contract (optional)

Copy the example contract:

```bash
cp config/contracts/example_orders.yml config/contracts/orders_v1.yml
# Edit to match your actual table and rules
```

Enable contracts in `kit.yml`:

```yaml
contracts:
  enabled: true
  contracts_dir: config/contracts/
```

Validate manually:
```bash
curl -X POST http://localhost:8000/contracts/validate \
  -H "X-API-Key: $OBSERVAKIT_API_KEY"
```

---

## Step 9 — Connect dbt (if you use it)

If your team uses dbt, ObservaKit can parse `run_results.json` and `manifest.json` directly — no dbt packages required:

```yaml
dbt:
  enabled: true
  project_dir: /path/to/your/dbt/project
  auto_parse_on_run: true
  poll_interval_minutes: 5
```

dbt test results are stored as `CheckResult` records. dbt model runs are stored as `PipelineRun` records. You get a unified view of both warehouse-level and dbt-level quality in the same dashboard.

---

## Step 10 — Install the CLI (optional)

```bash
pip install -e .
observakit status
```

```
Table              Freshness   Volume   Quality   Schema
─────────────────  ──────────  ───────  ────────  ──────
public.orders      ok          ok       warn      ok
public.customers   ok          ok       ok        fail
```

---

## What's next?

- [Adding Checks](adding_checks.md) — Soda Core, Great Expectations, and custom SQL
- [Alert Setup](alerting_setup.md) — Slack, Email, Discord, generic webhook
- [Data Contracts](data-contracts.md) — Enforcing producer-consumer agreements
- [Real-World Use Cases](real-world-use-cases.md) — How teams use ObservaKit in production
- [Troubleshooting](troubleshooting.md) — Common issues and fixes
