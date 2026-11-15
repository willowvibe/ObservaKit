# ---- Stage 1: build the React dashboard ----
FROM node:20-alpine AS ui

WORKDIR /ui

COPY landing-page/package.json landing-page/package-lock.json ./
RUN npm ci

COPY landing-page/ ./
# vite.config.js reads ../VERSION relative to /ui, i.e. /VERSION
COPY VERSION /VERSION
ARG VITE_API_KEY=""
ENV VITE_API_KEY=$VITE_API_KEY
RUN VITE_BUILD_SERVE=fastapi npm run build

# ---- Stage 2: runtime ----
FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY connectors/ ./connectors/
COPY alerts/ ./alerts/
COPY config/ ./config/
COPY checks/ ./checks/
COPY scripts/ ./scripts/

# The Vite build writes to ../backend/static from /ui, i.e. /backend/static
COPY --from=ui /backend/static ./backend/static

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
