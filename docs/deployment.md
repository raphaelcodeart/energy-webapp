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

## Scripts

All real and in active use (not skeletons -- verified against a live server, see
`docs/server-migration-guide.md §8` for the actual bugs found running them):

- `scripts/deploy.sh` — pulls, builds, migrates, restarts with health-check gating.
- `scripts/backup.sh` — `pg_dump` (real data), gzipped, 14-day retention, writes to
  `./backups/`, gitignored on purpose — never commit these. Runs nightly via cron on
  the reference server (`server-migration-guide.md §4.8`). Does **not** sync the MinIO
  document buckets — see that section for the separate `mc mirror` procedure.
- `scripts/dump-schema.sh` — regenerates `docs/database-schema.sql`, a structure-only
  (no data) `pg_dump`, portable across servers. Run after any new Alembic migration so
  this stays in sync; it's the artifact `docs/server-migration-guide.md` points to for
  "what does the database actually look like."
- `scripts/restore.sh` — restores from a named backup, verifies checksum before restore.
- `scripts/health-check.sh` — curls health/readiness endpoints for api/dashboard, checks
  postgres/redis connectivity.
- `scripts/migrate.sh` — wraps `alembic upgrade head` with a pre-migration backup.
- `scripts/rollback.sh` — `alembic downgrade -1` with an explicit confirmation prompt.
- `scripts/renew-cert.sh` — renews the Let's Encrypt certificate(s); the certbot
  package's own systemd timer does NOT cover this project's non-default config
  directory, so this must be on cron (see `server-migration-guide.md §4.6`).

## Environments
`development` (this repo's default), `staging`, `production` — see `network-model.md`
for the topology differences. Production additionally requires: real S3-compatible
storage credentials, SMTP credentials (or leave unset and every email falls back to
being logged instead of delivered -- functional, just not delivered), TLS certificates
(Let's Encrypt via certbot, wired at the nginx layer, see
`server-migration-guide.md §4.6`), and real Stripe keys entered from the admin
dashboard if card payments are wanted (not an env var -- see below).

**Payments are real, not a mock**: Stripe (card) and bank transfer are both fully
implemented for product orders and the partner-invoice cashback redemption fee,
self-checkout included -- see `business-rules.md` and
`cashback-partner-invoices-plan.md`. There is no `MockPaymentProvider` in this
codebase; that term only appears in early planning documents describing a design
since superseded by the real Stripe integration. Card payments simply do nothing
(the button never renders) until a `SUPER_ADMIN` pastes real Stripe keys into
Impostazioni Azienda → Pagamenti; bank transfer needs only an IBAN in the same
settings screen.

## What is NOT yet production-ready (be explicit, don't overclaim)
CI/CD pipeline (no automated lint/test/build-on-push -- run them by hand, see
`README.md`), automated backup/restore verification, off-server backup copies
(today's backup stays on the same disk as the database), monitoring stack
(Prometheus/Grafana/Loki), MFA enforcement, antivirus scanning of uploaded
documents (pluggable interface exists, no scanner wired in), OCR on cashback-
redemption invoices, and the AI/pgvector layer (`docs/ai-architecture.md` is a
design document only, no code). See `implementation-progress.md` and
`server-migration-guide.md §9` for the full, currently-accurate list -- payments,
notifications (in-app and email), the internal wallet/cashback system, and contract
document uploads are all real and live, not on this list.
