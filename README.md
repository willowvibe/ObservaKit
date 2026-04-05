<p align="center">
  <a href="https://www.willowvibe.com">
    <img src="willowvibe-logo.png" alt="WillowVibe Logo" width="200" />
  </a>
</p>

<h1 align="center">🔭 ObservaKit</h1>
<p align="center"><strong>Self-hosted data observability for small data teams — free forever.</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/maintained%20by-WillowVibe-6366f1?style=flat-square" />
  <img src="https://img.shields.io/github/license/willowvibe/ObservaKit?style=flat-square" />
  <img src="https://img.shields.io/github/stars/willowvibe/ObservaKit?style=flat-square" />
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square" />
  <img src="https://img.shields.io/badge/docker-compose-2496ED?style=flat-square&logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/version-0.1.10-green?style=flat-square" />
</p>

<p align="center">
  <a href="docs/getting-started.md">Getting Started</a> •
  <a href="docs/real-world-use-cases.md">Use Cases</a> •
  <a href="docs/adding_checks.md">Adding Checks</a> •
  <a href="docs/alerting_setup.md">Alert Setup</a> •
  <a href="docs/faq.md">FAQ</a> •
  <a href="docs/troubleshooting.md">Troubleshooting</a>
</p>

---

> **ObservaKit** gives 1–5 person data teams the same observability pillars that enterprise teams pay $50k/year for — running entirely on your own infrastructure in under 10 minutes.

## Why ObservaKit?

| Pain | Without ObservaKit | With ObservaKit |
|------|--------------------|-----------------|
| Pipeline breaks silently at 3 AM | Dashboard is stale, stakeholders notice first | Freshness alert fires within 15 minutes |
| A column gets renamed in production | Downstream models fail with cryptic errors | Schema drift alert fires at next snapshot |
| Volume drops 70% after a bad deploy | Nobody notices until the weekly meeting | Z-score anomaly fires immediately |
| A vendor changes their API response format | Null % climbs for weeks undetected | Distribution drift alert fires |
| New engineer changes `status` values | Analytics break but tests pass | Data contract violation alert fires |
| "Who broke the orders table?" | Hours of detective work in Slack | Lineage-aware alert names the upstream table |

## The 7 Observability Pillars

| # | Pillar | What It Catches |
|---|--------|-----------------|
| 1 | **🕐 Freshness** | Stale tables — `max(updated_at)` vs SLA threshold |
| 2 | **📊 Volume** | Row-count anomalies — Z-score against 7-day rolling avg |
| 3 | **✅ Quality Checks** | Nulls, duplicates, value ranges, FK violations (Soda Core / GX / custom SQL) |
| 4 | **🔀 Schema Drift** | Added/removed columns, type changes |
| 5 | **🚀 Pipeline Health** | Airflow/Prefect success rates, SLA misses, task durations |
| 6 | **📈 Distribution Drift** | Column value distribution shifts — the silent killer |
| 7 | **📋 Data Contracts** | Schema + business rule violations against producer-defined contracts |

> **Plus:** FinOps Tracker (Snowflake credits / BigQuery bytes), Native dbt Integration, Column Profiling, Cross-table Consistency Checks, and Lineage-aware Alerts.

## Supported Warehouses

| Warehouse | Status |
|-----------|--------|
| PostgreSQL | ✅ Supported |
| BigQuery | ✅ Supported |
| Snowflake | ✅ Supported |
| MySQL / MariaDB | ✅ Supported |
| Amazon Redshift | ✅ Supported |
| DuckDB | ✅ Supported |
| Databricks | ✅ Supported |
| Trino / Presto | ✅ Supported |

## Supported Alert Channels

| Channel | Status |
|---------|--------|
| Slack | ✅ Supported |
| Email (SMTP) | ✅ Supported |
| Discord | ✅ Supported |
| Generic Webhook | ✅ Supported (PagerDuty, Opsgenie, n8n, etc.) |
| Microsoft Teams | ✅ Supported |
| PagerDuty native | ✅ Supported |

