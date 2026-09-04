# Deployment

## Local development

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Then:
- Dashboard: http://localhost:3000
- API docs (OpenAPI): http://localhost:8000/docs
- MinIO console: http://localhost:9001

## Migrations

```bash
docker compose -f docker-compose.dev.yml exec api alembic upgrade head
```

or via helper script: `scripts/migrate.sh`

## Seed demo data

```bash
docker compose -f docker-compose.dev.yml exec api python -m app.seed
```

## Scripts (Phase H hardens these; skeletons exist now)

- `scripts/deploy.sh` — pulls, builds, migrates, restarts with health-check gating.
- `scripts/backup.sh` — pg_dump (real data) + document bucket sync to off-server storage.
  Writes to `./backups/`, gitignored on purpose — never commit these.
- `scripts/dump-schema.sh` — regenerates `docs/database-schema.sql`, a structure-only
  (no data) `pg_dump`, portable across servers. Run after any new Alembic migration so
  this stays in sync; it's the artifact `docs/server-migration-guide.md` points to for
  "what does the database actually look like."
- `scripts/restore.sh` — restores from a named backup, verifies checksum before restore.
- `scripts/health-check.sh` — curls health/readiness endpoints for api/dashboard, checks
  postgres/redis connectivity.
- `scripts/migrate.sh` — wraps `alembic upgrade head` with a pre-migration backup.
- `scripts/rollback.sh` — `alembic downgrade -1` with an explicit confirmation prompt.

## Environments
`development` (this repo's default), `staging`, `production` — see `network-model.md`
for the topology differences. Production additionally requires: real S3-compatible
storage credentials, SMTP or transactional email provider credentials, a real payment
provider adapter (Phase D ships only `MockPaymentProvider`), and TLS certificates
(Let's Encrypt via certbot, wired at the nginx layer).

## What is NOT yet production-ready (be explicit, don't overclaim)
CI/CD pipeline, automated backup/restore verification, monitoring stack
(Prometheus/Grafana/Loki), MFA enforcement, real payment provider, AI layer — all
Phase G/H work, tracked in `implementation-progress.md`.
