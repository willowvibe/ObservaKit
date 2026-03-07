# Adding Custom Quality Checks

ObservaKit ships with pre-built quality check templates for both **Soda Core** and **Great Expectations**. This guide shows you how to add your own checks.

## Quick Start

1. Copy a template from `checks/templates/soda/` to `checks/my_project/`
2. Edit the YAML to point to your table and columns
3. Checks will run automatically on the configured schedule

## Soda Core Checks

### Available Templates

| Template | What It Checks |
|----------|---------------|
| `no_nulls_on_pk.yml` | Primary key column has no NULL values |
| `no_duplicates.yml` | Column has no duplicate values |
| `value_range.yml` | Numeric values within expected range |
| `referential_integrity.yml` | Foreign key references exist |
| `row_count_min.yml` | Table is not empty |

### Writing a Custom Check

Create a `.yml` file in `checks/my_project/`:

```yaml
# checks/my_project/orders.yml
checks for public.orders:
  - row_count > 0
  - missing_count(order_id) = 0
  - duplicate_count(order_id) = 0
  - min(amount) >= 0
  - max(amount) < 1000000
  - missing_count(customer_id) = 0
```

### Soda Check Types

```yaml
# Row count checks
- row_count > 100
- row_count between 1000 and 50000

# Null checks
- missing_count(column_name) = 0
- missing_percent(column_name) < 5

# Duplicate checks
- duplicate_count(column_name) = 0
- duplicate_percent(column_name) < 1

# Value range checks
- min(amount) >= 0
- max(amount) < 1000000
- avg(amount) between 10 and 500

# Freshness checks (Soda native)
- freshness(updated_at) < 2h

# Schema checks
- schema:
    fail:
      when required column missing: [id, name, email]
```

## Great Expectations Checks

### Template Format

```yaml
# checks/templates/great_expectations/no_nulls_on_pk.yml
expectations:
  - expectation_type: expect_column_values_to_not_be_null
    kwargs:
      column: YOUR_PK_COLUMN
    meta:
      notes: "Primary key must never be null"
```

### Common Expectations

```yaml
expectations:
  # Not null
  - expectation_type: expect_column_values_to_not_be_null
    kwargs:
      column: order_id

  # Unique
  - expectation_type: expect_column_values_to_be_unique
    kwargs:
      column: order_id

  # Value range
  - expectation_type: expect_column_values_to_be_between
    kwargs:
      column: amount
      min_value: 0
      max_value: 1000000

  # Not empty
  - expectation_type: expect_table_row_count_to_be_between
    kwargs:
      min_value: 1
```

## Configuration

Control the quality check engine and schedule in `config/kit.yml`:

```yaml
quality:
  enabled: true
  schedule_minutes: 60           # Run every hour
  engine: soda                   # soda | great_expectations
  checks_dir: checks/my_project/
```

## Viewing Results

- **API**: `GET http://localhost:8000/checks/results`
- **Grafana**: Open the **Quality Trends** dashboard at `http://localhost:3000`
- **Filter by table**: `GET http://localhost:8000/checks/results?table_name=public.orders`
- **Filter by status**: `GET http://localhost:8000/checks/results?passed=false`
