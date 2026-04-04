# checks/my_project/

Place your **Soda Core** (`.yml`) check files here. ObservaKit will automatically discover and run all `*.yml` files in this directory when quality checks are triggered.

## Quick Start

Create a file like `orders_checks.yml`:

```yaml
# checks/my_project/orders_checks.yml
checks for public.orders:
  - row_count > 0
  - missing_count(order_id) = 0
  - duplicate_count(order_id) = 0
  - freshness(updated_at) < 24h
```

Then trigger a run:
```bash
curl -X POST http://localhost:8000/checks/run \
  -H "X-API-Key: your-api-key"
```

Or do a dry run first:
```bash
curl -X POST "http://localhost:8000/checks/run?dry_run=true" \
  -H "X-API-Key: your-api-key"
```

## Soda CL Reference

Full syntax: https://docs.soda.io/soda-cl/soda-cl-overview.html

Common checks:
| Check | Example |
|---|---|
| Row count | `row_count > 0` |
| Missing values | `missing_count(column) = 0` |
| Duplicates | `duplicate_count(column) = 0` |
| Freshness | `freshness(updated_at) < 24h` |
| Value range | `min(price) >= 0` |
| Invalid format | `invalid_count(email) = 0` |
