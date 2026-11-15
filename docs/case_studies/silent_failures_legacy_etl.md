# Silent failures in a legacy ETL migration

> **Illustrative scenario, not a client engagement.** The company, numbers, and timeline are invented to show how ObservaKit's checks work. No client, employer, or named organization is depicted.

## The situation

A mid-sized retailer is moving a legacy nightly ETL job to a modern warehouse. The migration has three risks that ordinary pipeline success alerts do not catch:

1. **Volume parity.** The new pipeline can succeed while loading fewer rows than the source.
2. **Schema drift.** A renamed or retyped column can pass the job and break downstream reporting.
3. **Freshness.** A partially failed load can leave the newest partition hours behind.

## What ObservaKit would surface

- **Volume:** compare today's row count with the 7-day rolling average. A load that drops 40% fails the volume check instead of waiting for a finance report to notice.
- **Schema:** snapshot `information_schema` before and after the cutover. An added, removed, or retyped column is recorded as a schema diff.
- **Freshness:** poll `max(updated_at)`. A table whose newest row is older than the SLA is marked `warn` or `fail` with the exact lag.
- **Quality:** run a custom SQL assertion such as "no orphaned order items" against both source and destination.

## The migration checklist

```text
1. Point ObservaKit at the source and destination warehouses.
2. Snapshot both schemas; resolve every diff before cutover.
3. Run volume checks against both for one full week.
4. Run the same custom SQL quality checks on both.
5. Cut over; keep the source checks running for one week as a backstop.
```

## What this demonstrates

The value is not a dashboard. It is a repeatable check that fails loudly when a migration is incomplete, with the table, the check, and the time window attached. The same pattern applies to any source-to-warehouse migration.
