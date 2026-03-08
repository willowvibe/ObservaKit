# dbt Integration

ObservaKit offers a native path for monitoring your dbt pipelines without requiring third-party packages in your warehouse: **Native Artifact Parsing (Lightweight)**.

---

## Native Artifact Parsing (Lightweight)

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

