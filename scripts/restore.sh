#!/usr/bin/env bash
# Restores a backup produced by scripts/backup.sh. Destructive: drops and
# recreates the target database. Requires explicit confirmation.
# Usage: scripts/restore.sh <backup-file.sql.gz> [dev|production]
set -euo pipefail

BACKUP_FILE="${1:?Usage: scripts/restore.sh <backup-file.sql.gz> [dev|production]}"
ENV="${2:-dev}"
COMPOSE_FILE="docker-compose.${ENV}.yml"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Unknown environment '$ENV' (expected dev or production)" >&2
  exit 1
fi

echo "==> Verifying gzip integrity of $BACKUP_FILE"
gzip -t "$BACKUP_FILE"

echo "This will DROP and recreate the $ENV database, then restore from $BACKUP_FILE."
read -r -p "Type 'yes' to confirm: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

# shellcheck disable=SC1091
[ -f .env ] && source .env

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -U "${POSTGRES_USER:-lial}" -c "DROP DATABASE IF EXISTS ${POSTGRES_DB:-lial_energy}_restoring;"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -U "${POSTGRES_USER:-lial}" -c "CREATE DATABASE ${POSTGRES_DB:-lial_energy}_restoring;"

gunzip -c "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -U "${POSTGRES_USER:-lial}" "${POSTGRES_DB:-lial_energy}_restoring"

echo "==> Restored into ${POSTGRES_DB:-lial_energy}_restoring."
echo "Verify it looks correct, then swap it in manually (rename databases) --"
echo "this script deliberately does not overwrite the live database automatically."
