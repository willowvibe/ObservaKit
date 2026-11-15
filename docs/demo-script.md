# ObservaKit demo — 2-minute walkthrough

Format: 1920×1080, H.264 + AAC, burned-in captions. Recorded from the demo stack.

| Time | Visual | Narration |
|---|---|---|
| 0:00–0:04 | Title card | Your pipeline says success. Your dashboard is three hours stale. Nobody notices until a stakeholder does. |
| 0:04–0:12 | Terminal card: `make demo-up` and real startup output | ObservaKit is a self-hosted observability layer. One command brings up the stack with a seeded demo warehouse. |
| 0:12–0:26 | Dashboard overview, health grid | A seeded warehouse, seven days of history, and the checks that matter: freshness, volume, quality, and schema drift. |
| 0:26–0:38 | Freshness tab | The customers table is deliberately stale. ObservaKit records the exact lag and marks the check failed. |
| 0:38–0:50 | Quality Checks tab, custom SQL results | Custom SQL checks run against the warehouse. Passing and failing results are stored with the table and timestamp. |
| 0:50–1:00 | Schema Drift tab | Schema snapshots catch added, removed, or retyped columns before downstream reports break. |
| 1:00–1:10 | Alerts tab | Alerts are routed to Slack, email, Teams, PagerDuty, or a generic webhook, with noise suppression. |
| 1:10–1:18 | Column Profiling tab | Column profiles show null rates, distinct counts, and value ranges without a separate profiling tool. |
| 1:18–1:26 | Grafana quality trends | Prometheus and Grafana are included, so the same checks feed dashboards without another vendor. |
| 1:26–1:34 | Grafana freshness | The freshness dashboard shows the same lag data over time, ready for on-call. |
| 1:34–1:42 | Terminal card: `observakit status` | The CLI and API expose the same data for CI and on-call workflows. |
| 1:42–1:46 | End card: repo URL, `make demo-up` | ObservaKit is MIT-licensed and free to self-host. The repo link and the one-command demo are in the release notes. |

## Shot list

1. Title card (0:00–0:04).
2. Terminal card with real `make demo-up` output (0:04–0:12).
3. UI overview (0:12–0:26).
4. UI freshness (0:26–0:38).
5. UI quality checks (0:38–0:50).
6. UI schema drift (0:50–1:00).
7. UI alerts (1:00–1:10).
8. UI column profiling (1:10–1:18).
9. Grafana quality trends (1:18–1:26).
10. Grafana freshness (1:26–1:34).
11. Terminal card with `observakit status` (1:34–1:42).
12. End card (1:42–1:46).
