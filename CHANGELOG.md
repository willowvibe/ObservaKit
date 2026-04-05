# Changelog

## [0.1.10] - 2026-04-05
### Added
- **Production Resiliency**:
  - Industrial-grade exponential backoff retries for all warehouse queries via `tenacity`.
  - Centralized alert logging to `AlertLog` database table for auditability.
  - State-aware alert deduplication and suppression fixes.
- **Connectors**:
  - Native support for **DuckDB**, **Databricks**, and **Trino / Presto**.
- **Alerting**:
  - **Microsoft Teams**: Rich Adaptive Card notifications with severity-based layouts.
  - **PagerDuty**: Native integration using the Events API v2 (Routing Key based).
  - **Slack Upgrades**: Professional Block Kit layouts with colour-coded severity strips.
- **CLI Enhancements**:
  - `observakit init`: Interactive setup wizard for quickstart.
  - `observakit validate-config`: Dry-run validation of `kit.yml`.
  - `observakit diff`: Schema drift inspection tool.
  - `observakit test-alert`: Manual alert dispatcher test.
- **API**:
  - `GET /scheduler/jobs`: Endpoint to inspect active internal background jobs.

### Fixed
- Improved Pydantic validation for complex `kit.yml` configurations.
- Fixed Postgres connector resource leak by ensuring connections are consistently closed.
- Resolved race condition in alert dispatcher during high-concurrency polling cycles.


## [0.1.2] - 2026-03-08
### Added
- API key authentication middleware
- FinOps router for Snowflake/BigQuery cost tracking
- Alembic migrations replacing create_all()
- Grafana provisioning YAMLs

## [0.1.0] - 2026-03-01
### Added
- Initial release: Freshness, Volume, Quality, Schema, Pipeline Health
