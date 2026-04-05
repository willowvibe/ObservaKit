"""
ObservaKit CLI — observakit

Usage:
    observakit check checks/my_project/orders.yml
    observakit status
    observakit status --output json
    observakit profile public.orders
    observakit suppress public.orders --minutes 60 --reason "Planned ETL reload"
    observakit validate-config
    observakit validate-config --config config/kit.staging.yml
    observakit diff --table public.orders
    observakit test-alert
    observakit init

Install: pip install -e .
Then use: observakit --help
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _api_url() -> str:
    return os.getenv("OBSERVAKIT_API_URL", "http://localhost:8000")


def _api_key() -> str:
    return os.getenv("OBSERVAKIT_API_KEY", "")


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    key = _api_key()
    if key:
        h["X-API-Key"] = key
    return h


def _get(path: str) -> dict:
    try:
        import httpx
    except ImportError:
        print("httpx is required for the CLI. Install with: pip install httpx")
        sys.exit(2)
    url = f"{_api_url()}{path}"
    resp = httpx.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, body: dict | None = None) -> dict:
    try:
        import httpx
    except ImportError:
        print("httpx is required for the CLI. Install with: pip install httpx")
        sys.exit(2)
    url = f"{_api_url()}{path}"
    resp = httpx.post(url, headers=_headers(), json=body or {}, timeout=120)
    resp.raise_for_status()
    return resp.json()


def _status_icon(s: str) -> str:
    return {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}.get(s, "❓")


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


def cmd_status(args) -> int:
    """Print a health summary of all monitored tables."""
    output_json = getattr(args, "output", None) == "json"
    try:
        data = _get("/status")
    except Exception as e:
        if output_json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"❌ Could not reach ObservaKit at {_api_url()}: {e}")
        return 1

    if output_json:
        print(json.dumps(data, indent=2))
        tables = data.get("tables", [])
        any_fail = any(
            t.get(p) == "fail" for t in tables for p in ("freshness", "volume", "quality", "schema")
        )
        return 1 if any_fail else 0

    summary = data.get("summary", {})
    tables = data.get("tables", [])

    print(f"\n🔭 ObservaKit Status  (window: {data.get('window_hours', 24)}h)")
    print(
        f"   Healthy: {summary.get('healthy', 0)}  Warn: {summary.get('warn', 0)}  Fail: {summary.get('fail', 0)}\n"
    )

    if not tables:
        print("   No monitored tables found in the last 24 hours.")
        return 0

    col_w = max((len(t["name"]) for t in tables), default=20)
    fmt = f"  {{:<{col_w}}}  {{:<8}} {{:<8}} {{:<8}} {{:<8}}"
    print(fmt.format("TABLE", "FRESH", "VOLUME", "QUALITY", "SCHEMA"))
    print("  " + "-" * (col_w + 36))

    any_fail = False
    for t in tables:
        icons = [_status_icon(t.get(p, "ok")) for p in ("freshness", "volume", "quality", "schema")]
        print(fmt.format(t["name"], *icons))
        if any(t.get(p) == "fail" for p in ("freshness", "volume", "quality", "schema")):
            any_fail = True

    print()
    return 1 if any_fail else 0


def cmd_check(args) -> int:
    """Run quality checks (and optionally a specific file via dry_run preview)."""
    output_json = getattr(args, "output", None) == "json"
    dry = getattr(args, "dry_run", False)
    path = f"/checks/run?dry_run={str(dry).lower()}"
    if not output_json:
        print(f"{'🔍 Dry run:' if dry else '🚀 Running'} quality checks via {_api_url()}{path}")
    try:
        data = _post(path)
    except Exception as e:
        if output_json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"❌ Check run failed: {e}")
        return 1

    if output_json:
        print(json.dumps(data, indent=2))
        failed = [r for r in data.get("results", []) if not r.get("passed", True)]
        return 1 if failed else 0

    results = data.get("results", [])
    checks_run = data.get("checks_run", 0)
    failed = [r for r in results if not r.get("passed", True)]

    print(f"\n   Engine: {data.get('engine', 'unknown')}  |  Checks run: {checks_run}")
    for r in results:
        icon = "✅" if r.get("passed") else "❌"
        print(f"   {icon}  {r.get('check_name', 'unnamed')}  [{r.get('table_name', '')}]")
        if not r.get("passed") and r.get("details"):
            print(f"       {r['details']}")

    print()
    if failed:
        print(f"❌ {len(failed)} check(s) failed.\n")
        return 1
    print("✅ All checks passed.\n")
    return 0


def cmd_profile(args) -> int:
    """Run column profiling for a table and print a summary."""
    table = args.table
    print(f"📊 Profiling {table} …")
    try:
        data = _post(f"/profiling/run?table_name={table}")
    except Exception as e:
        print(f"❌ Profiling failed: {e}")
        return 1

    profiles = data.get("profiles", [])
    if not profiles:
        print("   No columns profiled (table may not exist or be empty).")
        return 0

    print(f"\n   Table: {table}  |  Columns profiled: {data.get('columns_profiled', 0)}\n")
    print(f"   {'COLUMN':<30} {'NULL%':>7} {'DISTINCT':>10}")
    print("   " + "-" * 52)
    for p in profiles:
        print(f"   {p['column']:<30} {p['null_pct']:>6.1f}% {p['distinct_count']:>10,}")
    print()
    return 0


def cmd_suppress(args) -> int:
    """Suppress alerts for a table for N minutes."""
    body = {
        "table_name": args.table,
        "duration_minutes": args.minutes,
        "reason": args.reason,
    }
    try:
        data = _post("/suppress/", body)
    except Exception as e:
        print(f"❌ Suppression failed: {e}")
        return 1
    print(f"✅ Alerts suppressed for '{data['table_name']}' until {data['suppressed_until']}")
    if data.get("reason"):
        print(f"   Reason: {data['reason']}")
    return 0


def cmd_test_alert(args) -> int:
    """Trigger a generic test alert to configured channels."""
    print(f"🔔 Triggering test alert via {_api_url()}/webhooks/test-alert ...")
    try:
        data = _post("/webhooks/test-alert")
    except Exception as e:
        print(f"❌ Failed to reach backend: {e}")
        return 1

    if data.get("status") == "success":
        print(f"✅ {data.get('message', 'Alert sent!')}")
        return 0
    else:
        print(f"❌ {data.get('message', 'Failed to send alert.')}")
        return 1


def cmd_validate_config(args) -> int:
    """Dry-run parse kit.yml and contracts without connecting to a warehouse."""
    config_path = getattr(args, "config", None) or os.getenv("OBSERVAKIT_CONFIG", "config/kit.yml")
    print(f"🔍 Validating config: {config_path}")

    # 1. Load and parse kit.yml
    try:
        from config.loader import load_config

        config = load_config(config_path)
    except FileNotFoundError:
        print(f"❌ Config file not found: {config_path}")
        return 2
    except Exception as e:
        print(f"❌ Failed to parse config: {e}")
        return 2

    errors = []
    warnings = []

    # 2. Required top-level sections
    for section in ("warehouse", "freshness"):
        if section not in config:
            warnings.append(f"Missing section '{section}' — some features will be disabled")

    # 3. Validate freshness tables
    freshness_cfg = config.get("freshness", {})
    for i, tbl in enumerate(freshness_cfg.get("tables", [])):
        if not tbl.get("table"):
            errors.append(f"freshness.tables[{i}]: missing required field 'table'")
        if not tbl.get("timestamp_column"):
            errors.append(f"freshness.tables[{i}]: missing required field 'timestamp_column'")

    # 4. Validate volume tables
    volume_cfg = config.get("volume", {})
    for i, tbl in enumerate(volume_cfg.get("tables", [])):
        if not tbl.get("table"):
            errors.append(f"volume.tables[{i}]: missing required field 'table'")

    # 5. Validate alert config
    alerts_cfg = config.get("alerts", {})
    default_channel = alerts_cfg.get("default_channel")
    supported_channels = {"slack", "email", "discord", "webhook", "teams", "pagerduty"}
    if default_channel and default_channel not in supported_channels:
        errors.append(
            f"alerts.default_channel '{default_channel}' is not supported (supported: {', '.join(sorted(supported_channels))})"
        )

    for i, rule in enumerate(alerts_cfg.get("routing", [])):
        if not rule.get("channel"):
            errors.append(f"alerts.routing[{i}]: missing required field 'channel'")

    # 6. Validate contracts directory if specified
    contracts_dir = config.get("contracts", {}).get("directory", "config/contracts")
    import glob as _glob
    import os as _os

    import yaml

    contract_files = _glob.glob(f"{contracts_dir}/*.yml") if _os.path.isdir(contracts_dir) else []
    contract_errors = 0
    for cf in contract_files:
        try:
            with open(cf) as f:
                doc = yaml.safe_load(f)
            if not doc or "contract" not in doc:
                warnings.append(f"Contract file {cf}: missing top-level 'contract' key")
        except yaml.YAMLError as e:
            errors.append(f"Contract file {cf}: YAML parse error — {e}")
            contract_errors += 1

    # 7. Report
    if warnings:
        for w in warnings:
            print(f"⚠️  {w}")
    if errors:
        for e in errors:
            print(f"❌ {e}")
        print(f"\n❌ Validation failed with {len(errors)} error(s).")
        return 2

    sections = list(config.keys())
    print(f"✅ Config valid — sections: {', '.join(sections)}")
    if contract_files:
        print(
            f"   Contracts validated: {len(contract_files) - contract_errors}/{len(contract_files)}"
        )
    return 0


def cmd_diff(args) -> int:
    """Compare the current schema snapshot vs last saved snapshot (offline)."""
    table = getattr(args, "table", None)
    print(f"🔍 Fetching schema diff{' for ' + table if table else ''} ...")
    try:
        path = f"/schema/diff?table_name={table}" if table else "/schema/diff"
        data = _get(path)
    except Exception as e:
        print(f"❌ Failed to fetch schema diff: {e}")
        return 1

    diffs = data.get("diffs", [])
    if not diffs:
        print("✅ No schema changes detected.")
        return 0

    print(f"\n   {'TABLE':<35} {'CHANGE':<18} {'COLUMN':<25} {'OLD':<20} NEW")
    print("   " + "-" * 110)
    for d in diffs:
        old_v = d.get("old_value", "") or ""
        new_v = d.get("new_value", "") or ""
        print(
            f"   {d.get('table_name', ''):<35} {d.get('change_type', ''):<18} {d.get('column_name', ''):<25} {old_v:<20} {new_v}"
        )
    print(f"\n   {len(diffs)} change(s) detected.")
    return 1  # exit 1 when drift found — useful for CI gates


def cmd_init(args) -> int:
    """Interactive wizard to initialize ObservaKit local configuration."""
    print("🚀 Welcome to ObservaKit!")
    print("This will create a basic 'kit.yml' configuration file in the current directory.\n")

    if os.path.exists("kit.yml"):
        print("⚠️  A kit.yml already exists in this directory. Do you want to overwrite it? (y/N)")
        resp = input("> ").strip().lower()
        if resp != "y":
            print("Aborted.")
            return 1

    print("Q: Which database type do you want to use for the metadata store? (sqlite/postgres)")
    db_type = input("> [sqlite]: ").strip().lower() or "sqlite"

    print("\nQ: Do you have a Slack Webhook URL for alerts? (Leave blank to skip)")
    slack_url = input("> ").strip()

    print(
        "\nQ: What is the main table you want to monitor for data freshness? (e.g. public.orders)"
    )
    table_name = input("> [public.orders]: ").strip() or "public.orders"

    yaml_content = f"""# ObservaKit Configuration
