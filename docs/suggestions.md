I've read through the [entire codebase](https://github.com/willowvibe/ObservaKit) — root structure, `backend/`, `connectors/`, `alerts/`, and `tests/`. The foundation is very solid. Here's a surgical breakdown of everything that needs to be fixed or added, from blocking bugs to OSS-polish improvements.

***

## 🔴 Critical Bugs (Fix Before Sharing)

### 1. Scheduler self-calls via HTTP — will silently fail in Docker
`scheduler.py` fires `httpx.post("http://localhost:8000/...")` to trigger its own jobs. Inside Docker Compose, `localhost` inside the container is not the service host — it should be `http://backend:8000`. Worse, the scheduler starts before Airflow is fully up, so early calls will 404.

**Fix:** Call service functions directly instead of HTTP round-trips:
```python
# Instead of:
httpx.post("http://localhost:8000/freshness/poll")

# Do:
from backend.routers.freshness import poll_freshness
from backend.models import SessionLocal
db = SessionLocal()
poll_freshness(db=db)
db.close()
```

***

### 2. CORS misconfiguration — browsers will reject credentialed requests
`main.py` has `allow_origins=["*"]` combined with `allow_credentials=True`. The CORS spec explicitly forbids this combination — browsers will reject all credentialed requests silently.

**Fix:**
```python
allow_origins=["http://localhost:3000", "http://localhost:8000"],  # explicit list
allow_credentials=True,
```
Or if you want wildcard, drop `allow_credentials=True`.

***

### 3. Missing `/metrics` endpoint — Prometheus can't scrape anything
`freshness.py` registers a `prometheus_client.Gauge` but `main.py` never mounts a `/metrics` endpoint. Prometheus has nothing to scrape.

**Fix — add to `main.py`:**
```python
from prometheus_client import make_asgi_app
from starlette.routing import Mount

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

***

### 4. `datetime.utcnow()` — deprecated in Python 3.12+
`models.py` uses `default=datetime.utcnow` across all 7 models. This is deprecated and will raise a warning on Python 3.12 and break on 3.13+.

**Fix — replace all occurrences:**
```python
from datetime import datetime, timezone
# Replace:
default=datetime.utcnow
# With:
default=lambda: datetime.now(timezone.utc)
```

***

## 🟡 Missing Pieces (Required for Real-World Use)

### 5. No GitHub Actions CI workflow
README promises CI but there's no `.github/workflows/` directory. Without this, contributors can't trust the project.

**Add `.github/workflows/ci.yml`:**
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: observakit_test
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r backend/requirements.txt pytest pytest-cov
      - run: pytest tests/ --cov=backend --cov-report=xml
```

***

### 6. No database migrations (Alembic)
`Base.metadata.create_all()` on startup is fine for dev but destroys existing data on schema changes in production. Add Alembic from day one so users trust the project for real deployments.

```bash
pip install alembic
alembic init alembic
# Then generate first migration:
alembic revision --autogenerate -m "initial schema"
```
Replace `create_all()` in `lifespan` with `alembic upgrade head`.

***

### 7. No API authentication
The `/freshness/poll`, `/checks/run`, `/schema/snapshot` endpoints are fully open. Anyone who can reach port 8000 can trigger expensive warehouse queries.

**Add a simple API-key middleware to `main.py`:**
```python
from fastapi import Security, HTTPException
from fastapi.security.api_key import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(key: str = Security(api_key_header)):
    if key != os.getenv("OBSERVAKIT_API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
```
Add `Security(verify_api_key)` to all mutating endpoints. Document the key in `.env.example`.

***

### 8. No `CONTRIBUTING.md` or issue templates
README says "read CONTRIBUTING.md before opening a PR" but the file doesn't exist. This breaks first-time contributors immediately.

**Minimum `CONTRIBUTING.md` should cover:**
- Local dev setup (Python venv + Docker Compose)
- How to run tests (`pytest tests/`)
- Branch naming convention (`feat/`, `fix/`, `docs/`)
- PR checklist (tests passing, linting, docs updated)

**Add `.github/ISSUE_TEMPLATE/`:**
- `bug_report.md`
- `feature_request.md`

***

### 9. No `checks/templates/` YAML files
The README advertises copy-paste Soda Core templates. If a new user clones the repo and the `checks/templates/soda/` folder is empty, they're immediately stuck.

