#!/usr/bin/env bash
# Pulls/builds images, migrates, restarts, then gates on health checks.
# Usage: scripts/deploy.sh [dev|production]
set -euo pipefail

ENV="${1:-dev}"
COMPOSE_FILE="docker-compose.${ENV}.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Unknown environment '$ENV' (expected dev or production)" >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo ".env not found -- copy .env.example to .env and fill in real values first." >&2
  exit 1
fi

echo "==> Building images"
docker compose -f "$COMPOSE_FILE" build

echo "==> Starting postgres/redis and waiting for health"
docker compose -f "$COMPOSE_FILE" up -d postgres redis
docker compose -f "$COMPOSE_FILE" up -d --wait postgres redis

echo "==> Running migrations"
docker compose -f "$COMPOSE_FILE" run --rm api alembic upgrade head

echo "==> Starting the rest of the stack"
docker compose -f "$COMPOSE_FILE" up -d

echo "==> Running health checks"
sleep 5
"$(dirname "$0")/health-check.sh" "$ENV"

echo "Deploy complete."
