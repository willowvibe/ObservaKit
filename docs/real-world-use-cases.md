# Real-World Use Cases

How real data teams use ObservaKit to solve production problems.

---

## 1. Cloud Data Migration Audit

**Scenario:** Your team is migrating a legacy PostgreSQL data warehouse to Snowflake. You need to guarantee that every row made it across and that no column types were silently changed during the ETL.

**How ObservaKit helps:**

1. Connect ObservaKit to **both** the source (Postgres) and destination (Snowflake) — run two instances.
2. **Local Audit Snapshots**: Alternatively, use the **DuckDB** connector to pull a local snapshot of your production data for zero-latency schema and volume comparisons during the migration window.
3. Enable **Volume monitoring** on both with the same table list.
4. Enable **Schema Drift** on both.
5. After each migration batch, call `POST /schema/snapshot` and `POST /checks/volume` on both instances and compare the results via `GET /status`.

**What it catches in practice:**
- `TIMESTAMP WITH TIME ZONE` → `TIMESTAMP_NTZ` conversion silently dropping timezone info
- Columns with `NUMERIC(18,4)` precision getting truncated to `FLOAT` in the destination
- Rows filtered out by the ETL because a NULL value didn't fit the destination's `NOT NULL` constraint
- A migration script that processed 50 of 52 tables (silent partial failure)

**Result:** Zero-drift guarantee, automated audit log, and a green light to cut over — without manually comparing row counts in a spreadsheet.

---

## 2. Multi-Team Data Contracts

**Scenario:** The backend engineering team owns the `orders` and `payments` tables. The data analytics team builds revenue dashboards on top of them. When backend makes a breaking change (renames `amount` to `total_amount`, removes a status value), the dashboards break silently.

**How ObservaKit helps:**

1. The backend team creates `config/contracts/orders_v1.yml` and `config/contracts/payments_v1.yml`, defining the expected schema and business rules.
2. The data team enables `contracts.enabled: true` and routes contract violation alerts to `#data-engineering-alerts`.
3. Every pipeline run validates the contract. If a column is removed or a new status value appears that wasn't in `allowed_values`, an alert fires before any dashboard is impacted.
4. The contract file is version-controlled — changes require a PR, forcing a conversation between teams.

**What it catches in practice:**
- Backend renames `status` values without telling analytics (e.g. `'complete'` → `'delivered'`)
- A backend deploy accidentally removes `discount_code` column during a model refactor
- A new payment provider introduces a new `currency` code (`'USDC'`) not in the allowed values list
- An ETL bug that sets `amount = 0` for all rows in a batch (caught by `min: 0.01` rule)

**Result:** Data consumers get advance warning of breaking changes. Backend team has a clear contract to maintain. No more "why is revenue zero?" incidents on Monday morning.

---

## 3. Catching Distribution Drift Before Stakeholders Do

**Scenario:** Your e-commerce platform runs a promo campaign. Halfway through the day, a bug in the discount engine sets `discount_pct = 100` for all new orders. Revenue dashboards show $0. The row count is perfectly normal — 5,000 orders per hour as expected. A volume check won't catch this.

**How ObservaKit helps:**

Enable Distribution Drift on `public.orders.discount_pct` with `type: numeric`. ObservaKit snapshots the histogram every hour. When `discount_pct` suddenly shifts from a mean of 15% to a mean of 100%, the mean_shift detector fires an alert within 60 minutes.

**Other examples of distribution drift in production:**

| Column | Drift type | Root cause |
|--------|-----------|------------|
| `status` | `value_share_shift` | Payment provider outage → all orders stuck in `pending` |
| `country_code` | `value_share_shift` | IP geolocation library updated, misclassifying US traffic as `XX` |
| `age` | `mean_shift` | Frontend form validation bug accepting `0` for age field |
| `email` | `null_pct_change` | Auth migration that didn't copy email addresses for 30% of users |
| `payment_method` | `value_share_shift` | New checkout flow removed Apple Pay option, shifting 20% to `card` |

**Result:** Catch data quality regressions that volume and schema checks miss entirely. Detect silent business logic bugs before they appear in weekly reports.

---

## 4. dbt Project Health Dashboard

**Scenario:** Your team runs dbt with 80 models and 200 tests. Tests fail occasionally but no one has a clear view of which models are consistently flaky, which take longest, or whether quality is improving or degrading over time.

