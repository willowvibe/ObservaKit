#!/usr/bin/env python3
"""Capture ObservaKit proof screenshots from the running demo stack."""

import html
import json
import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets" / "screenshots"
# The FastAPI build serves the landing page at /ui/; the React dashboard
# route is /ui/ui (basename /ui/ + <Route path="/ui">).
UI = "http://localhost:8000/ui/ui"
GRAFANA = "http://localhost:3001"
CLI_HTML = ROOT / "docs" / "assets" / "_cli.html"


def wait_for(url: str, timeout: int = 60) -> None:
    import time
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(2)
    raise SystemExit(f"timed out waiting for {url}")


def capture_ui(page) -> None:
    # The dashboard polls in the background, so networkidle can hang.
    page.goto(UI, wait_until="load")
    page.wait_for_timeout(4000)
    page.screenshot(path=OUT / "ui-overview.png", full_page=False)

    for tab, filename in [
        ("Freshness", "ui-freshness.png"),
        ("Quality Checks", "ui-quality.png"),
        ("Alerts", "ui-alerts.png"),
    ]:
        page.get_by_role("button", name=tab).click()
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / filename, full_page=False)

    # Profiling only renders after a table is entered and profiled.
    page.get_by_role("button", name="Column Profiling").click()
    page.get_by_placeholder("Table (e.g. public.orders)").fill("public.orders")
    page.get_by_role("button", name="Profile").click()
    page.wait_for_timeout(3000)
    page.screenshot(path=OUT / "ui-profiling.png", full_page=False)


def capture_grafana(page) -> None:
    for uid, filename in [
        ("observakit-quality-trends", "grafana-quality.png"),
        ("observakit-data-freshness", "grafana-freshness.png"),
    ]:
        # The demo's Prometheus metrics only exist from seed time, and the
        # dashboards' default 7-day range renders them as "No data".
        page.goto(
            f"{GRAFANA}/d/{uid}?from=now-15m&to=now", wait_until="load"
        )
        page.wait_for_timeout(15000)
        page.screenshot(path=OUT / filename, full_page=False)


def capture_cli(page) -> None:
    env = os.environ.copy()
    env["OBSERVAKIT_API_URL"] = "http://localhost:8000"
    env["OBSERVAKIT_API_KEY"] = "observakit-demo-key"
    env["NO_COLOR"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "status"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout.strip() or result.stderr.strip()
    if not output:
        raise SystemExit("CLI returned no output")

    CLI_HTML.write_text(
        f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
body {{ margin: 0; background: #0b1020; color: #d7e0ff;
       font: 15px/1.55 'SFMono-Regular', Consolas, monospace; }}
.window {{ padding: 28px 32px; }}
.bar {{ color: #7c8db5; margin-bottom: 18px; }}
pre {{ white-space: pre-wrap; }}
.prompt {{ color: #7ee787; }}
</style></head><body><div class="window">
<div class="bar">observakit — demo stack</div>
<pre><span class="prompt">$</span> observakit status
{html.escape(output)}
</pre></div></body></html>"""
    )
    page.goto(CLI_HTML.as_uri(), wait_until="load")
    page.wait_for_timeout(300)
    page.screenshot(path=OUT / "cli-output.png", full_page=False)
    CLI_HTML.unlink()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    wait_for("http://localhost:8000/healthz")
    wait_for("http://localhost:3001/api/health")
    # Give Prometheus one scrape interval to pick up the seeder's checks.
    import time

    time.sleep(20)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        capture_ui(page)
        capture_grafana(page)
        capture_cli(page)
        browser.close()

    print(json.dumps(sorted(p.name for p in OUT.glob("*.png")), indent=2))


if __name__ == "__main__":
    main()