**Minimum templates to ship:**
```
checks/templates/soda/no_nulls_on_pk.yml
checks/templates/soda/no_duplicates.yml
checks/templates/soda/value_range.yml
checks/templates/soda/row_count_min.yml
checks/templates/soda/referential_integrity.yml
checks/examples/ecommerce_orders.yml    ← working real-world example
```

***

### 10. No `config/kit.yml` example with all keys documented
`freshness.py` reads `config/kit.yml` but there's no canonical example showing all supported keys with comments. New users will have no idea what to write.

**Add `config/kit.example.yml`:**
```yaml
# ObservaKit Master Config
warehouse:
  type: postgres           # postgres | bigquery | snowflake

freshness:
  enabled: true
  tables:
    - table: public.orders
      timestamp_column: updated_at
      warn_after: 1h
      fail_after: 2h
      alert: slack

volume:
  enabled: true
  tables:
    - table: public.orders
      dag_id: load_orders
      anomaly_threshold: 0.30

schema:
  enabled: true
  tables:
    - public.orders
    - public.customers

alerts:
  slack:
    webhook_url: "${SLACK_WEBHOOK_URL}"
  email:
    smtp_host: "${SMTP_HOST}"
    from: "observakit@yourcompany.com"
    to: ["data-team@yourcompany.com"]
```

***

## 🟢 Polish Improvements (Makes It OSS-Grade)

### 11. Add `pyproject.toml` for tooling consistency
Replace the bare `requirements.txt` with a `pyproject.toml` that pins tools so contributors use the same linting/formatting:

```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "I"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

***

### 12. Add Grafana dashboard JSON files (they're missing)
`grafana/dashboards/` is referenced everywhere but the actual JSON dashboards are likely empty. A new user running `docker-compose up` will see blank Grafana panels. This is the highest-visibility gap for anyone evaluating the project.

Priority order to create:
1. `pipeline_health.json` — DAG success rate + task duration P95
2. `data_freshness.json` — Lag per table over time
3. `volume_anomaly.json` — Row count + rolling average
4. `quality_trends.json` — Check pass/fail over time

***

### 13. Add alert deduplication using `AlertLog`
`AlertLog` model exists in `models.py` but the alert dispatchers in `alerts/slack.py` and `alerts/email.py` likely don't check it. Without deduplication, a stale table will flood Slack every 15 minutes.

**Logic to add in `_trigger_alert()`:**
```python
# Don't re-alert if same table+type was alerted in last N minutes
recent = db.query(AlertLog).filter(
    AlertLog.table_name == table,
    AlertLog.alert_type == "freshness",
    AlertLog.sent_at >= datetime.now(timezone.utc) - timedelta(minutes=60)
).first()
if recent:
    return  # already alerted, skip
```

***

### 14. Add a `make` or `just` task file for common commands
Contributors and users hate reading long READMEs to find commands. A `Makefile` makes this effortless:

```makefile
up:       docker-compose up -d
down:     docker-compose down
test:     pytest tests/ -v
lint:     ruff check . && ruff format --check .
migrate:  alembic upgrade head
logs:     docker-compose logs -f backend
```

***

## Priority Order to Tackle

| Priority | Fix | Effort |
|----------|-----|--------|
| 🔴 Now | Scheduler direct calls (no HTTP self-calls) | 30 min |
| 🔴 Now | Add `/metrics` Prometheus endpoint | 10 min |
| 🔴 Now | Fix CORS credentials + wildcard conflict | 5 min |
| 🔴 Now | Fix `datetime.utcnow` → timezone-aware | 15 min |
| 🟡 This week | GitHub Actions CI | 1 hr |
| 🟡 This week | `CONTRIBUTING.md` + issue templates | 1 hr |
| 🟡 This week | Soda Core YAML templates + `kit.example.yml` | 2 hr |
| 🟡 This week | Alert deduplication via `AlertLog` | 1 hr |
| 🟡 This week | Alembic migrations | 1 hr |
| 🟡 This week | API key auth middleware | 45 min |
| 🟢 Before launch | Grafana dashboard JSONs | 3–4 hr |
| 🟢 Before launch | `pyproject.toml` + Makefile | 30 min |

The four 🔴 bugs should be fixed before you share the repo link anywhere — they will visibly break real usage. The 🟡 items are what separates a "toy repo" from one that gets GitHub stars and contributors.