**How ObservaKit helps:**

1. Point ObservaKit at your dbt project directory (`dbt.project_dir` in `kit.yml`).
2. ObservaKit watches for `target/run_results.json` after each `dbt run`.
3. Every model run is stored as a `PipelineRun` record. Every test is stored as a `CheckResult`.
4. Use `GET /checks/trends/{model_name}` to see pass rates and failure streaks per model.
5. The Grafana dashboard shows model success rates, p95 run times, and SLA misses.

**What it shows:**
- `stg_orders` has failed 3 out of the last 5 runs (flaky test, not a real data issue)
- `fct_revenue` takes 45 minutes to run (blocking downstream models)
- Test `unique_order_id` has had a 5-day consecutive failure streak (real data issue)
- Last full `dbt run` succeeded at 06:15 UTC; it's now 09:00 UTC (freshness violation)

**Result:** Unified health view of your entire dbt project. No more hunting through CI logs.

---

## 5. Snowflake Cost Governance for Seed-Stage Startups

**Scenario:** Your Snowflake bill doubled last month and you don't know why. A new analyst is running exploratory queries on a 5TB table without a `LIMIT` clause.

**How ObservaKit helps:**

1. Enable `finops` in `kit.yml`:
   ```yaml
   finops:
     enabled: true
     alert_threshold_credits: 10   # alert if a single day exceeds 10 credits
   ```
2. ObservaKit polls `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` daily and stores credit usage in the metadata DB.
3. A Slack alert fires the moment a configured daily credit threshold is exceeded.
4. Grafana shows credit burn by user, warehouse size, and query tag over time.

**Other FinOps scenarios:**
- BigQuery: alert when a single query scans > 100 GB (with cost estimate)
- Detect unpartitioned table scans that bypass partition pruning
- Track daily cost trend — is this week's burn higher than last week's?

**Result:** Cost surprises caught within hours, not at the end of the billing cycle.

---

## 6. Backfill Detection and Late-Arriving Data

**Scenario:** Your upstream vendor sends a data file every hour. Occasionally they backfill 3 days of historical corrections. Your pipeline ingests this as a massive volume spike — triggering a false-positive volume alert — while the actual data is perfectly valid.

**How ObservaKit helps:**

The Volume monitor's `anomaly_threshold` can be tuned per table. For tables that receive backfills, increase the threshold to absorb expected spikes:

```yaml
volume:
  tables:
    - table: vendor.raw_events
      anomaly_threshold: 2.0   # 200% deviation is fine for backfill tables
```

For tables where backfills should be distinguished from anomalies, use a **Custom SQL check** to detect rows with `event_date < NOW() - INTERVAL '7 days'` appearing in a batch:

```yaml
quality:
  custom_sql:
    - name: "No unexpected backfill data"
      query: |
        SELECT COUNT(*) FROM vendor.raw_events
        WHERE event_date < NOW() - INTERVAL '7 days'
          AND loaded_at >= NOW() - INTERVAL '1 hour'
      assert: "result == 0"
      table: vendor.raw_events
```

---

## 7. Incident Post-Mortem: "The Silent NULL Creep"

**Real pattern seen in production:**

A data engineer updated a Python ETL script. A `None` value that previously raised an exception was silently coerced to `NULL` by the new version. The `email` column null rate went from 0.1% → 3% → 15% over two weeks. Nobody noticed until an email marketing campaign failed to send.

**How ObservaKit catches it:**

Distribution drift on `email` with `null_drift_threshold: 0.02` (2% null shift):

```yaml
distribution:
  tables:
    - table: public.users
      null_drift_threshold: 0.02
      columns:
        - name: email
          type: categorical
```

The alert fires when null % shifts from 0.1% to 2.1% — within the first week of the regression, not two weeks later.

---

## Summary

ObservaKit is most valuable at the intersection of these patterns:

1. **Silently broken pipelines** — freshness + volume catch them
2. **Schema-breaking deployments** — schema drift + contracts catch them
3. **Business logic regressions** — distribution drift + quality checks catch them
4. **Multi-team data ownership** — contracts formalise the interface
5. **Cost surprises** — FinOps tracker catches them before the invoice

The goal is to make every data incident **detectable in minutes**, not days.
