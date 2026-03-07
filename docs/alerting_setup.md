# Alerting Setup Guide

ObservaKit supports **Slack** and **Email (SMTP)** alerts out of the box, with PagerDuty planned for a future release.

## Slack Setup

### 1. Create a Slack Incoming Webhook

1. Go to [Slack API: Incoming Webhooks](https://api.slack.com/messaging/webhooks)
2. Click **Create a new Slack app** → **From scratch**
3. Name it `ObservaKit` and select your workspace
4. Under **Incoming Webhooks**, toggle it **On**
5. Click **Add New Webhook to Workspace** and select your channel
6. Copy the webhook URL

### 2. Configure ObservaKit

Add the webhook URL to your `.env` file:

```bash
SLACK_WEBHOOK_URL=<your-slack-webhook-url>
SLACK_CHANNEL=#data-alerts
```

Or configure in `config/kit.yml`:

```yaml
alerts:
  slack:
    webhook_url: ${SLACK_WEBHOOK_URL}
    channel: "#data-alerts"
    username: ObservaKit
    icon_emoji: ":mag:"
```

### 3. Test the Alert

```bash
curl -X POST http://localhost:8000/freshness/poll
```

If any table exceeds its freshness threshold, you'll see an alert in your Slack channel.

## Email (SMTP) Setup

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

### 2. Configure in kit.yml

```yaml
alerts:
  email:
    smtp_host: ${SMTP_HOST}
    smtp_port: ${SMTP_PORT}
    from: ${ALERT_EMAIL_FROM}
    to: ${ALERT_EMAIL_TO}
```

### 3. Point Checks to Email

In `config/kit.yml`, set `alert: email` for any table:

```yaml
freshness:
  tables:
    - table: public.orders
      timestamp_column: updated_at
      warn_after: 1h
      fail_after: 2h
      alert: email  # ← Use email instead of slack
```

## Alert Types

| Alert | Trigger | Example |
|-------|---------|---------|
| Freshness | Table lag exceeds `warn_after` or `fail_after` | 🟡 Freshness Alert: public.orders — Lag: 1.5 hours |
| Volume | Row count deviates >X% from 7-day rolling avg | 🔴 Volume Anomaly: public.orders — Deviation: 45.2% |
| Schema Drift | Column added, removed, or type changed | ⚠️ Schema Drift: public.orders — Column `discount_pct` added |
| Quality | Soda/GX check fails | ❌ Quality Check Failed: missing_count(order_id) = 3 |

## PagerDuty (Planned)

PagerDuty integration is on the roadmap. To contribute, add a new dispatcher in `alerts/pagerduty.py` implementing the `AlertDispatcher` base class.
