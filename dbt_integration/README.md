# dbt Integration

ObservaKit offers two paths for monitoring your dbt pipelines:
1. **Native Artifact Parsing (Lightweight)**
2. **Elementary Integration (Comprehensive)**

---

## 1. Native Artifact Parsing (Lightweight)

If you don't want to install additional dbt packages into your warehouse, you can use ObservaKit's native script to parse standard dbt JSON artifacts and ingest them directly into ObservaKit's metadata database.

### Setup & Usage

After you run your dbt models or tests, dbt generates `run_results.json` and `manifest.json` in the `target/` directory.

Run the parser script, pointing it to those files:

```bash
python dbt_integration/parse_artifacts.py \
  --run-results path/to/your/dbt/target/run_results.json \
  --manifest path/to/your/dbt/target/manifest.json
```

**What this does:**
- Maps dbt model/seed executions to ObservaKit `PipelineRun` records.
- Maps dbt test results to ObservaKit `CheckResult` records.
- Instantly surfaces dbt failures in your Grafana "Pipeline Health" and "Data Quality" dashboards.

---

## 2. Elementary Integration (Comprehensive)
- **Anomalies** in row counts, freshness, and column-level metrics
- **Schema drift** (column added/removed/type changed)
- **Freshness** issues using dbt source freshness

## Setup

### 1. Install the Elementary dbt Package

Add to your `packages.yml`:

```yaml
packages:
  - package: elementary-data/elementary
    version: ">=0.15.0"
```

Then run:

```bash
dbt deps
```

### 2. Add Elementary Models

Add to your `dbt_project.yml`:

```yaml
models:
  elementary:
    +schema: "elementary"
```

Then run:

```bash
dbt run --select elementary
```

This creates the Elementary schema and tables in your warehouse.

### 3. Add Elementary Tests to Your Models

In your dbt model YAML files:

```yaml
# models/staging/schema.yml
version: 2

models:
  - name: stg_orders
    columns:
      - name: order_id
        tests:
          - not_null
          - unique
          - elementary.column_anomalies:
              timestamp_column: updated_at
      - name: amount
        tests:
          - elementary.column_anomalies:
              timestamp_column: updated_at
    tests:
      - elementary.volume_anomalies:
          timestamp_column: updated_at
      - elementary.freshness_anomalies:
          timestamp_column: updated_at
          warn_after: {count: 1, period: hour}
          error_after: {count: 2, period: hour}
      - elementary.schema_changes
```

### 4. Run Tests

```bash
dbt test
```

Elementary automatically stores results in your warehouse. ObservaKit's backend can then query these results for dashboards and alerts.

### 5. Generate Elementary Report (Optional)

```bash
pip install elementary-data[postgres]  # or [bigquery], [snowflake]
edr report
```

## Integration with ObservaKit

Elementary stores its results in `elementary.dbt_run_results` and `elementary.alerts` tables. ObservaKit can query these tables through your warehouse connector for a unified observability view including dbt-layer checks alongside direct warehouse checks.

## Resources

- [Elementary Documentation](https://docs.elementary-data.com/)
- [Elementary GitHub](https://github.com/elementary-data/elementary)
- [dbt Package Hub](https://hub.getdbt.com/elementary-data/elementary/)