# Generated by `observakit init`

alerts:
  default_channel: slack
  slack:
    webhook_url: "{slack_url}"

warehouse:
  # In a real environment, you'd configure postgres, snowflake, bigquery, etc.
  type: {db_type}

freshness:
  enabled: true
  schedule_minutes: 15
  tables:
    - table: "{table_name}"
      timestamp_column: "updated_at"
      warn_after: "2h"
      fail_after: "4h"

volume:
  enabled: true
  rolling_window_days: 7
  tables:
    - table: "{table_name}"
      anomaly_threshold: 0.15
"""
    try:
        with open("kit.yml", "w") as f:
            f.write(yaml_content)
        print("\n✅ Created kit.yml successfully!")
        print("Run `observakit validate-config --config kit.yml` to verify your config.")
        print("Run `observakit test-alert` to verify your Slack webhook works.")
        return 0
    except Exception as e:
        print(f"❌ Failed to write config: {e}")
        return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        prog="observakit",
        description="ObservaKit CLI — data observability for small teams",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="ObservaKit API URL (default: $OBSERVAKIT_API_URL or http://localhost:8000)",
    )
    parser.add_argument("--api-key", default=None, help="API key (default: $OBSERVAKIT_API_KEY)")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to kit.yml (default: $OBSERVAKIT_CONFIG or config/kit.yml)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = sub.add_parser("status", help="Print health status of all monitored tables")
    p_status.add_argument(
        "--output", choices=["json"], default=None, help="Output format (json for scripting/CI)"
    )

    # check
    p_check = sub.add_parser("check", help="Run quality checks")
    p_check.add_argument("--dry-run", action="store_true", help="Preview without writing results")
    p_check.add_argument(
        "--output", choices=["json"], default=None, help="Output format (json for scripting/CI)"
    )

    # profile
    p_profile = sub.add_parser("profile", help="Run column profiling for a table")
    p_profile.add_argument("table", help="Table name (e.g. public.orders)")

    # suppress
    p_suppress = sub.add_parser("suppress", help="Suppress alerts for a table")
    p_suppress.add_argument("table", help="Table name")
    p_suppress.add_argument(
        "--minutes", type=int, default=60, help="Duration in minutes (default: 60)"
    )
    p_suppress.add_argument("--reason", default=None, help="Reason for suppression")

    # init
    sub.add_parser("init", help="Interactively initialize a local kit.yml configuration")

    # test-alert
    sub.add_parser("test-alert", help="Fire a test alert to configured channels")

    # validate-config
    p_validate = sub.add_parser(
        "validate-config", help="Dry-run parse kit.yml without connecting to warehouse"
    )
    p_validate.add_argument(
        "--config",
        dest="config",
        default=None,
        help="Path to kit.yml to validate (overrides --config at top level)",
    )

    # diff
    p_diff = sub.add_parser("diff", help="Show schema changes vs last saved snapshot")
    p_diff.add_argument("--table", default=None, help="Limit diff to a specific table")

    args = parser.parse_args()

    # Override env vars from flags
    if args.url:
        os.environ["OBSERVAKIT_API_URL"] = args.url
    if args.api_key:
        os.environ["OBSERVAKIT_API_KEY"] = args.api_key
    if hasattr(args, "config") and args.config and args.command != "validate-config":
        os.environ["OBSERVAKIT_CONFIG"] = args.config

    dispatch = {
        "status": cmd_status,
        "check": cmd_check,
        "profile": cmd_profile,
        "suppress": cmd_suppress,
        "init": cmd_init,
        "test-alert": cmd_test_alert,
        "validate-config": cmd_validate_config,
        "diff": cmd_diff,
    }

    handler = dispatch.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    # Exit codes: 0 = pass, 1 = check failures / runtime error, 2 = config error
    sys.exit(handler(args))


if __name__ == "__main__":
    main()