## Quickstart (under 10 minutes)

### Prerequisites
- Docker + Docker Compose v2
- Python 3.10+
- A supported SQL warehouse

### 1. Clone
```bash
git clone https://github.com/willowvibe/ObservaKit.git
cd ObservaKit
```

### 2. Configure
```bash
cp .env.example .env
# Minimum required: WAREHOUSE_TYPE, WAREHOUSE_HOST, WAREHOUSE_USER,
# WAREHOUSE_PASSWORD, WAREHOUSE_DB, OBSERVAKIT_API_KEY
```

### 3. Start (Lite Mode — recommended for first run)
```bash
docker compose -f docker-compose.lite.yml up -d
```

For the full observability stack with Prometheus + Grafana:
```bash
docker compose up -d
```

### 4. Try the demo (no warehouse needed)
```bash
make demo
# Seeds 7 days of history with injected anomalies — dashboard populates immediately
```

### 5. Open the dashboard
```
http://localhost:8000/ui          ← Health grid + check results
http://localhost:8000/docs        ← Interactive API (Swagger UI)
http://localhost:8000/healthz     ← Kubernetes health probe
```

### 6. Add your first check
```bash
cp checks/templates/soda/no_nulls_on_pk.yml checks/my_project/orders.yml
# Edit the YAML to point to your table and column
```

Checks run hourly by default. All timings are configurable in `config/kit.yml`.

> **Full step-by-step walkthrough** → [docs/getting-started.md](docs/getting-started.md)

## Configuration

All settings live in `config/kit.yml`. Environment variables are expanded with `${VAR:-default}` syntax.

```yaml
warehouse:
  type: postgres   # postgres | bigquery | snowflake | mysql | redshift

freshness:
  enabled: true
  tables:
    - table: public.orders
      timestamp_column: updated_at
      warn_after: 1h
      fail_after: 2h

distribution:
  enabled: true
  tables:
    - table: public.orders
      columns:
        - name: status
          type: categorical     # tracks top-20 value shares over time
        - name: amount
          type: numeric         # tracks histogram + mean over time

contracts:
  enabled: true
  contracts_dir: config/contracts/  # one YAML file per contract
```

See the [annotated kit.yml](config/kit.yml) for all options.

## Data Contracts

Define a YAML contract for any table and ObservaKit will validate it on every run:

```yaml
# config/contracts/orders_v1.yml
contract:
  id: orders_v1
  version: "1.0.0"
  table: public.orders
  columns:
    - name: status
      nullable: false
      allowed_values: [pending, confirmed, shipped, delivered, cancelled]
    - name: amount
      nullable: false
      min: 0
  rules:
    - name: "No future-dated orders"
      sql: "SELECT COUNT(*) FROM public.orders WHERE created_at > NOW()"
      assert: "result == 0"
```

```bash
curl -X POST http://localhost:8000/contracts/validate \
  -H "X-API-Key: $OBSERVAKIT_API_KEY"
```

> Full guide → [docs/data-contracts.md](docs/data-contracts.md)

## Distribution Drift

The silent killer in production. Your `status` column still exists, your row count is fine — but 80% of orders are now `cancelled` instead of the usual 5%:

```yaml
distribution:
  enabled: true
  tables:
    - table: public.orders
      drift_threshold: 0.10        # alert if any value's share shifts >10%
      null_drift_threshold: 0.05   # alert if null % shifts >5%
      columns:
        - name: status
          type: categorical
```

ObservaKit snapshots distributions on a schedule and compares them. A Slack alert fires before your stakeholders notice.

## CLI

```bash
pip install -e .

observakit status             # full health summary (supports --output json)
observakit check              # run quality checks (supports --output json)
observakit profile            # profile all configured tables
observakit suppress orders 4h # mute alerts for 4 hours (planned maintenance)
observakit validate-config    # dry-run parse kit.yml (no warehouse needed)
observakit diff               # compare schema snapshot vs saved version
observakit init               # interactive setup wizard
observakit test-alert         # fire a manual test notification
```

## Architecture

```mermaid
flowchart TD
    subgraph Warehouses
        W[(PostgreSQL / BigQuery / Snowflake\nMySQL / Redshift)]
    end

    subgraph Orchestration
        O[Airflow / Prefect]
    end

    subgraph ObservaKit Backend
        API[FastAPI Service]
        S[APScheduler]
        DB[(Metadata Store\nPostgreSQL / SQLite)]
    end

    subgraph Observability Pillars
        F[Freshness Poller]
        V[Volume Anomaly Detector]
        Q[Quality Checks\nSoda / GX / Custom SQL]
        SD[Schema Drift Engine]
        DD[Distribution Drift Monitor]
        DC[Data Contracts Validator]
        P[Column Profiler]
    end

    subgraph Integrations
        DBT[Native dbt Parser\nrun_results.json]
        OTEL[OpenTelemetry]
        PROM[Prometheus]
        GRAF[Grafana]
    end

    subgraph Alerts
        SL[Slack (Block Kit)]
        EM[Email]
        DI[Discord]
        WH[Generic Webhook]
        MS[MS Teams]
        PD[PagerDuty]
    end

    W --> F & V & Q & SD & DD & DC & P
    O -- REST API --> API
    DBT --> DB
    S --> F & V & Q & SD & DD & DC
    F & V & Q & SD & DD & DC & P --> DB
    API --> DB
    API --> PROM --> GRAF
    O --> OTEL --> PROM
    DB --> SL & EM & DI & WH
```

## Project Structure

```
ObservaKit/
├── backend/
│   ├── main.py                  ← FastAPI app + /healthz + /status
│   ├── models.py                ← SQLAlchemy models (12 tables)
│   ├── scheduler.py             ← APScheduler (standalone mode)
│   └── routers/
│       ├── checks.py            ← Quality checks + volume + consistency
│       ├── freshness.py         ← Freshness polling
│       ├── schema_diff.py       ← Schema drift detection
│       ├── distribution.py      ← Distribution drift (NEW)
│       ├── contracts.py         ← Data contracts (NEW)
│       ├── finops.py            ← Cost tracking
│       ├── profiling.py         ← Column profiling
│       ├── suppressions.py      ← Alert suppression windows
│       └── webhooks.py          ← Incoming webhooks
├── connectors/
│   ├── postgres.py              ← PostgreSQL
│   ├── bigquery.py              ← BigQuery
│   ├── snowflake.py             ← Snowflake
│   ├── mysql.py                 ← MySQL / MariaDB
│   ├── redshift.py              ← Amazon Redshift
│   ├── duckdb.py                ← DuckDB (NEW)
│   ├── databricks.py            ← Databricks (NEW)
│   └── trino.py                 ← Trino (NEW)
├── alerts/
│   ├── slack.py                 ← Slack (Block Kit + Retries)
│   ├── email.py                 ← SMTP email
│   ├── discord.py               ← Discord webhooks
│   ├── teams.py                 ← MS Teams (NEW)
│   ├── pagerduty.py             ← PagerDuty Native (NEW)
│   └── webhook.py               ← Generic outgoing webhook
├── config/
│   ├── kit.yml                  ← Master config (all pillars)
│   ├── contracts/               ← Data contract YAML files (NEW)
│   │   └── example_orders.yml
│   └── warehouses/              ← Per-warehouse connection configs
├── checks/
│   ├── templates/               ← Soda Core + Great Expectations templates
│   └── examples/                ← Example checks for orders, self-checks
├── dbt_integration/             ← Native dbt artifact parser
├── landing-page/                ← Vite/React embedded dashboard
├── cli/                         ← observakit CLI
├── tests/                       ← Pytest suite
├── docs/                        ← Full documentation
├── grafana/                     ← Grafana dashboard provisioning
├── prometheus/                  ← Prometheus config
├── otel/                        ← OpenTelemetry collector config
├── docker-compose.yml           ← Full stack
├── docker-compose.lite.yml      ← Lite mode (backend + postgres only)
└── Makefile                     ← make up / down / test / demo
```

## Comparison with Alternatives

| Feature | ObservaKit | Monte Carlo | Metaplane | Great Expectations |
|---------|-----------|-------------|-----------|-------------------|
| **Price** | Free / self-hosted | $30k–$100k/yr | $15k–$50k/yr | Free (OSS) |
| **Setup time** | < 10 min | Days (sales cycle) | Days | Hours–Days |
| **Self-hosted** | ✅ | ❌ SaaS only | ❌ SaaS only | ✅ |
| **Freshness monitoring** | ✅ | ✅ | ✅ | ❌ |
| **Volume anomaly detection** | ✅ | ✅ | ✅ | ❌ |
| **Distribution drift** | ✅ | ✅ | ✅ | Partial |
| **Schema drift** | ✅ | ✅ | ✅ | ❌ |
| **Data contracts** | ✅ | ✅ (enterprise) | ❌ | ❌ |
| **Native dbt integration** | ✅ (no packages) | ✅ | ✅ | Partial |
| **Pipeline health (Airflow/Prefect)** | ✅ | ✅ | Partial | ❌ |
| **FinOps tracking** | ✅ | ❌ | ❌ | ❌ |
| **MySQL / Redshift support** | ✅ | ✅ | Partial | ✅ |
| **Discord alerts** | ✅ | ❌ | ❌ | ❌ |
| **Vendor lock-in** | ❌ None | 🔒 High | 🔒 High | ❌ None |

## Real-World Use Cases

- **Data migration audits** — Run ObservaKit against source and destination simultaneously to guarantee zero schema drift and 100% volume parity during cloud migrations.
- **dbt project health** — Parse `run_results.json` natively; no Elementary package or dbt Cloud required. Track model success rates and test failures in one place.
- **Multi-team data contracts** — Each producing team owns a contract YAML. ObservaKit validates it on every pipeline run and alerts consumers before they're broken.
- **Cost governance** — Track Snowflake credit burn and BigQuery bytes billed per pipeline. Alert when a single query scans more than a configured threshold.
- **Seed-stage startups** — Get enterprise-grade data observability on a startup budget. Replace ad-hoc Slack messages with structured, routed alerts.

Full scenarios → [docs/real-world-use-cases.md](docs/real-world-use-cases.md)

## Makefile Commands

```bash
make up           # Start full stack (Prometheus + Grafana)
make up-lite      # Start lite mode (backend + postgres only)
make down         # Stop all services
make build        # Rebuild backend Docker image
make test         # Run pytest suite
make test-cov     # Run tests with coverage report
make lint         # Ruff linting
make format       # Auto-format with ruff
make migrate      # Run Alembic migrations
make demo         # Generate 7 days of mock data with anomalies
make logs         # Follow backend logs
make dev          # Run in dev mode (hot reload)
make ui-build     # Build React dashboard
```

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](docs/getting-started.md) | Step-by-step first 15 minutes |
| [Adding Checks](docs/adding_checks.md) | Write Soda, GX, and custom SQL checks |
| [Data Contracts](docs/data-contracts.md) | Define and enforce data contracts |
| [Alert Setup](docs/alerting_setup.md) | Configure Slack, Email, Discord, Webhooks |
| [Architecture](docs/architecture.md) | System design with diagrams |
| [Real-World Use Cases](docs/real-world-use-cases.md) | How real teams use ObservaKit |
| [FAQ](docs/faq.md) | Frequently asked questions |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and fixes |

> 📹 **Video walkthrough coming soon** — follow the repo to be notified.

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Good first issues:**
- Add a Grafana dashboard for a new use case
- Write a quality check template for a common schema pattern
- Improve documentation or add a tutorial
- Add column-level lineage tracking
- Improve the CLI experience with autocomplete

## License

MIT — free to use, modify, and distribute.

---

**Built by [WillowVibe DataSynapse](https://www.willowvibe.com)** — AI-first data enablement for modern teams.
