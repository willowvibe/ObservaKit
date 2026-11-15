#!/usr/bin/env python3
"""Record the ObservaKit demo walkthrough at 1920x1080.

Scene order is fixed. The holds total 106 seconds; if the measured
narration is longer, trim words from docs/demo-script.md rather than
speeding up the audio. If it is shorter, extend the two Grafana holds.
"""

import html
import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "video-work"
OUT.mkdir(exist_ok=True)
UI = "http://localhost:8000/ui/"
GRAFANA = "http://localhost:3001"


def card(name: str, title: str, body: str) -> str:
    path = OUT / f"{name}.html"
    path.write_text(
        f"""<!doctype html><html><head><meta charset="utf-8"><style>
        html,body {{ margin:0; width:100%; height:100%; background:#0b1020; color:#e6ecff;
          font-family:'Inter',system-ui,sans-serif; }}
        .wrap {{ display:flex; flex-direction:column; justify-content:center;
          height:100%; padding:80px 110px; box-sizing:border-box; }}
        h1 {{ font-size:64px; margin:0 0 18px; letter-spacing:-1px; }}
        p {{ font-size:30px; line-height:1.5; color:#aab6d6; margin:8px 0; }}
        pre {{ font:24px/1.55 'SFMono-Regular',Consolas,monospace; background:#111831;
          border:1px solid #22305c; border-radius:12px; padding:28px; color:#d7e0ff;
          white-space:pre-wrap; overflow:hidden; }}
        .accent {{ color:#8b9cff; }}
        </style></head><body><div class="wrap"><h1>{title}</h1>{body}</div></body></html>"""
    )
    return path.as_uri()


def cli_output() -> str:
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
    return (result.stdout or result.stderr).strip()


def main() -> None:
    demo_log = OUT / "demo-up.log"
    if not demo_log.exists():
        raise SystemExit("run `make demo-reset 2>&1 | tee video-work/demo-up.log` first")

    title = card(
        "card-title",
        "ObservaKit",
        "<p>Self-hosted data observability for small data teams.</p>"
        "<p class='accent'>make demo-up</p>",
    )
    terminal = card(
        "card-terminal",
        "One command",
        f"<pre>$ make demo-up\n{html.escape(demo_log.read_text()[-900:])}</pre>",
    )
    cli = card(
        "card-cli",
        "The same checks in your terminal",
        f"<pre>$ observakit status\n{html.escape(cli_output())}</pre>",
    )
    end = card(
        "card-end",
        "ObservaKit",
        "<p>MIT licensed. Free to self-host.</p>"
        "<p class='accent'>github.com/willowvibe/ObservaKit</p>",
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(OUT),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        def hold(seconds: float) -> None:
            page.wait_for_timeout(int(seconds * 1000))

        page.goto(title)
        hold(4)
        page.goto(terminal)
        hold(8)
        page.goto(UI, wait_until="load")
        hold(14)
        page.get_by_role("button", name="Freshness").click()
        hold(12)
        page.get_by_role("button", name="Quality Checks").click()
        hold(12)
        page.get_by_role("button", name="Schema Drift").click()
        hold(10)
        page.get_by_role("button", name="Alerts").click()
        hold(10)
        page.get_by_role("button", name="Column Profiling").click()
        page.get_by_placeholder("Table (e.g. public.orders)").fill("public.orders")
        page.get_by_role("button", name="Profile").click()
        hold(8)
        page.goto(f"{GRAFANA}/d/observakit-quality-trends?from=now-15m&to=now&kiosk", wait_until="load")
        hold(8)
        page.goto(f"{GRAFANA}/d/observakit-data-freshness?from=now-15m&to=now&kiosk", wait_until="load")
        hold(8)
        page.goto(cli)
        hold(8)
        page.goto(end)
        hold(4)

        video = page.video
        context.close()
        browser.close()

    if video is None:
        raise SystemExit("Playwright did not produce a video")
    raw = Path(video.path())
    target = OUT / "observakit-raw.webm"
    raw.replace(target)
    print(target)


if __name__ == "__main__":
    main()
