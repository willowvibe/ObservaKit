# Data Contracts in ObservaKit

Data contracts are one of the most impactful patterns in modern data engineering. This guide explains what they are, why they matter, and how to use them in ObservaKit.

---

## What is a Data Contract?

A **data contract** is a versioned, machine-enforceable agreement between:
- The **producer** — the team or service that writes data to a table (e.g. backend engineering, a vendor, an ETL pipeline)
- The **consumer** — the team or system that reads that data (e.g. analytics, ML, reporting)

The contract defines:
- Which columns must exist and their types
- Which columns must never be null
- Allowed values for categorical columns
- Business rules (expressed as SQL assertions)
- Volume expectations (minimum row counts)
- Freshness SLAs

When the producer changes the data in a way that violates the contract, ObservaKit fires an alert **before consumers are impacted**.

---

## Why does this matter?

Without contracts, breaking changes happen like this:

1. Backend engineer renames `amount` to `total_amount` in a PR — looks fine to them.
2. dbt model `select amount from orders` breaks silently overnight.
3. Revenue dashboard shows $0 at 9am.
4. Data team spends 2 hours finding the root cause.

With contracts:

1. Same PR is merged.
2. ObservaKit validates the `orders_v1` contract at the next pipeline run.
3. Alert fires within 60 minutes: `Contract violation: column 'amount' is missing from public.orders`.
4. Backend team is notified before the dashboard is opened.

---

## Contract File Format

Each contract is a YAML file in `config/contracts/`. The full schema:

```yaml
contract:
  id: orders_v1              # Unique identifier — used in API calls
  version: "1.2.0"           # Semantic version — increment on breaking changes
  table: public.orders       # schema.table format
  owner: "data-eng@company.com"
  description: |
    Core orders table produced by the backend API ingestion pipeline.
    Consumed by: analytics dashboards, revenue reporting, ML churn model.

  # ---- Column rules ----
  columns:
    - name: id
      type: integer
      nullable: false
      unique: true

    - name: status
      type: varchar
      nullable: false
      allowed_values:
        - pending
        - confirmed
        - shipped
        - delivered
        - cancelled

    - name: amount
      type: numeric
      nullable: false
      min: 0          # value must be >= 0
      # max: 100000   # optional upper bound

    - name: created_at
      type: timestamp
      nullable: false

  # ---- Volume expectation ----
  volume:
    min_rows: 1000

  # ---- Custom SQL business rules ----
  rules:
    - name: "No future-dated orders"
      sql: "SELECT COUNT(*) FROM public.orders WHERE created_at > NOW()"
      assert: "result == 0"
      severity: critical      # critical | warning (for documentation only currently)

    - name: "Revenue non-negative"
      sql: "SELECT COALESCE(MIN(amount), 0) FROM public.orders WHERE status != 'refunded'"
      assert: "result >= 0"
      severity: critical

    - name: "Delivered orders have a timestamp"
      sql: |
        SELECT COUNT(*) FROM public.orders
        WHERE status = 'delivered' AND updated_at IS NULL
      assert: "result == 0"
      severity: warning
```

---

## Setting Up Contracts

### 1. Create a contract file

```bash
cp config/contracts/example_orders.yml config/contracts/orders_v1.yml
# Edit to match your table
```

### 2. Enable contracts in kit.yml

```yaml
contracts:
  enabled: true
  schedule_minutes: 60      # validate every hour
  contracts_dir: config/contracts/
```

### 3. Route alerts

```yaml
alerts:
  routing:
    - match:
        alert_type: "contract"
      channel: slack
      slack_channel: "#data-contracts"
```

### 4. Validate manually

```bash
# Via CLI (Dry-run validation of contract YAMLs)
observakit validate-config

# Via API (Trigger real-time validation against the warehouse)
curl -X POST http://localhost:8000/contracts/validate \
  -H "X-API-Key: $OBSERVAKIT_API_KEY"

# Validate a specific contract by ID
curl -X POST "http://localhost:8000/contracts/validate?contract_id=orders_v1" \
  -H "X-API-Key: $OBSERVAKIT_API_KEY"
```

### 5. View results

```bash
curl http://localhost:8000/contracts/results \
  -H "X-API-Key: $OBSERVAKIT_API_KEY"
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/contracts/validate` | Validate all contracts (or one by ID) |
| `GET` | `/contracts/results` | Query historical validation results |
| `GET` | `/contracts/results?contract_id=orders_v1` | Filter by contract ID |
| `GET` | `/contracts/results?table_name=public.orders` | Filter by table |

---

## Rules Reference

### Column rules

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Column name (required) |
| `type` | string | Expected data type (prefix match — `integer` matches `integer4`) |
| `nullable` | bool | If `false`, checks for NULLs in the column |
| `unique` | bool | If `true`, checks for duplicate values |
| `allowed_values` | list | Checks that no values outside this list exist |
| `min` | number | Minimum allowed value |
| `max` | number | Maximum allowed value |

### Volume rules

| Field | Type | Description |
|-------|------|-------------|
| `min_rows` | int | Minimum row count. Fails if table has fewer rows. |

### Custom SQL rules

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable rule name |
| `sql` | string | SQL query that returns a **single scalar value** |
| `assert` | string | Python expression evaluated with `result` = the query return value |
| `severity` | string | `critical` or `warning` (for documentation; alerts fire regardless) |

---

## Best Practices

**Version your contracts.** Use semantic versioning. Increment the minor version for backward-compatible additions (new optional columns). Increment the major version for breaking changes (removed columns, narrowed allowed values).

**Keep contracts close to the code.** Store contract files in the same repository as the service that produces the data, or in a dedicated `data-contracts` repo. Review them in PRs just like code.

**Start small.** Don't try to define every constraint on day one. Start with: not-null PKs, not-null FKs, allowed values for status columns, and one or two business rules. Add more over time.

**Don't duplicate Soda/GX checks.** Data contracts are for producer-consumer agreements. Soda/GX quality checks are for detailed row-level validation. Use contracts for the interface-level guarantees and Soda/GX for the implementation details.

**Alert the producer, not just the consumer.** Route contract violation alerts to the team that owns the producing pipeline (`#backend-alerts`), not just the data team. The goal is to fix the source, not just observe the symptom.

---

## Example: Migrating from Spreadsheet Agreements

Many small teams maintain "data dictionaries" as spreadsheets or Confluence pages. These go stale immediately. Here's how to migrate to machine-enforced contracts:

1. For each critical table, copy `example_orders.yml` and fill in what you know.
2. Start with `nullable: false` for PKs and FKs only.
3. Add `allowed_values` for your most important categorical columns.
4. Add one or two SQL rules for your most critical business invariants.
5. Run validation in `warn` mode first — just observe violations without alerting.
6. Once false positives are tuned out, enable alerting.

This incremental approach gets you from zero to enforced contracts in a week without disruption.
