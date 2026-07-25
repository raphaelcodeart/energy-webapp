#!/usr/bin/env bash
# Rolls back the most recent Alembic migration. Destructive-adjacent (a downgrade
# can drop columns/tables) -- requires explicit confirmation.
# Usage: scripts/rollback.sh [dev|production]
set -euo pipefail

ENV="${1:-dev}"
COMPOSE_FILE="docker-compose.${ENV}.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Unknown environment '$ENV' (expected dev or production)" >&2
  exit 1
fi

echo "This will run 'alembic downgrade -1' against the $ENV database."
read -r -p "Type 'yes' to confirm: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

docker compose -f "$COMPOSE_FILE" exec api alembic downgrade -1
