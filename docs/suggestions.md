Great progress — almost all the critical bugs from last session are fixed. Here's the full picture of what's confirmed working vs. what a real user will still hit as friction, traced from the actual current repo state.

***

## ✅ What's Now Confirmed Fixed

| Item | Evidence |
|------|----------|
| Scheduler direct calls (no HTTP self-loop) | `scheduler.py` now imports and calls functions directly |
| `/metrics` Prometheus endpoint | `make_asgi_app()` mounted in `main.py` |
| CORS wildcard + credentials conflict | Explicit `ALLOWED_ORIGINS` from env var |
| CI workflow | `.github/workflows/ci.yml` exists |
| Issue templates | `.github/ISSUE_TEMPLATE/` present |
| `CONTRIBUTING.md` | File exists (2311 bytes) |
| `Makefile` | Present |
| `pyproject.toml` | Present |
| Alembic setup | `alembic.ini` + `alembic/` directory |
| Soda Core templates | 5 YAMLs in `checks/templates/soda/` |
| All 4 Grafana dashboard JSONs | Present in `grafana/dashboards/` |

***

## 🔴 What a Real User Will Hit Right Now

### 1. Grafana opens completely blank — highest visibility failure

`grafana/provisioning/dashboards/` and `grafana/provisioning/datasources/` both exist as empty directories. Without provisioning YAMLs, Grafana starts with zero data sources and zero dashboards. A user running `docker-compose up` will open `localhost:3000`, see nothing, and think the project is broken.

**Two files needed immediately:**

`grafana/provisioning/datasources/prometheus.yml`:
```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
```

`grafana/provisioning/dashboards/dashboards.yml`:
```yaml
apiVersion: 1
providers:
  - name: ObservaKit
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
```

***

### 2. Dashboard JSON files are likely stubs — panels will be empty

The 4 dashboard JSON files are between 1.4KB and 3KB. Real Grafana dashboard JSONs with actual panel queries are typically 15–80KB. These are almost certainly skeleton files with no real PromQL queries wired up. A user will see blank grey panels.

**Minimum viable panels each dashboard needs:**

`pipeline_health.json`:
- Stat: DAG success rate → `sum(airflow_dag_run_success_total) / sum(airflow_dag_run_total)`
- Time series: Task duration P95 → `histogram_quantile(0.95, airflow_task_duration_bucket)`
- Table: SLA misses by DAG

`data_freshness.json`:
- Gauge per table → `data_freshness_lag_seconds`
- Status table: table name, lag, status (ok/warn/fail) from Postgres

`volume_anomaly.json`:
- Time series: actual row count vs rolling average

`quality_trends.json`:
- Bar chart: pass/fail per check over time (from Postgres `check_results` table via JSON API)

***

### 3. Alembic has no initial migration — `alembic upgrade head` does nothing

`alembic/` directory exists but there are no version files inside it. Running `make migrate` will output `INFO: No upgrade operations to perform` and leave the database with no tables. Meanwhile `main.py` still calls `Base.metadata.create_all()`, which creates tables but bypasses Alembic's version tracking — so when you add a column in the future, Alembic won't know the baseline.

**Fix — run once and commit the output:**
```bash
alembic revision --autogenerate -m "initial_schema"
# This generates alembic/versions/xxxx_initial_schema.py
# Commit that file to the repo
```
Then in `main.py` lifespan, replace `create_all` with:
```python
from alembic.config import Config
from alembic import command
alembic_cfg = Config("alembic.ini")
command.upgrade(alembic_cfg, "head")
```

***

### 4. `checks/examples/` is empty — first-time user is stuck

The folder structure exists but no example file shows a user how to wire a Soda check to a real table end-to-end. The templates in `checks/templates/soda/` have placeholder table names but no working demo.

**Add one complete example that actually runs against the kit's own Postgres:**

`checks/examples/observakit_self_check.yml`:
```yaml
# Self-check: verifies ObservaKit's own metadata tables are healthy
# Run against: the Postgres metadata store (METADATA_DB_*)
checks for public.freshness_records:
  - row_count >= 0
  - missing_count(table_name) = 0

checks for public.check_results:
  - row_count >= 0
  - missing_count(check_name) = 0

checks for public.pipeline_runs:
  - row_count >= 0
```
This is powerful because it works with zero external warehouse — the user can validate their full setup on day one.

***

### 5. No API key authentication (still open endpoints)

The updated `main.py` has no auth middleware. The `/freshness/poll`, `/schema/snapshot`, `/checks/run` endpoints are still fully open and trigger expensive warehouse queries. Any user deploying this even on a VPS is exposed.

**Quick win — add to `main.py`:**
```python
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def require_api_key(key: str = Security(api_key_header)):
    expected = os.getenv("OBSERVAKIT_API_KEY")
    if not expected or key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
```
Add `dependencies=[Depends(require_api_key)]` to the router includes for all mutating endpoints. Add `OBSERVAKIT_API_KEY=your-secret-here` to `.env.example`.

***

### 6. `config/warehouses/` has no example files

`docker-compose.yml` mounts `./config` into the container but there are no `postgres.example.yml`, `bigquery.example.yml` files in `config/warehouses/`. A new user won't know the expected format for their warehouse connection.

***

### 7. `datetime.utcnow` in `models.py` — likely still unfixed

`models.py` was not in the updated files list. If `default=datetime.utcnow` is still there, Python 3.12+ will emit deprecation warnings on every insert, and this will hard-break on Python 3.13. Worth double-checking and replacing with `default=lambda: datetime.now(timezone.utc)`.

***

## Priority Fix Order (Real User Perspective)

```
Day 1 — unblocks anyone who clones and runs:
  1. Add grafana/provisioning/datasources/prometheus.yml
  2. Add grafana/provisioning/dashboards/dashboards.yml
  3. Add real PromQL panels to dashboard JSONs
  4. Add alembic/versions/initial migration and commit it

Day 2 — unblocks real usage:
  5. Add checks/examples/observakit_self_check.yml
  6. Add API key middleware + document in .env.example
  7. Add config/warehouses/*.example.yml files

Day 3 — production hardening:
  8. Fix datetime.utcnow → timezone-aware in models.py
  9. Replace create_all() in lifespan with alembic upgrade head
```

The single highest-impact fix right now is the **two Grafana provisioning YAMLs** — without them the entire visual layer is invisible and every user's first impression is a broken product.