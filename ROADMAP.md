# ObservaKit Roadmap

## Shipped (v0.1.x)

- [x] Freshness Monitor (configurable SLA thresholds, Prometheus metrics)
- [x] Volume Anomaly Detection (Z-score, rolling average, min-history guard)
- [x] Quality Checks (Soda Core, Great Expectations, custom SQL)
- [x] Schema Drift Detector (column add/remove/type-change)
- [x] Pipeline Health (Airflow + Prefect REST API)
- [x] FinOps Tracker (Snowflake credits, BigQuery bytes)
- [x] Native dbt Integration (run_results.json + manifest.json, no package needed)
- [x] Column Profiling (null %, distinct count, min/max/mean)
- [x] Cross-Table Consistency Checks (row_count_match, sum_match)
- [x] Lineage-aware Alerts (downstream impact in alert message)
- [x] Alert Deduplication (60-minute window per table+type)
- [x] Alert Suppression (planned maintenance windows)
- [x] Slack + Email alerts with routing rules
- [x] Embedded React Dashboard (`/ui`)
- [x] CLI (`observakit status`, `check`, `profile`, `suppress`)
- [x] PostgreSQL, BigQuery, Snowflake connectors
- [x] Docker Compose (full stack + lite mode)
- [x] **Distribution Drift Monitor** (categorical value-share shifts, numeric mean shifts, null % drift)
- [x] **Data Contracts** (YAML-defined schema + business rule enforcement, violation alerts)
- [x] **MySQL / MariaDB connector**
- [x] **Amazon Redshift connector** (with SVV_COLUMNS + IAM auth support)
- [x] **Discord alert channel** (rich embeds)
- [x] **Generic outgoing Webhook alerts** (HMAC-signed, works with PagerDuty, Opsgenie, n8n)
- [x] **`/healthz` endpoint** (Kubernetes liveness/readiness probe)
- [x] **DuckDB / Databricks / Trino connectors**
- [x] **PagerDuty native integration** (Events API v2)
- [x] **Microsoft Teams alert channel** (Adaptive Cards)
- [x] **`observakit init`** interactive setup wizard
- [x] **`observakit validate-config`** & **`observakit diff`** CLI tools
- [x] **Automatic Query Retries** (tenacity-based resiliency for all warehouses)
- [x] **Centralized Alert Auditing** (`AlertLog` table)
- [x] **Slack Block Kit** support (richer notifications with severity colour-strips)

---

## v0.2.0 — Storage & Advanced Monitoring

- [ ] Delta Lake support (via delta-rs)
- [ ] Backfill detection (distinguish backfill spikes from true anomalies)
- [ ] Late-arriving data detector (tracks expected vs actual data arrival times)
- [ ] Scheduled metadata purge (auto-delete records older than N days)

## v0.3.0 — Incident Management & Analytics

- [ ] Opsgenie integration
- [ ] Incident timeline — link related alerts into a single incident
- [ ] Alert recovery notifications (auto-send "resolved" when checks pass again)
- [ ] Weekly digest email / Slack summary (scheduled health report)
- [ ] On-call rotation support (route alerts based on time-of-day)

## v0.4.0 — UI & Developer Experience

- [ ] Enhanced React dashboard with per-table drill-down pages
- [ ] Contract management UI (create/edit contracts without editing YAML)
- [ ] Distribution trend charts (visualise value shares over time)
- [ ] Check history timeline (visualise pass/fail streaks)
- [ ] Dark mode
- [ ] Python SDK (`pip install observakit`) for programmatic access
- [ ] Pre-commit hook — run quality checks in CI before merging

## v0.5.0 — Advanced Quality

- [ ] Column-level lineage (track which columns feed which downstream columns)
- [ ] Data catalog integration (Amundsen, DataHub, Atlan metadata linking)
- [ ] Partition freshness monitoring (BigQuery/Snowflake partition-level SLAs)
- [ ] Regex / format validation checks (emails, phone numbers, UUIDs)
- [ ] Cross-column consistency (e.g. `end_date >= start_date`)
- [ ] Row-level sampling for failed checks (show actual failing rows in alert)
- [ ] Materialized view staleness tracking

## Future / Considering

- [ ] dbt Cloud API integration (replace local artifact parsing for cloud-hosted dbt)
- [ ] Kafka / streaming source freshness monitoring
- [ ] Multi-warehouse support (monitor multiple warehouses in one instance)
- [ ] RBAC (read-only vs admin roles)
- [ ] Multi-tenancy (multiple projects in one instance with isolation)
- [ ] Cloud-hosted SaaS version — maintained by WillowVibe (for teams that want zero ops)
- [ ] Anomaly explanation (LLM-powered root cause suggestions)

---

## How to influence the roadmap

Open a GitHub issue with the label `roadmap` or vote on existing issues with a 👍. Features with the most votes move up the priority list.

**Contributions welcome** — if you implement any of the above, we'd love a PR!
