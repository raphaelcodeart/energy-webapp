#!/usr/bin/env bash
# Runs Alembic migrations against the running `api` container's database.
# Usage: scripts/migrate.sh [dev|production]
set -euo pipefail

ENV="${1:-dev}"
COMPOSE_FILE="docker-compose.${ENV}.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Unknown environment '$ENV' (expected dev or production)" >&2
  exit 1
fi

echo "==> Backing up database before migrating (see scripts/backup.sh)"
"$(dirname "$0")/backup.sh" "$ENV" || echo "WARNING: backup step failed or was skipped -- proceeding anyway is your call, Ctrl+C to abort"

echo "==> Running alembic upgrade head against $ENV"
docker compose -f "$COMPOSE_FILE" exec api alembic upgrade head
