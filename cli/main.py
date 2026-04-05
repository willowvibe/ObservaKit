"""
ObservaKit CLI — observakit

Usage:
    observakit check checks/my_project/orders.yml
    observakit status
    observakit profile public.orders
    observakit suppress public.orders --minutes 60 --reason "Planned ETL reload"

Install: pip install -e .
Then use: observakit --help
"""

from __future__ import annotations

import argparse
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
        sys.exit(1)
    url = f"{_api_url()}{path}"
    resp = httpx.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, body: dict | None = None) -> dict:
    try:
        import httpx
    except ImportError:
        print("httpx is required for the CLI. Install with: pip install httpx")
        sys.exit(1)
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
    try:
        data = _get("/status")
    except Exception as e:
        print(f"❌ Could not reach ObservaKit at {_api_url()}: {e}")
        return 1

    summary = data.get("summary", {})
    tables = data.get("tables", [])

    print(f"\n🔭 ObservaKit Status  (window: {data.get('window_hours', 24)}h)")
    print(f"   Healthy: {summary.get('healthy', 0)}  Warn: {summary.get('warn', 0)}  Fail: {summary.get('fail', 0)}\n")

    if not tables:
        print("   No monitored tables found in the last 24 hours.")
        return 0

    # Header
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
    dry = getattr(args, "dry_run", False)
    path = f"/checks/run?dry_run={str(dry).lower()}"
    print(f"{'🔍 Dry run:' if dry else '🚀 Running'} quality checks via {_api_url()}{path}")
    try:
        data = _post(path)
    except Exception as e:
        print(f"❌ Check run failed: {e}")
        return 1

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

    print("\nQ: What is the main table you want to monitor for data freshness? (e.g. public.orders)")
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
        "--url", default=None,
        help="ObservaKit API URL (default: $OBSERVAKIT_API_URL or http://localhost:8000)"
    )
    parser.add_argument(
        "--api-key", default=None,
        help="API key (default: $OBSERVAKIT_API_KEY)"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Print health status of all monitored tables")

    # check
    p_check = sub.add_parser("check", help="Run quality checks")
    p_check.add_argument("--dry-run", action="store_true", help="Preview without writing results")

    # profile
    p_profile = sub.add_parser("profile", help="Run column profiling for a table")
    p_profile.add_argument("table", help="Table name (e.g. public.orders)")

    # suppress
    p_suppress = sub.add_parser("suppress", help="Suppress alerts for a table")
    p_suppress.add_argument("table", help="Table name")
    p_suppress.add_argument("--minutes", type=int, default=60, help="Duration in minutes (default: 60)")
    p_suppress.add_argument("--reason", default=None, help="Reason for suppression")

    # init
    sub.add_parser("init", help="Interactively initialize a local kit.yml configuration")

    # test-alert
    sub.add_parser("test-alert", help="Fire a test alert to configured channels")

    args = parser.parse_args()

    # Override env vars from flags
    if args.url:
        os.environ["OBSERVAKIT_API_URL"] = args.url
    if args.api_key:
        os.environ["OBSERVAKIT_API_KEY"] = args.api_key

    dispatch = {
        "status": cmd_status,
        "check": cmd_check,
        "profile": cmd_profile,
        "suppress": cmd_suppress,
        "init": cmd_init,
        "test-alert": cmd_test_alert,
    }

    handler = dispatch.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
