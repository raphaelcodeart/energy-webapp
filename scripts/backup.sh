#!/usr/bin/env bash
# Dumps Postgres to a timestamped, gzip-compressed file under ./backups/.
# This is the mechanical part only -- retention (7 daily / 4 weekly / 6 monthly,
# see docs/deployment.md), off-server copy, and encryption are Phase H work and
# are NOT implemented by this script yet. Do not treat a local-disk-only backup
# as sufficient disaster recovery.
# Usage: scripts/backup.sh [dev|production]
set -euo pipefail

ENV="${1:-dev}"
COMPOSE_FILE="docker-compose.${ENV}.yml"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="./backups"
BACKUP_FILE="${BACKUP_DIR}/lial_energy_${ENV}_${TIMESTAMP}.sql.gz"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Unknown environment '$ENV' (expected dev or production)" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# shellcheck disable=SC1091
[ -f .env ] && source .env

echo "==> Dumping database to $BACKUP_FILE"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-lial}" "${POSTGRES_DB:-lial_energy}" | gzip > "$BACKUP_FILE"

echo "==> Verifying gzip integrity"
gzip -t "$BACKUP_FILE"

echo "Backup complete: $BACKUP_FILE"
