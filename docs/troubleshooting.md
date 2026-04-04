# Troubleshooting ObservaKit

Common problems and their solutions. If your issue isn't listed here, open an issue on GitHub.

---

## Service won't start

### `docker compose up -d` exits immediately

**Check the logs:**
```bash
docker compose logs backend
```

Common causes:

| Error message | Fix |
|---------------|-----|
| `could not connect to server: Connection refused` | `METADATA_DB_HOST` is wrong or the DB container isn't ready yet. Wait 10s and retry. |
| `FATAL: password authentication failed` | Wrong `METADATA_DB_PASSWORD` in `.env` |
| `alembic.ini not found` | Run from the repo root, not a subdirectory |
| `Port 8000 already in use` | Change `BACKEND_PORT=8001` in `.env` |

### `make up` works but `http://localhost:8000` returns 502

The backend container is starting slowly. Run `docker compose ps` — if the backend shows `starting`, wait 15 seconds and retry. If it shows `exited`, check `docker compose logs backend`.

---

## Database / connection issues

### `psycopg2.OperationalError: could not connect to server`

The backend is trying to connect to your **data warehouse** (not the metadata DB). Check:

1. `WAREHOUSE_HOST`, `WAREHOUSE_PORT`, `WAREHOUSE_USER`, `WAREHOUSE_PASSWORD`, `WAREHOUSE_DB` in `.env`
2. Network connectivity: can the Docker container reach your warehouse?
3. For cloud warehouses (BigQuery, Snowflake), check that firewall/VPC rules allow the container's IP.

**For BigQuery** — ensure `GOOGLE_APPLICATION_CREDENTIALS` points to a valid service account JSON inside the container:
```yaml
# docker-compose.yml (add to backend service)
volumes:
  - ./my-service-account.json:/app/sa.json
environment:
  GOOGLE_APPLICATION_CREDENTIALS: /app/sa.json
```

**For Snowflake** — the `WAREHOUSE_ACCOUNT` env var must be in `account.region.cloud` format (e.g. `xy12345.us-east-1.aws`).

### `MySQL connector not found`

ObservaKit uses PyMySQL for MySQL. Install it:
```bash
pip install 'observakit[mysql]'
# or inside the container:
docker compose exec backend pip install pymysql
```

### `Redshift: SSL SYSCALL error`

Redshift requires SSL by default on port 5439. Ensure your connector config doesn't disable SSL. The `redshift-connector` library handles this automatically — make sure you're using it:
```bash
pip install 'observakit[redshift]'
```

---

## Freshness checks

### Every table shows `fail` freshness

Your `timestamp_column` values might be stored in local time instead of UTC, causing ObservaKit to compute a large lag. Check:
```sql
SELECT MAX(updated_at), NOW() AT TIME ZONE 'UTC' FROM your_table;
```
If the difference doesn't match the expected lag, your warehouse stores timestamps in a different timezone. Either:
- Convert in the warehouse (`updated_at AT TIME ZONE 'UTC'`)
- Or set `TZ=UTC` in your warehouse session

### `column "updated_at" does not exist`

Your table uses a different name. Common alternatives: `modified_at`, `last_modified`, `_updated_at`, `ts`. Update `timestamp_column` in `kit.yml`.

---

## Volume / anomaly detection

### Volume checks never fire anomalies

ObservaKit requires **at least 3 historical data points** before it will fire a volume anomaly (`MIN_HISTORY_FOR_ANOMALY = 3`). If you've just set it up, wait for 3 scheduled runs, or manually call `POST /checks/volume` three times.

### Volume always shows anomaly even when nothing changed

Your `anomaly_threshold` is too low. The default is `0.3` (±30% deviation). If your table has natural daily variation larger than 30%, increase it:
```yaml
volume:
  tables:
    - table: public.orders
      anomaly_threshold: 0.5   # ±50%
```

---

## Quality checks / Soda Core

### `'soda' CLI not found`

Soda Core is not installed in the backend container. Install it:
```bash
docker compose exec backend pip install soda-core-postgres
# or for other warehouses:
# pip install soda-core-bigquery
# pip install soda-core-snowflake
# pip install soda-core-mysql
```

