# Lial Energy Platform

Gestionale completo per Lial Energy: sito/marketplace, rete commerciale
multilivello, contratti e forniture, motore provvigionale deterministico,
dashboard cliente/promoter/amministratore.

See `docs/` for the full documentation set — start with `docs/architecture.md` and
`docs/implementation-progress.md` (what's actually built vs. planned).

## Stack

- **Backend**: FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16, Celery + Redis
- **Frontend**: Next.js 16 (App Router), React 19, TypeScript strict, TanStack Query/Table, Tailwind CSS 4
- **Monorepo**: pnpm workspace (`apps/api`, `apps/dashboard`, `apps/worker`)

## Quickstart (Docker Compose)

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD, JWT_SECRET_KEY, MINIO_ROOT_USER/PASSWORD, S3_ACCESS_KEY/SECRET_KEY

docker compose -f docker-compose.dev.yml up --build
```

This starts Postgres, Redis, MinIO, the API (migrations run automatically on
startup), the Celery worker + beat, the dashboard, and nginx in front of
everything.

- App: http://localhost/ (via nginx) or http://localhost:3000 (dashboard directly)
- API docs (OpenAPI): http://localhost:8000/docs (or http://localhost/backend/docs
  through nginx — see `infrastructure/nginx/nginx.conf`'s comment on why this isn't
  `/api/docs`: the dashboard's own BFF routes already own `/api/*`)
- MinIO console: http://localhost:9001

Load demo data (20 promoters across 2 parallel branches / 6 levels deep, sample
customers, contracts in every state, generated commissions):

```bash
docker compose -f docker-compose.dev.yml exec api python -m app.seed
```

The seed script prints the demo organization ID and login credentials
(password `DemoPass123!` for all seeded users) — you need the organization ID to
log in via the dashboard's login form.

## Verifying the system

```bash
scripts/health-check.sh dev
```

or manually:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/readiness
```

Run the backend test suite (needs a Postgres reachable at `TEST_DATABASE_URL`):

```bash
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
TEST_DATABASE_URL=postgresql+psycopg://lial:<password>@localhost:5432/lial_energy_test python -m pytest
```

Run the frontend checks:

```bash
cd apps/dashboard
pnpm install
pnpm typecheck
pnpm lint
pnpm build
```

## Repository layout

```
/apps
  /api         FastAPI backend -- domains/, alembic/, tests/, seed/
  /dashboard   Next.js 16 App Router BFF + UI
  /worker      Shares apps/api's image (see apps/worker/README.md) -- no separate package
/infrastructure
  /nginx       Reverse proxy config
/scripts       deploy / backup / restore / health-check / migrate / rollback
/docs          Architecture, data model, business rules, ADRs, security model, ...
```

## What's implemented vs. planned

This is a vertical slice through Phases A–E of the implementation plan (analysis,
foundations, commercial network, commercial domain, commissions), not the full
36-section specification. See `docs/implementation-progress.md` for the exact,
continuously-updated checklist and `docs/open-questions.md` for every business-rule
placeholder awaiting the real Lial Energy commission/career-plan document.
