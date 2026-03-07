# dbt Integration with Elementary

ObservaKit integrates with [Elementary](https://github.com/elementary-data/elementary) for dbt-native data observability.

## What is Elementary?

Elementary's `dbt-data-reliability` package runs as dbt tests and detects:
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
