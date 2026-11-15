#!/usr/bin/env sh
set -eu

BASE_URL="${OBSERVAKIT_URL:-http://backend:8000}"
API_KEY="${OBSERVAKIT_API_KEY:-observakit-demo-key}"

echo "Waiting for backend health..."
attempt=0
until curl -fsS "$BASE_URL/healthz" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "backend did not become healthy after 120 seconds" >&2
    exit 1
  fi
  sleep 2
done

echo "Seeding 7 days of metadata history..."
python /app/scripts/generate_mock_data.py

echo "Running real checks against the demo warehouse..."
for path in freshness/poll checks/run schema/snapshot checks/volume; do
  echo "  POST /$path"
  curl -fsS -X POST -H "X-API-Key: $API_KEY" "$BASE_URL/$path" >/dev/null
done

echo "Demo seed complete."
