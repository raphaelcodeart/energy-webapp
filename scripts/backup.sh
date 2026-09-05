#!/usr/bin/env bash
# Dumps Postgres to a timestamped, gzip-compressed file under ./backups/,
# then deletes any same-environment backup older than RETENTION_DAYS.
# Scheduled daily via cron (see crontab -l) -- see docs/deployment.md for
# the fuller 7-daily/4-weekly/6-monthly retention shape and off-server copy,
# neither of which this script implements yet: this is a same-disk safety
# net, not full disaster recovery (a lost/corrupted disk takes the backups
# with it) -- an off-server copy is still a real follow-up, not done here.
# Usage: scripts/backup.sh [dev|production]
set -euo pipefail

ENV="${1:-dev}"
COMPOSE_FILE="docker-compose.${ENV}.yml"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="./backups"
BACKUP_FILE="${BACKUP_DIR}/lial_energy_${ENV}_${TIMESTAMP}.sql.gz"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Unknown environment '$ENV' (expected dev or production)" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# shellcheck disable=SC1091
# Every value in .env must be quoted if it contains spaces (e.g.
# COMPANY_BANK_HOLDER="Lial Energy") -- plain `source` parses it as bash,
# not as a dotenv file, so an unquoted space breaks this line with a
# confusing "command not found" and aborts the whole backup silently
# (confirmed live: COMPANY_BANK_HOLDER=Lial Energy without quotes did
# exactly this before it was fixed).
[ -f .env ] && source .env

echo "==> Dumping database to $BACKUP_FILE"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-lial}" "${POSTGRES_DB:-lial_energy}" | gzip > "$BACKUP_FILE"

echo "==> Verifying gzip integrity"
gzip -t "$BACKUP_FILE"

echo "Backup complete: $BACKUP_FILE"

echo "==> Removing ${ENV} backups older than ${RETENTION_DAYS} days"
find "$BACKUP_DIR" -maxdepth 1 -name "lial_energy_${ENV}_*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete
