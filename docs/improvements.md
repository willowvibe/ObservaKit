Based on full inspection of the repo structure, `pyproject.toml`, `README.md`, `tests/`, `backend/`, `docs/`, and `connectors/` , here is the complete actionable list — organized by domain:

***

## 🔐 Security & Auth

**Add:**
- `backend/auth.py` currently only does single API-key check  — replace with per-project API keys (1 key per configured project/team)
- Role-based access: at minimum a `viewer` vs `admin` distinction in a `users` table + middleware
- HTTPS / TLS configuration guide for the FastAPI service and between containers
- Secret management docs: IAM-based auth for BigQuery/Snowflake (service accounts), Vault/KMS integration notes
- Audit log model + router: record every check trigger, config mutation, contract change, suppression window create/delete
- PII redaction config: a flag to never log raw column sample values into the metadata store

**Modify:**
- `.env.example`  — add notes for each secret explaining safer alternatives (e.g., `GOOGLE_APPLICATION_CREDENTIALS` instead of raw keys for BQ)
- `SECURITY.md`  — currently minimal; expand with vulnerability disclosure timeline, supported versions, and CVE contact

***

## 🏗️ Backend / API

**Add:**
- Multi-project model: `Project` table with scoped configs, isolated check runs, and per-project alert routing
- Pydantic v2 request/response schemas (separate from SQLAlchemy models) — right now `models.py` is 9KB of SQLAlchemy  with no sign of Pydantic schemas for API contracts
- API versioning prefix: `/api/v1/` on all routes (future-proof)
- OpenAPI spec (`openapi.json`) checked into repo and versioned per release
- Pagination on all list endpoints (checks, runs, alerts, profiles)
- `GET /api/v1/status` detailed health breakdown per pillar (not just `/healthz`)
- Background task queue concept — right now APScheduler runs in-process ; add a note/path for offloading to Celery/ARQ for scale

**Modify:**
- `backend/main.py` (13KB)  — split into smaller modules; it's doing too much in one file
- `backend/scheduler.py`  — add job locking / idempotency guard so double-firing on multiple replicas doesn't cause duplicate alerts

***

## 🧪 Testing

**Add (missing tests for headline features):**
- `tests/test_distribution_drift.py` — test snapshot comparison, threshold triggers, categorical vs numeric paths
- `tests/test_contracts.py` — test YAML loading, SQL assertion eval, `allowed_values` check, FK rule
- `tests/test_alerts.py` — mock Slack/email/Discord/webhook; verify payload structure, retry on failure, suppress window honoring
- `tests/test_cli.py` — test `status`, `check`, `profile`, `suppress` CLI commands via `click.testing.CliRunner`
- `tests/test_api_auth.py` — test API key rejection, missing key, invalid key
- `tests/test_suppressions.py` — test suppression window logic (active/expired/future windows)
- E2E integration test: spin up Dockerized Postgres + fake Slack endpoint → config → scheduler → check → alert fired 
- Coverage gate: add `--cov-fail-under=70` to CI so coverage doesn't silently drop

**Modify:**
- `tests/conftest.py`  — add shared fixtures for fake warehouse connector, fake alert dispatcher, seeded metadata DB
- `tests/test_connectors.py`  — add connection timeout and retry behavior tests, not just happy path

***

## 🚀 Deployment & Operations

**Add:**
- `k8s/` directory with: Deployment + Service manifests for backend, ConfigMap for `kit.yml`, Secret template for `.env`, HPA (Horizontal Pod Autoscaler) example
- `k8s/README.md` — sizing guide (CPU/memory per N tables checked per hour)
- Multi-env config pattern: `config/kit.dev.yml`, `config/kit.staging.yml`, `config/kit.prod.yml` with environment override docs
- `docs/production-guide.md` — cover HA topology, scaling scheduler vs API separately, Postgres connection pooling (`pgbouncer` recommendation), log aggregation
- `docs/upgrade-guide.md` — Alembic migration compatibility matrix, rollback procedure, how to check which migration version is running 
- `docs/backup-restore.md` — how to backup the metadata Postgres, restore, point-in-time recovery basics
- Runbook stubs in `docs/runbooks/`: "alert storm", "scheduler stuck", "DB migration failed", "connector timeout spike"
- `docker-compose.yml`  — add `restart: unless-stopped`, resource `limits` (memory/cpu), and `healthcheck` for the backend service

**Modify:**
- `backend/Dockerfile`  — add multi-stage build (builder + slim runtime), non-root user (`USER app`), and `HEALTHCHECK` instruction
- `docker-compose.yml`  — pin all image versions (not `latest`)

***

## 🔌 Connectors

**Add:**
- `connectors/duckdb.py` — planned in roadmap ; DuckDB is increasingly popular for local/embedded pipelines
- `connectors/databricks.py` — also planned ; required for teams on Databricks Lakehouse
- `connectors/trino.py` — common in federated query setups (Iceberg, Hive, Delta Lake)
- Connection pool management per connector (SQLAlchemy `pool_size`, `max_overflow`, `pool_timeout` configs)
- Connection retry with exponential backoff + dead-letter on repeated failure
- `connectors/base.py` — abstract base class with interface contract so all connectors are guaranteed to implement `test_connection()`, `get_schema()`, `run_query()`, `get_row_count()`
- `tests/` — integration tests per connector using `testcontainers-python` (spin up real Postgres/MySQL containers)

**Modify:**
- `connectors/bigquery.py`  — add IAM workload identity / service account JSON path support (not just API key)
- `connectors/snowflake.py`  — add key-pair auth support (required by enterprise Snowflake admins)

***

## 🔔 Alerting

**Add:**
- `alerts/teams.py` — Microsoft Teams webhook dispatcher (planned in roadmap )
- `alerts/pagerduty.py` — native PagerDuty Events API v2 (not just generic webhook) with severity mapping and dedup key
- Alert grouping/dedup: if the same check fails 5 times in a row, send 1 alert + "still failing" updates, not 5 separate pings
- Severity levels on alerts: `INFO`, `WARN`, `CRITICAL` — routable to different channels
- Alert routing rules in `kit.yml`: e.g., `CRITICAL` → PagerDuty, `WARN` → Slack, `INFO` → email digest
- Alert templates: configurable message body with `{{table}}`, `{{check_name}}`, `{{value}}`, `{{threshold}}`, `{{run_id}}` variables
- Digest/batching mode: hourly digest email instead of individual alerts (for noisy environments)
- `tests/test_alerts.py` — mock all dispatchers (see Testing section above) 

**Modify:**
- `alerts/slack.py`  — use Block Kit layout (not plain text) with buttons linking to dashboard and lineage; add retry logic on 429/5xx
- `alerts/webhook.py`  — add HMAC signature header for outbound payloads (PagerDuty, n8n, etc. expect this)

***

## ⚙️ Config & Multi-Env

**Add:**
- Config schema validation on startup: if `kit.yml` is malformed, fail fast with a human-readable error (not a Python traceback)
- JSON Schema or Pydantic model for `kit.yml` — publishable so editors (VS Code, etc.) can provide autocomplete
- Config diff API: `GET /api/v1/config/diff` — show what changed since last load (useful in GitOps)
- `config/contracts/`  — add a `README.md` explaining contract YAML schema, versioning, and how consumers subscribe
- Per-table override for schedule: `cron` expression per check, not just global schedule

**Modify:**
- `config/kit.yml`  — add `environments` top-level key with env-specific overrides (warehouse creds, thresholds, alert channels)
- `.env.example`  — split into groups: `# Warehouse`, `# Auth`, `# Alerts`, `# Feature Flags` for clarity

***

## 📚 Documentation

**Add (files to create):**
- `docs/production-guide.md` — HA deployment, sizing, env strategy, secrets management 
- `docs/upgrade-guide.md` — version compatibility, migration steps, rollback 
- `docs/backup-restore.md` — metadata DB backup/restore 
- `docs/security.md` (full) — network isolation, TLS, secrets, RBAC, audit log, PII handling
- `docs/runbooks/` — operational playbooks (scheduler stuck, alert storm, connector timeout)
- `docs/connector-guide.md` — per-warehouse connection setup (IAM, service accounts, firewall rules)
- `docs/api-reference.md` — hand-written supplement to Swagger with pagination, auth examples, error codes
- `docs/contributing/architecture-decisions.md` — ADR (Architecture Decision Records) for key choices (APScheduler vs Celery, SQLite vs Postgres metadata store, etc.)

**Modify:**
- `CHANGELOG.md`  — currently 315 bytes; switch to [Keep a Changelog](https://keepachangelog.com) format with `Added / Changed / Deprecated / Removed / Fixed / Security` sections
- `ROADMAP.md`  — add estimated timelines and acceptance criteria per milestone
- `README.md`  — fix version badge mismatch (`0.1.7` badge vs `0.1.10` in `pyproject.toml` )

***

## 📦 Packaging & Distribution

**Add:**
- Published Docker image on GHCR (`ghcr.io/willowvibe/observakit`) with tags per Git release (`v0.1.10`, `latest`, `main`)
- GitHub Actions workflow: `release.yml` — build + push Docker image on tag push, publish to PyPI
- PyPI publish workflow (package is installable via `pip install -e .` locally  but not on PyPI yet)
- `SLSA` / supply chain: add `sigstore` signing of release artifacts (increasingly expected in OSS data tools)
- Semantic versioning policy in `CONTRIBUTING.md` : define what constitutes a major/minor/patch change for this project

**Modify:**
- `pyproject.toml`  — fix `build-backend = "setuptools.backends._legacy:_Backend"` → use `"setuptools.build_meta"` (legacy backend is deprecated)
- `pyproject.toml`  — add `mysql` and `redshift` as named extras (currently only `bigquery`, `snowflake`, `soda-*` extras exist despite MySQL/Redshift connectors being in )
- `pyproject.toml`  — add `pytest-asyncio` to dev deps (FastAPI async routes need it for proper testing)

***

## 💻 CLI

**Add:**
- `observakit init` — interactive setup wizard: detect warehouse type, write `kit.yml`, test connection, create first check
- `observakit validate-config` — dry-run parse of `kit.yml` + contracts without connecting to warehouse
- `observakit test-alert` — fire a test alert to configured channels (essential for onboarding)
- `observakit diff` — compare current schema snapshot vs last saved snapshot (offline, no scheduler needed)
- Shell completion: `observakit --install-completion` (Click supports this natively)
- `--output json` flag on `status` and `check` for scripting/CI use

**Modify:**
- `cli/main.py` — add `--config` flag to override default `config/kit.yml` path (critical for multi-env use)
- `cli/main.py` — add proper exit codes: `0` = pass, `1` = check failures, `2` = config error (enables CI pipeline integration)

***

## ✅ Checks & Contracts

**Add:**
- UI: "Test this check now" button in dashboard → preview failing rows (even a simple `LIMIT 10` display)
- Auto-suggest checks from profiler output: if profiler detects a column has `null_pct > 0` on a PK, suggest a `not_null` check
- Check inheritance / templates: a base template `checks/templates/base_table.yml` that any table check can `extends:` from
- `checks/` — add Trino, DuckDB, and Databricks template variants (not just Soda/GX) 
- Contract evolution: `version` field on contracts + diff alert when producer changes contract without bumping version 
- Cross-table consistency check templates (README mentions this feature  but `docs/` has no guide for it)

**Modify:**
- `checks/templates/`  — add `README.md` explaining when to use Soda Core vs Great Expectations vs raw SQL checks
- `config/contracts/example_orders.yml`  — add more realistic examples: FK integrity rule, regex pattern check, time-series window check

***

## 🗓️ Scheduler

**Add:**
- Job locking via DB advisory lock or `apscheduler`'s `SQLAlchemyJobStore` so multiple replicas don't double-fire
- Per-check `enabled: false` flag — skip a specific check without removing it from config
- Backfill command: `observakit backfill --table orders --from 2026-01-01` — rerun checks against historical snapshots
- Scheduler observability: expose `GET /api/v1/scheduler/jobs` listing next run times and last run status

**Modify:**
- `backend/scheduler.py`  — add structured logging (JSON) with `run_id`, `pillar`, `table`, `duration_ms` on every job execution
- `backend/scheduler.py`  — wrap each job in try/except so one bad connector doesn't crash the entire scheduler loop

***

## 🌿 dbt Integration

**Add:**
- Auto-generate check stubs from `schema.yml` test definitions (if a dbt model has `not_null` tests, create matching ObservaKit checks)
- `manifest.json` parsing (not just `run_results.json`) — to extract lineage graph and surface upstream/downstream context in alerts
- dbt Cloud webhook receiver: `POST /webhooks/dbt-cloud` — trigger freshness/volume checks after a dbt job completes

**Modify:**
- `dbt_integration/`  — add a `README.md` explaining the integration model (what's read, what's written, how to configure path)

***

## 📊 UI / Dashboard

**Add:**
- Check authoring form: minimal UI to create/edit a check YAML without leaving the browser
- Lineage view: simple directed graph showing upstream tables for a failing check (even a static Mermaid diagram per table)
- Historical trend chart per check: sparkline of pass/fail over last 30 days
- User preference: timezone selector (all timestamps localized client-side)
- Alert inbox tab: browsable history of all fired alerts with filter by pillar/table/severity

**Modify:**
- `landing-page/`  — add `README.md` explaining how to build (`make ui-build`) and what framework/version is used
- Dashboard — add dark mode toggle (light/dark preference persistence)

***

## 💰 FinOps Tracker

**Add:**
- Cost anomaly detection: alert if a single query/model scans >X% above rolling 7-day average (not just threshold breach)
- Per-model cost attribution from dbt: tag Snowflake credits / BQ bytes to the dbt model that triggered them
- Cost export: `GET /api/v1/finops/export?format=csv&from=2026-01-01` for finance team reporting

**Modify:**
- `tests/test_finops.py`  — currently 1.7KB; add tests for threshold alerts and time-window aggregations

***

## 🧹 Code Quality & Repo Hygiene

**Add:**
- `pre-commit` config (`.pre-commit-config.yaml`): ruff + mypy + check for secrets (e.g., `detect-secrets`)
- Type annotations across all Python files — `mypy` strict mode configured in `pyproject.toml`
- `mypy` added to dev deps in `pyproject.toml` 
- `.github/workflows/ci.yml` — lint + test + coverage on every PR (currently `.github/` exists  but CI content unknown)
- `CODEOWNERS` file: assign ownership per directory (`/connectors` → connector maintainer, `/alerts` → alert maintainer)
- Issue templates: Bug Report, Feature Request, Connector Request, New Check Template

**Modify:**
- `pyproject.toml`  — `ruff` config currently ignores `E501` (line length); enable it or at least enforce a consistent line length
- `.gitignore`  — ensure `config/kit.yml` is in `.gitignore` (users may put real creds in it) and that only `config/kit.yml.example` is committed
- `VERSION` file  — sync with `pyproject.toml` version (`0.1.10` ) and automate this in the release workflow

***

## Priority Order (Starter-Kit → Production-Ready Path)

| Priority | Area | Why |
|---|---|---|
| 🔴 P0 | Tests for distribution drift + contracts + alerts  | Headline features with zero test coverage |
| 🔴 P0 | Fix `pyproject.toml` build backend + version sync  | Breaks installs and erodes trust |
| 🔴 P0 | Scheduler job locking  | Silent data corruption risk on multi-replica |
| 🟠 P1 | Production deployment guide + K8s manifests  | First thing platform engineers ask for |
| 🟠 P1 | Per-project API keys + basic RBAC  | Blocks any multi-team use |
| 🟠 P1 | `observakit init` wizard + `test-alert` CLI | Reduces onboarding friction dramatically |
| 🟡 P2 | Connector base class + retry/pool | Stability for production environments |
| 🟡 P2 | Alert dedup/grouping + severity routing | Alert fatigue is the #1 reason people abandon observability tools |
| 🟢 P3 | DuckDB, Trino, Databricks connectors | Expands addressable user base |
| 🟢 P3 | Check authoring UI + auto-suggest from profiler | Dramatically improves day-to-day UX |