# ObservaKit Production Guide

Deploying ObservaKit to production requires a shift from a simple Docker Compose local setup to a reliable, available, and secure infrastructure. This guide outlines best practices for deployment.

## Architecture & High Availability (HA)

ObservaKit is built on **FastAPI** and **APScheduler**. To ensure high availability and prevent duplicate scheduling, we use **PostgreSQL advisory locks**. This enables safely running multiple replicas.

### Core Recommendations:

- **Replica Count:** Run at least `2` replicas of `observakit-backend` to handle rolling updates smoothly.
- **Database Backend:** Use a managed PostgreSQL instance (e.g., AWS RDS, GCP Cloud SQL). SQLite is strictly for local dev and will not scale or safely coordinate multi-pod scheduler ticks.
- **Connection Pooling:** We recommend placing **PgBouncer** in front of your PostgreSQL node to handle connection pooling if you expect heavy simultaneous check iterations. ObservaKit uses SQLAlchemy connection pools internally, but external pooling ensures safety across multiple replica sets.

## Kubernetes Deployment (k8s/)

We provide a starter pack of Kubernetes manifests inside the `k8s/` directory.

```bash
k8s/
├── backend-deployment.yaml   # Scalable ReplicaSet for FastAPI
├── backend-service.yaml      # ClusterIP service
├── configmap.yaml            # Your kit.yml
└── secret.yaml               # Environment Variables / Credentials
```

### Applying the Manifests

1. Base64-encode your secrets or modify `secret.yaml` to inject them via a Secret Manager (e.g., AWS Secrets Manager, Hashicorp Vault, or SealedSecrets).
2. Apply the manifests:
```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/backend-service.yaml
```

## Security Best Practices

### Role-Based Access Control (RBAC)

Use the built-in per-project API keys rather than the legacy `OBSERVAKIT_API_KEY` global environment variable. 
ObservaKit distinguishes between `admin` and `viewer` roles, ensuring only authorized services can trigger checks or mutate suppressions.

### Resource Limits

Always enforce CPU and Memory limits (as defined in `backend-deployment.yaml`). APScheduler background threads can occasionally spike CPU usage if multiple heavy warehouse queries execute concurrently. A minimum of `512Mi` memory is recommended.

## Resiliency & Retries

Data warehouses are notoriously prone to transient connectivity issues (TCP resets, rate limits, maintenance windows). ObservaKit implements **industrial-grade exponential backoff** for all core warehouse operations:

- **Automatic Retries**: All `SELECT` queries for freshness, volume, distribution, and schema checks are decorated with `@resilient_query`.
- **Strategy**: 3 attempts with exponential backoff (`2^n` seconds).
- **Graceful Failure**: If all retries fail, a `critical` alert is dispatched specifically for the connectivity failure, preventing silent monitoring gaps.

## Alert Logging & Auditing

For production compliance and incident post-mortems, every alert dispatched by ObservaKit is persisted to the **`AlertLog`** metadata table.

- **Deduplication**: ObservaKit automatically suppresses duplicate alerts for the same table/type within a 60-minute window (configurable in `kit.yml`).
- **Audit Trail**: You can query the `AlertLog` table directly or via the API to see a history of what was sent, to which channel, and the full JSON payload:
  ```sql
  SELECT * FROM alert_log WHERE table_name = 'public.orders' ORDER BY dispatched_at DESC;
  ```

## Backups & Point-In-Time-Recovery (PITR)

ObservaKit maintains critical historical state (snapshots, freshness models, volume metrics). 
Since data anomaly detection requires the historical context stored inside your Postgres metadata database, you should:
- Maintain daily automated backups of the Postgres metadata DB.
- Consider utilizing PITR via WAL archiving. If a bad alert causes an automated pipeline teardown, you can easily restore state.
