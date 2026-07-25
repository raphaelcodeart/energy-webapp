#!/usr/bin/env bash
# Checks health/readiness of every service. Usage: scripts/health-check.sh [dev|production]
set -euo pipefail

ENV="${1:-dev}"
COMPOSE_FILE="docker-compose.${ENV}.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Unknown environment '$ENV' (expected dev or production)" >&2
  exit 1
fi

FAILED=0

check() {
  local name="$1" cmd="$2"
  if eval "$cmd" > /dev/null 2>&1; then
    echo "OK   $name"
  else
    echo "FAIL $name"
    FAILED=1
  fi
}

check "api /health"       "docker compose -f $COMPOSE_FILE exec -T api curl -sf http://localhost:8000/health"
check "api /readiness"    "docker compose -f $COMPOSE_FILE exec -T api curl -sf http://localhost:8000/readiness"
check "postgres"          "docker compose -f $COMPOSE_FILE exec -T postgres pg_isready -U \${POSTGRES_USER:-lial}"
check "redis"             "docker compose -f $COMPOSE_FILE exec -T redis redis-cli ping"

if [ "$FAILED" -ne 0 ]; then
  echo "One or more health checks failed."
  exit 1
fi
echo "All health checks passed."
