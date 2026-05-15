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
<img width="635" height="82" alt="image" src="https://github.com/user-attachments/assets/5aa9d768-ed68-4ba5-b62e-629e40b95dc8" />

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

<img width="1065" height="86" alt="image" src="https://github.com/user-attachments/assets/93c98709-ea44-4492-88a6-435f15d128c2" />

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
<img width="1882" height="904" alt="image" src="https://github.com/user-attachments/assets/2cfbb0b1-2e26-4548-a046-e1d7fd93f107" />

2. Click the "Fork" button.

<img width="1359" height="635" alt="Screenshot 2026-05-14 154028" src="https://github.com/user-attachments/assets/a81725da-bbd3-4f93-bed9-ba767fd2eae6" />


3. Create your own copy of the repository.

---

## 4. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/ObservaKit.git

cd ObservaKit
```

<img width="766" height="270" alt="image" src="https://github.com/user-attachments/assets/db143f99-4812-4dd9-8106-5bb280c3583d" />

---

## 5. Configure Environment

### Windows Setup

```bash
copy .env.example .env
```
<img width="729" height="85" alt="image" src="https://github.com/user-attachments/assets/d9e49aa0-7159-4fad-80c6-a44749f49589" />

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
<img width="1666" height="137" alt="image" src="https://github.com/user-attachments/assets/72c8e455-f603-41b6-9f9b-0199ceadbca3" />

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
<img width="1179" height="728" alt="Screenshot 2026-05-14 155229" src="https://github.com/user-attachments/assets/30d9ec74-2dd5-46b4-882f-a726c29d3dff" />

- PostgreSQL container should be running successfully

- Backend service should be accessible on port `8000`

- Docker containers should appear in:

```bash
docker ps
```
<img width="1666" height="137" alt="image" src="https://github.com/user-attachments/assets/72c8e455-f603-41b6-9f9b-0199ceadbca3" />
