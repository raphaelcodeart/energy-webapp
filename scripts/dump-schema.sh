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
# Usage: scripts/dump-schema.sh [dev|production] [--from-migrations]
#
# --from-migrations (Session 68): instead of the running database, builds a
# throwaway empty database with `alembic upgrade head` inside the api image
# (the code you have checked out, even if not deployed yet) and dumps that --
# the exact structure a brand-new server gets. The throwaway DB is dropped.
set -euo pipefail

ENV="${1:-dev}"
FROM_MIGRATIONS="${2:-}"
COMPOSE_FILE="docker-compose.${ENV}.yml"
OUT_FILE="docs/database-schema.sql"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Unknown environment '$ENV' (expected dev or production)" >&2
  exit 1
fi

# shellcheck disable=SC1091
[ -f .env ] && source .env

DB_NAME="${POSTGRES_DB:-lial_energy}"
if [ "$FROM_MIGRATIONS" = "--from-migrations" ]; then
  DB_NAME="lial_energy_schema_template"
  echo "==> Building $DB_NAME from the migrations"
  docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U "${POSTGRES_USER:-lial}" -d postgres \
    -c "DROP DATABASE IF EXISTS $DB_NAME" -c "CREATE DATABASE $DB_NAME"
  docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
    -e DATABASE_URL="postgresql+psycopg://${POSTGRES_USER:-lial}:${POSTGRES_PASSWORD}@postgres:5432/$DB_NAME" \
    api alembic upgrade head
fi

echo "==> Dumping schema-only structure of $DB_NAME to $OUT_FILE"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-lial}" -d "$DB_NAME" \
  --schema-only --no-owner --no-privileges > "$OUT_FILE"

if [ "$FROM_MIGRATIONS" = "--from-migrations" ]; then
  docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U "${POSTGRES_USER:-lial}" -d postgres \
    -c "DROP DATABASE $DB_NAME"
fi

echo "==> Done. Review the diff (git diff $OUT_FILE) before committing --"
echo "    a change here should always trace back to a specific migration."
