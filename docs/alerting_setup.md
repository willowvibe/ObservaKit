# Alerting Setup Guide

ObservaKit supports six alert channels out of the box: **Slack**, **Microsoft Teams**, **PagerDuty (Native)**, **Email (SMTP)**, **Discord**, and a generic **Webhook**.

All channels are configured through routing rules in `config/kit.yml` and resolved at runtime using the `dispatch_alert()` function. Each rule can match on `alert_type` and/or a `table_pattern` glob, with a fallback to `default_channel` when no rule matches.

---

## Slack

### 1. Create a Slack Incoming Webhook

1. Go to [Slack API: Incoming Webhooks](https://api.slack.com/messaging/webhooks)
2. Click **Create a new Slack app** → **From scratch**
3. Name it `ObservaKit` and select your workspace
4. Under **Incoming Webhooks**, toggle it **On**
5. Click **Add New Webhook to Workspace** and select your channel
6. Copy the webhook URL

### 2. Configure ObservaKit

Add to your `.env` file:

```bash
SLACK_WEBHOOK_URL=<your-slack-webhook-url>
SLACK_CHANNEL=#data-alerts
OBSERVAKIT_DASHBOARD_URL=http://your-observakit-domain.com
```

ObservaKit uses **Slack Block Kit** to send rich, actionable alerts. Status is colour-coded (Red for Critical, Yellow for Warning) and includes a direct link to the affected table in the dashboard.

Or configure routing in `config/kit.yml`:

```yaml
alerts:
  default_channel: slack
  routing:
    - match:
        alert_type: freshness
      channel: slack
      slack_channel: "#data-freshness"
    - match:
        alert_type: quality
        table_pattern: "payments.*"
      channel: slack
      slack_channel: "#payments-data"
```

### 3. Test the Alert

```bash
curl -X POST http://localhost:8000/freshness/poll \
  -H "X-API-Key: $OBSERVAKIT_API_KEY"
```

---

## Microsoft Teams

ObservaKit sends rich **Adaptive Cards** to Microsoft Teams, featuring layout-specific status blocks and deep links to the dashboard.

### 1. Create a Teams Incoming Webhook

1. Open your Teams channel → **Workflows** (or Connectors) → **Incoming Webhook**
2. Name it `ObservaKit` and copy the URL

### 2. Configure ObservaKit

Add to your `.env` file:

```bash
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/XXXXXXXX/XXXXXXXX
```

### 3. Route Alerts to Teams

In `config/kit.yml`:

```yaml
alerts:
  routing:
    - match:
        alert_type: freshness
      channel: teams
```

---

## PagerDuty (Native)

While you can use the generic Webhook for PagerDuty, the native integration uses the **Events API v2** for better event deduplication and incident grouping.

### 1. Configure PagerDuty

Add to your `.env` file:

```bash
PAGERDUTY_ROUTING_KEY=your-pagerduty-integration-key
```

### 2. Route Alerts

In `config/kit.yml`:

```yaml
alerts:
  routing:
    - match:
        alert_type: quality
      channel: pagerduty
```

---

## Email (SMTP)

### 1. Configure SMTP Credentials

Add to your `.env` file:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
ALERT_EMAIL_FROM=observakit@yourcompany.com
ALERT_EMAIL_TO=data-team@yourcompany.com
```

> **Note for Gmail**: Use an [App Password](https://support.google.com/accounts/answer/185833) instead of your account password.

### 2. Route Alerts to Email

In `config/kit.yml`:

```yaml
alerts:
  routing:
    - match:
        alert_type: quality
      channel: email
```

---

## Discord

Discord is popular with developer-heavy teams. ObservaKit sends rich embedded messages with colour-coded severity.

### 1. Create a Discord Webhook

1. Open your Discord server → **Server Settings** → **Integrations** → **Webhooks**
2. Click **New Webhook**, choose your `#data-alerts` channel
3. Copy the webhook URL

### 2. Configure ObservaKit

Add to your `.env` file:

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/XXXXXXXX/XXXXXXXXXXXXXXXXXXXXXXXX
DISCORD_MENTION=@here          # Optional: ping on-call when alerts fire
```

### 3. Route Alerts to Discord

In `config/kit.yml`:

```yaml
alerts:
  default_channel: discord
```

Colour coding is automatic:
| Alert Type | Colour |
|------------|--------|
| volume, quality, contract | 🔴 Red |
| freshness, schema, distribution, finops | 🟡 Yellow |

---

## Webhook (PagerDuty / Opsgenie / n8n / custom)

The generic webhook channel posts a signed JSON payload to any HTTP endpoint.

### Payload Format

```json
{
  "source": "observakit",
  "version": "0.1.10",
  "alert_type": "volume",
  "table_name": "public.orders",
  "subject": "🔴 Volume Anomaly: public.orders",
  "message": "...",
  "timestamp": "2024-01-15T10:30:00Z",
  "severity": "critical"
}
```

Severity mapping:

| Alert Type | Severity |
|------------|----------|
| quality, volume, contract | critical |
| freshness, schema, distribution | warning |
| finops | info |

### HMAC Signature Verification (optional)

Set `WEBHOOK_SECRET` and ObservaKit adds an `X-ObservaKit-Signature: sha256=<hex>` header. Verify on the receiver side with `hmac.compare_digest`.

### 1. Configure the Webhook

Add to your `.env` file:

```bash
WEBHOOK_ALERT_URL=https://events.pagerduty.com/v2/enqueue
WEBHOOK_SECRET=my-shared-secret          # optional
WEBHOOK_AUTH_HEADER=Bearer my-api-token  # optional extra header
```

### 2. Route Alerts to Webhook

In `config/kit.yml`:

```yaml
alerts:
  routing:
    - match:
        alert_type: quality
      channel: webhook
      webhook_url: https://events.pagerduty.com/v2/enqueue
      webhook_severity_map:
        quality: critical
        freshness: warning
```

---

## Alert Routing Rules

Rules are evaluated top-to-bottom; the **first match wins**. If no rule matches, `default_channel` is used.

```yaml
alerts:
  default_channel: slack

  routing:
    # All schema alerts for payments tables → Slack #finance-data
    - match:
        alert_type: schema
        table_pattern: "payments.*"
      channel: slack
      slack_channel: "#finance-data"

    # All quality failures → PagerDuty webhook
    - match:
        alert_type: quality
      channel: webhook
      webhook_url: https://events.pagerduty.com/v2/enqueue

    # Everything else → default (slack #data-alerts)
```

---

## Alert Types

| Alert | Trigger | Example |
|-------|---------|---------|
| `freshness` | Table lag exceeds `warn_after` or `fail_after` | 🟡 Freshness Alert: public.orders — Lag: 1.5 hours |
| `volume` | Row count deviates >X% from 7-day rolling avg | 🔴 Volume Anomaly: public.orders — Deviation: 45.2% |
| `schema` | Column added, removed, or type changed | ⚠️ Schema Drift: public.orders — Column `discount_pct` added |
| `quality` | Soda check or custom SQL assertion fails | ❌ Quality Check Failed: missing_count(order_id) = 3 |
| `distribution` | Column value share shifts beyond threshold | 📊 Distribution Drift: public.orders.status |
| `contract` | Data contract rule violated | 📋 Contract Violation: orders_v1 |
| `finops` | Warehouse compute cost anomaly | 💰 FinOps: BigQuery bytes exceeded threshold |

---

## Alert Suppression

Suppress alerts during planned maintenance windows via the API:

```bash
curl -X POST http://localhost:8000/suppress \
  -H "X-API-Key: $OBSERVAKIT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "public.orders",
    "suppressed_until": "2024-01-15T08:00:00Z",
    "reason": "Planned backfill — ignore volume spikes"
  }'
```
