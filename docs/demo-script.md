# ObservaKit demo — 2-minute walkthrough

Format: 1920×1080, H.264 + AAC, voiceover only (no burned-in captions), with 0.35 s crossfades between scenes. Recorded from the demo stack.

| Time | Visual | Narration |
|---|---|---|
| 0:00–0:07 | Title card | Your pipeline says success. Your dashboard is three hours stale. Nobody notices until a stakeholder does. |
| 0:07–0:15 | Terminal card: `make demo-up` and real startup output | ObservaKit is a self-hosted observability layer. One command brings up the stack with a seeded demo warehouse. |
| 0:15–0:29 | Dashboard overview, health grid | A seeded warehouse, seven days of history, and the checks that matter: freshness, volume, quality, and schema drift. |
| 0:29–0:41 | Freshness tab | The customers table is deliberately stale. ObservaKit records the exact lag and marks the check failed. |
| 0:41–0:53 | Quality Checks tab, custom SQL results | Custom SQL checks run against the warehouse. Passing and failing results are stored with the table and timestamp. |
| 0:53–1:03 | Schema Drift tab | Schema snapshots catch added, removed, or retyped columns before downstream reports break. |
| 1:03–1:13 | Alerts tab | Alerts are routed to Slack, email, Teams, PagerDuty, or a generic webhook, with noise suppression. |
| 1:13–1:21 | Column Profiling tab | Column profiles show null rates, distinct counts, and value ranges without a separate profiling tool. |
| 1:21–1:29 | Grafana quality trends | Prometheus and Grafana are included, so the same checks feed dashboards without another vendor. |
| 1:29–1:37 | Grafana freshness | The freshness dashboard shows the same lag data over time, ready for on-call. |
| 1:37–1:45 | Terminal card: `observakit status` | The CLI and API expose the same data for CI and on-call workflows. |
| 1:45–1:53 | End card: repo URL, `make demo-up` | ObservaKit is MIT-licensed and free to self-host. The repo link and the one-command demo are in the release notes. |

## Shot list

1. Title card (0:00–0:07).
2. Terminal card with real `make demo-up` output (0:07–0:15).
3. UI overview (0:15–0:29).
4. UI freshness (0:29–0:41).
5. UI quality checks (0:41–0:53).
6. UI schema drift (0:53–1:03).
7. UI alerts (1:03–1:13).
8. UI column profiling (1:13–1:21).
9. Grafana quality trends (1:21–1:29).
10. Grafana freshness (1:29–1:37).
11. Terminal card with `observakit status` (1:37–1:45).
12. End card (1:45–1:53).
