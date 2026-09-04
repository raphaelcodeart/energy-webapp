#!/usr/bin/env bash
# Regenerates docs/database-schema.sql -- a real, structure-only pg_dump of
# the live database (no data), --no-owner/--no-privileges so it applies
# cleanly on a new server even under a different Postgres username. This is
# the "install identical schema on another server" artifact referenced by
# docs/server-migration-guide.md -- NOT a disaster-recovery backup (that's
# scripts/backup.sh, which includes real data and is gitignored on purpose).
#
# Run this after any migration lands (a new alembic/versions/*.py file),
# so docs/database-schema.sql never drifts from what Alembic actually builds.
# Usage: scripts/dump-schema.sh [dev|production]
set -euo pipefail

ENV="${1:-dev}"
COMPOSE_FILE="docker-compose.${ENV}.yml"
OUT_FILE="docs/database-schema.sql"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Unknown environment '$ENV' (expected dev or production)" >&2
  exit 1
fi

# shellcheck disable=SC1091
[ -f .env ] && source .env

echo "==> Dumping schema-only structure to $OUT_FILE"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-lial}" -d "${POSTGRES_DB:-lial_energy}" \
  --schema-only --no-owner --no-privileges > "$OUT_FILE"

echo "==> Done. Review the diff (git diff $OUT_FILE) before committing --"
echo "    a change here should always trace back to a specific migration."
