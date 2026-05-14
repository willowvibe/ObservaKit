# ObservaKit Setup Guide

## 1. Introduction

ObservaKit is a self-hosted data observability platform for monitoring data pipelines, freshness, schema drift, alerts, and overall data quality.

---

## 2. Prerequisites

Before starting, install the following:

- Docker Desktop
- Git
- VS Code
- Python 3.10+

Ensure Docker Compose V2 is installed.

Verify using:

```bash
docker compose version
```

### Windows Docker Issue

If Docker shows:

```text
WSL needs updating
```

Run:

```bash
wsl --update
```

Then restart Docker Desktop.

### Docker Build Network Error

If Docker shows:

```text
Unable to connect to deb.debian.org
```

Retry the docker compose command again. Temporary network issues during image build may cause package installation failures.

---

## 3. Fork the Repository

1. Open the original repository:

```text
https://github.com/willowvibe/ObservaKit
```

2. Click the "Fork" button.

![alt text](<Screenshot 2026-05-14 154028.png>)

3. Create your own copy of the repository.

---

## 4. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/ObservaKit.git

cd ObservaKit
```

---

## 5. Configure Environment

### Windows Setup

```bash
copy .env.example .env
```

### Linux/macOS Setup

```bash
cp .env.example .env
```

This creates a `.env` file from the example template.

---

## 6. Run the Project

Start the application using Docker Compose:

```bash
docker compose up --build
```

The initial build may take a few minutes depending on your internet connection.

![alt text](<Screenshot 2026-05-14 154522.png>)

---

## 7. Verify Installation

After starting the containers, verify that ObservaKit is running by opening:

```text
http://localhost:8000/docs
```

![alt text](<Screenshot 2026-05-14 155229.png>)

If the Swagger UI loads successfully, the backend service is running correctly.

The endpoint:

```text
http://localhost:8000/ui
```

may not be enabled in the current configuration and can return:

```json
{"detail":"Not Found"}
```
![alt text](<Screenshot 2026-05-14 154653.png>)

### Check Running Containers

```bash
docker ps
```

Expected running containers:

- observakit-backend
- observakit-postgres

Default ports:

- Backend: `8000`
- PostgreSQL: `5433`

---

## 8. Expected Result

After successful startup:

- Swagger API documentation should be available at:

```text
http://localhost:8000/docs
```

- PostgreSQL container should be running successfully

- Backend service should be accessible on port `8000`

- Docker containers should appear in:

```bash
docker ps
```