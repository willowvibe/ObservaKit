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

<img width="1359" height="635" alt="Screenshot 2026-05-14 154028" src="https://github.com/user-attachments/assets/a81725da-bbd3-4f93-bed9-ba767fd2eae6" />


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

<img width="1395" height="773" alt="Screenshot 2026-05-14 154522" src="https://github.com/user-attachments/assets/1e355397-7536-4599-8a43-42a07472f406" />


---

## 7. Verify Installation

After starting the containers, verify that ObservaKit is running by opening:

```text
http://localhost:8000/docs
```

<img width="1179" height="728" alt="Screenshot 2026-05-14 155229" src="https://github.com/user-attachments/assets/30d9ec74-2dd5-46b4-882f-a726c29d3dff" />


If the Swagger UI loads successfully, the backend service is running correctly.

The endpoint:

```text
http://localhost:8000/ui
```

may not be enabled in the current configuration and can return:

```json
{"detail":"Not Found"}
```
<img width="1231" height="715" alt="Screenshot 2026-05-14 154653" src="https://github.com/user-attachments/assets/24c16360-9584-4c66-90e4-bc67ad143995" />


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
