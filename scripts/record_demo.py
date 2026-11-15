#!/usr/bin/env python3
"""Record the ObservaKit demo walkthrough at 1920x1080.

Scene order is fixed. Each scene holds for the larger of its base duration
and its measured narration segment plus 0.5s, so the voice track and the
visuals stay aligned. The timeline is written to /tmp/observakit-tts/holds.json
for the audio and caption steps.
"""

import html
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Error, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "video-work"
OUT.mkdir(exist_ok=True)
TTS = Path("/tmp/observakit-tts")
UI = "http://localhost:8000/ui/"
GRAFANA = "http://localhost:3001"
BASE_HOLDS = [4, 8, 14, 12, 12, 10, 10, 8, 8, 8, 8, 4]


def segment_durations() -> list[float]:
    durations = []
    for index in range(len(BASE_HOLDS)):
        segment = TTS / f"{index:02d}.mp3"
        if not segment.exists():
            raise SystemExit(f"missing narration segment {segment}")
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(segment),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        durations.append(float(result.stdout.strip()))
    return durations


def build_timeline() -> dict:
    durations = segment_durations()
    holds = [max(base, length + 0.5) for base, length in zip(BASE_HOLDS, durations)]
    starts = []
    cursor = 0.0
    for hold in holds:
        starts.append(round(cursor, 3))
        cursor += hold
    timeline = {
        "audio_durations": [round(length, 3) for length in durations],
        "holds": [round(hold, 3) for hold in holds],
        "scene_starts": starts,
        "total": round(cursor, 3),
    }
    (TTS / "holds.json").write_text(json.dumps(timeline, indent=2) + "\n")
    return timeline


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

    for stale in OUT.glob("page@*.webm"):
        stale.unlink()

    timeline = build_timeline()
    holds = timeline["holds"]
    print(f"timeline: {timeline['total']:.2f}s", file=sys.stderr)

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

        def scene(index: int, action) -> None:
            started = time.monotonic()
            action()
            remaining = holds[index] - (time.monotonic() - started)
            if remaining > 0:
                page.wait_for_timeout(int(remaining * 1000))

        def profile() -> None:
            page.get_by_role("button", name="Column Profiling").click()
            page.get_by_placeholder("Table (e.g. public.orders)").fill("public.orders")
            page.get_by_role("button", name="Profile").click()
            page.wait_for_selector("table.data-table tbody tr", timeout=15000)

        scene(0, lambda: page.goto(title))
        scene(1, lambda: page.goto(terminal))
        scene(2, lambda: page.goto(UI, wait_until="load"))
        scene(3, lambda: page.get_by_role("button", name="Freshness").click())
        scene(4, lambda: page.get_by_role("button", name="Quality Checks").click())
        scene(5, lambda: page.get_by_role("button", name="Schema Drift").click())
        scene(6, lambda: page.get_by_role("button", name="Alerts").click())
        scene(7, profile)
        scene(
            8,
            lambda: page.goto(
                f"{GRAFANA}/d/observakit-quality-trends?from=now-15m&to=now&kiosk", wait_until="load"
            ),
        )
        scene(
            9,
            lambda: page.goto(
                f"{GRAFANA}/d/observakit-data-freshness?from=now-15m&to=now&kiosk", wait_until="load"
            ),
        )
        scene(10, lambda: page.goto(cli))
        scene(11, lambda: page.goto(end))

        video = page.video
        # Resolve the path while Playwright is still running; video.path()
        # raises once the context manager stops the event loop.
        video_path = None
        if video is not None:
            try:
                video_path = video.path()
            except Error:
                video_path = None
        context.close()
        browser.close()

    if video_path is None:
        # Playwright can leave page.video unset or unusable even though the
        # context wrote the recording. Fall back to the newest raw capture.
        candidates = sorted(OUT.glob("page@*.webm"), key=lambda path: path.stat().st_mtime)
        if not candidates:
            raise SystemExit("Playwright did not produce a video")
        raw = candidates[-1]
    else:
        raw = Path(video_path)
    target = OUT / "observakit-raw.webm"
    if target.exists():
        target.unlink()
    raw.replace(target)
    print(target)


if __name__ == "__main__":
    main()
