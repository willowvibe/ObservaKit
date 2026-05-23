# ObservaKit Test Plan

This is my test plan for the ObservaKit data observability project assignment. I have analyzed the codebase, run the tests, and documented how the core features work.

---

## 1. What is included and what is not

### What is working / in-scope:
* **Core Monitoring Features**: Checking data freshness, tracking row counts (volume checks) with backfill detection, running quality checks (Soda Core & Custom SQL queries), detecting schema drift, validating data contracts, and recording pipeline runs.
* **Alerting**: Managing alert channels (Slack, Teams, PagerDuty, Email, Discord, Webhooks), setting up mute windows (suppressions), and automatic alert deduplication (noise reduction).
* **API endpoints**: Standard endpoints to trigger and query results.
* **Local environment**: Runs on SQLite for local development and PostgreSQL for Docker.

### What is not implemented / out-of-scope:
* **Great Expectations**: The code has a function for Great Expectations quality checks, but it is just a placeholder and returns a fake failure. It is not implemented.
* **Roadmap features**: Future items like the dashboard UI editor, incident timelines, and column lineage are not in the current codebase.

---

## 2. The 7 core flows I checked

### F1: Booting the project and checking API health
* **What I checked**: Setting up the docker containers, running migrations, and hit the health endpoints.
* **Files and folders involved**:
  * `docker-compose.yml`
  * `backend/main.py` (FastAPI app setup)
  * `backend/models.py` (Database tables definition)
  * `backend/scheduler.py` (Runs background checks)
  * `alembic/` (Database migrations folder)
* **Endpoints**:
  * `GET /healthz` (Check if DB connection is active)
  * `GET /status` (Summary of table health in last 24 hours)
* **Inputs needed**:
  * Env variables like `OBSERVAKIT_API_KEY` and DB credentials.
* **Expected result**:
  * Running `docker compose up` starts everything and automatically runs database migrations.
  * `/healthz` returns `{"status": "ok"}` when the database is connected.
* **Status**: `✅ appears to work`

---

### F2: Running a data freshness check
* **What I checked**: How the system monitors if tables are receiving fresh data based on SLA rules.
* **Files and folders involved**:
  * `backend/routers/freshness.py`
  * `connectors/base.py` (Used to query target databases)
  * `config/kit.yml` (Where we configure freshness SLAs)
* **Endpoints**:
  * `POST /freshness/poll` (Runs the freshness checks)
* **Inputs needed**:
  * Configuration in `config/kit.yml` indicating the table name, `timestamp_column`, and SLA thresholds (`warn_after`, `fail_after`).
* **Expected result**:
  * The code queries the target database for the newest timestamp in the column.
  * It calculates lag (`now - max_timestamp`) and records a `FreshnessRecord` in the DB.
  * If the lag is too high, it sends an alert to the configured channel.
* **Status**: `✅ appears to work`

---

### F3: Running data quality checks
* **What I checked**: Checking data quality rules using Soda Core, custom SQL queries, consistency comparisons, and row count anomalies.
* **Files and folders involved**:
  * `backend/routers/checks.py`
  * `checks/` (Where Soda Core YAML files are kept)
  * `backend/models.py` (`CheckResult`, `VolumeRecord`, `BackfillEvent` tables)
* **Endpoints**:
  * `POST /checks/run` (Runs quality checks)
  * `POST /checks/volume` (Runs volume checks)
* **Inputs needed**:
  * Soda Core YAML configurations, custom SQL queries in `kit.yml`, and historical row counts to detect volume anomalies.
* **Expected result**:
  * **Soda Core**: The code starts a subprocess to run `soda scan`, reads the JSON output, and logs the results.
  * **Custom SQL**: Executes SQL and checks if assertions pass (e.g. `result == 0`).
  * **Volume checks**: Compares row count to 7-day average. If there's a big change, it checks if it's a "backfill" (historical data imports) to avoid false alert alarms.
* **Status**:
  * **Soda Core Scan**: `⚠️ unclear` (Requires Soda CLI to be installed on the machine; if missing, the scan fails).
  * **Great Expectations**: `❌ broken/missing` (Not implemented in code; returns a dummy failure).
  * **Custom SQL, Consistency & Volume**: `✅ appears to work`