Or add it to `backend/requirements.txt` and rebuild:
```bash
docker compose build backend && docker compose up -d backend
```

### Soda returns `No JSON output`

Some versions of Soda Core don't support `--json-output` or output to stderr instead of stdout. Try upgrading:
```bash
pip install --upgrade soda-core-postgres
```

If the issue persists, use **custom SQL checks** instead of Soda:
```yaml
quality:
  custom_sql:
    - name: "No null order IDs"
      query: "SELECT COUNT(*) FROM orders WHERE order_id IS NULL"
      assert: "result == 0"
      table: orders
```

---

## Schema drift

### Schema diff fires on every run (false positives)

This usually means the `information_schema` query is returning column types in a non-deterministic format (e.g. `character varying` vs `varchar`). This is a known PostgreSQL behaviour.

**Workaround:** ObservaKit normalises type strings, but if you see persistent false positives, open an issue with your PostgreSQL version and the column types affected.

### Schema diff misses a renamed column

Schema drift detects **added** and **removed** columns. A rename looks like one removal + one addition. This is intentional — ObservaKit cannot infer intent from information_schema alone. If you rename a column, you'll see two drift events: one `removed` and one `added`.

---

## Distribution drift

### `Distribution drift monitoring is disabled`

Set `distribution.enabled: true` in `config/kit.yml`.

### Distribution alert fires constantly

Your `drift_threshold` is too low for the natural variation in your column. Increase it:
```yaml
distribution:
  tables:
    - table: public.orders
      drift_threshold: 0.20   # 20% shift (was 10%)
```

---

## Data Contracts

### `No contract files found in config/contracts/`

Make sure you have at least one `.yml` file in `config/contracts/`. Copy the example:
```bash
cp config/contracts/example_orders.yml config/contracts/my_table.yml
```

### `eval` assertion fails unexpectedly

Assertions are evaluated with `result` as the variable. Make sure your SQL returns a single scalar value:
```yaml
rules:
  - name: "Max lag"
    sql: "SELECT COUNT(*) FROM orders WHERE created_at > NOW()"
    assert: "result == 0"    # ✅ correct
    # assert: "COUNT(*) == 0"  # ❌ wrong — use 'result', not the column name
```

---

## Alerts

### Slack alerts not sending

1. Check `SLACK_WEBHOOK_URL` is set and starts with `https://hooks.slack.com/`
2. Test the webhook directly:
   ```bash
   curl -X POST $SLACK_WEBHOOK_URL -d '{"text":"test from ObservaKit"}'
   ```
3. Check the backend logs: `docker compose logs backend | grep -i slack`

### Discord alerts not sending

1. Check `DISCORD_WEBHOOK_URL` is set.
2. Discord webhooks return HTTP 204 on success (not 200) — ObservaKit handles this correctly in v0.1.7+.
3. Test directly: copy the URL from Discord → Server Settings → Integrations → Webhooks.

### Duplicate alerts firing

ObservaKit has a 60-minute deduplication window per table + alert type. If you're still seeing duplicates, check:
- The `alert_logs` table in your metadata DB.
- Whether you have multiple routing rules matching the same alert.

### Alerts fire during planned maintenance

Use the suppression API to mute alerts:
```bash
curl -X POST http://localhost:8000/suppress \
  -H "X-API-Key: $OBSERVAKIT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"table_name": "public.orders", "suppress_hours": 4, "reason": "Planned migration"}'
# Or use the CLI:
observakit suppress orders 4h
```

---

## Performance

### Health checks are slow (> 5s)

The `GET /status` endpoint queries several tables. For large metadata DBs, add indexes:
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_freshness_checked_at
  ON freshness_records(checked_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_volume_recorded_at
  ON volume_records(recorded_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_check_results_executed_at
  ON check_results(executed_at);
```

### Distribution snapshots time out on large tables

For very large tables, use a sample instead of a full scan. You can work around this with a custom SQL check that queries a `TABLESAMPLE` or a materialized view with pre-computed statistics.

---

## Getting help

- GitHub Issues: https://github.com/willowvibe/ObservaKit/issues
- Check the [FAQ](faq.md) for common questions
- Run `make logs` to see live backend output