---

### F4: Detecting schema drift
* **What I checked**: Finding out if someone modified columns in the warehouse tables.
* **Files and folders involved**:
  * `backend/routers/schema_diff.py`
  * `connectors/base.py` (To fetch table metadata)
  * `backend/models.py` (`SchemaSnapshot` and `SchemaDiff` tables)
* **Endpoints**:
  * `POST /schema/snapshot` (Runs comparison)
* **Inputs needed**:
  * List of tables to watch in `config/kit.yml` under `schema_drift:`.
* **Expected result**:
  * Saves the current list of columns and types as a `SchemaSnapshot`.
  * Compares it to the previous snapshot. If columns are added, removed, or type is changed, it logs the change into `SchemaDiff` and alerts the user.
* **Status**: `✅ appears to work`

---

### F5: Data contract validation
* **What I checked**: Validating tables against a YAML schema contract defined by developers.
* **Files and folders involved**:
  * `backend/routers/contracts.py`
  * `config/contracts/` (YAML files detailing the contracts)
* **Endpoints**:
  * `POST /contracts/validate` (Validates contract files)
* **Inputs needed**:
  * Contract YAML definitions stating column types, null limits, allowed values, min rows, and custom rules.
* **Expected result**:
  * Queries database to verify if all columns exist and have the correct types.
  * Performs counts on nulls, duplicate values, value ranges, and custom business rules.
  * Logs the validation results. If any check fails, triggers a contract violation alert.
* **Status**: `✅ appears to work`

---

### F6: Alert suppression and noise reduction
* **What I checked**: How the system avoids sending too many alerts during maintenance or when a check fails repeatedly.
* **Files and folders involved**:
  * `backend/routers/suppressions.py` (Mute endpoints)
  * `backend/routers/alert_noise.py` (Noise tracking endpoints)
  * `alerts/base.py` (Dispatches alerts and checks deduplication)
* **Endpoints**:
  * `POST /suppress/` (To mute a table's alerts)
  * `GET /alerts/noise/summary` (See noisy alerts)
* **Inputs needed**:
  * Suppression details (table name, mute time, reason) and historical alert counts.
* **Expected result**:
  * Before sending an alert, the system checks if the table is muted or if a similar alert was sent recently (using an adaptive time window based on a calculated noise score).
  * If yes, the alert is skipped. If sent, it increments the noise counters.
* **Status**: `✅ appears to work`

---

### F7: Pipeline webhook integration
* **What I checked**: Receiving callback requests from Airflow or Prefect to log pipeline runs.
* **Files and folders involved**:
  * `backend/routers/webhooks.py`
  * `backend/models.py` (`PipelineRun` table)
* **Endpoints**:
  * `POST /webhooks/airflow`
  * `POST /webhooks/prefect`
* **Inputs needed**:
  * JSON payloads from Airflow or Prefect with DAG details and states.
* **Expected result**:
  * Parses the payload, normalizes status values, and inserts a `PipelineRun` record.
* **Status**: `⚠️ unclear` 

---

## 3. Major gaps and things that might break

* **Great Expectations is missing**: If someone configures `engine: great_expectations` in the config, it will fail because the runner is not coded.
* **SQLite vs PostgreSQL locking**: In PostgreSQL, the scheduler locks tasks so multiple servers don't run them at the same time. On SQLite, it doesn't do anything, which might cause double runs during testing.
* **No alert retry logic**: If Slack or Teams is down, the alert fails. It records it in `AlertLog`, but it won't try to send it again later.
* **Soda Core CLI dependency**: The quality check depends on having the `soda` command line tool installed on the server. If it isn't, the tests fail.

---

## 4. Things I couldn't test or verify

* **Database performance**: I couldn't test how fast the schema diff fetches column data if the database has thousands of tables.
* **Third-party API rate limits**: I am not sure if Slack or Teams will block us if we send hundreds of alerts before the noise throttling turns on.

---

## 5. Future Testing Considerations / Improvements

* **Edge Case Coverage**: Expand test scenarios to cover failure modes and edge cases, such as:
  * Database connection failures (bad DB connection).
  * Malformed or invalid configurations (bad config).
  * Schema type mismatches and wrong data types.
  * Other potential system failure modes.
