# Implementation Progress

Updated at the end of each work session. This is the authoritative "what's actually
done vs. planned" record — `architecture.md` describes the target, this file describes
reality.

## Session 1 — 2026-07-25

### Phase A — Analysis & documentation ✅
- [x] Repository analysis (repo was empty — greenfield build, no existing stack,
      no `Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf`)
- [x] `docs/architecture.md`, `docs/database-model.md` (+ ER diagram),
      `docs/business-rules.md`, `docs/commission-engine-specification.md`,
      `docs/open-questions.md`, `docs/security-model.md`, `docs/network-model.md`,
      `docs/ai-architecture.md` (design only), `docs/deployment.md`,
      `docs/adr/0001..0005`

### Phase B/C/D/E — Vertical slice ✅ (verified working end-to-end)

**Monorepo & infra**
- [x] pnpm workspace (`apps/api`, `apps/dashboard`; `apps/worker` shares the api image)
- [x] `docker-compose.dev.yml` (postgres, redis, minio, api, celery-worker,
      celery-beat, dashboard, nginx) — actually run with `docker compose up --build`
      on the target server (Docker installed this session); all 8 containers
      healthy, demo data seeded, full login flow verified through the public
      nginx entrypoint. Three real bugs found and fixed in the process (see below).
- [x] `docker-compose.production.yml`, multi-stage `Dockerfile`s (non-root users,
      healthchecks) for api and dashboard
- [x] `.env.example`, `.gitignore`, `scripts/{deploy,backup,restore,health-check,migrate,rollback}.sh`

**Backend (FastAPI, verified against a real local Postgres 18 instance)**
- [x] `auth`: Argon2id hashing, JWT access tokens, rotating refresh tokens in a
      `sessions` table, single/all-session revocation, account lockout, identical
      error message for unknown-email vs wrong-password (enumeration mitigation)
- [x] `organizations`, `users`, `rbac` (roles/permissions/ABAC-ready), `audit`
      (append-only)
- [x] `network`: `agent_profiles`, `network_nodes`, `network_edges`,
      `network_closure` (with reflexive rows + composite indexes),
      `network_assignment_history`, `network_snapshots`/`network_snapshot_nodes`;
      transactional `move_agent()` (cycle prevention, whole-subtree relocation,
      closure table maintenance) and `create_snapshot_for_contract()`
- [x] `referral`: promoter codes, referral events/sessions (hashed cookie tokens),
      customer attribution
- [x] `catalog`, `customers`, `contracts`: explicit state machine
      (`state_machine.py`, `assert_transition_allowed`), status history, ownership
      link (`customers.user_id`) for customer self-service
- [x] `outbox`: transactional outbox table + dispatcher (ADR 0005) — commission
      calculation triggers only on `ContractActivated`/`ContractRenewed`, never on
      creation/submission
- [x] `commissions`: pure-function calculator (`calculators/entrepreneurial_difference.py`),
      isolated 33%-rule policy (`policies/branch_cap.py`), orchestration service with
      idempotency (`(contract_id, trigger_event_id)` + unique `idempotency_key`),
      append-only `commission_movements` ledger, read-only simulator
- [x] Ownership-scoped endpoints: `GET /contracts/mine` (customer), `GET /network/mine`
      + `GET /network/agents/{id}/branch` (promoter, ABAC-checked against the
      closure table), `GET /commissions/mine`
- [x] Celery app (`app/celery_app.py`) reusing the same domain code; beat schedule
      polls the outbox every minute

**Database**
- [x] Alembic migration `0001_initial_schema` — 43 tables, generated via
      autogenerate and applied cleanly to a real Postgres instance
- [x] Fixed a real bug found during verification: bare `datetime` columns defaulted
      to naive `TIMESTAMP` (no `timezone=True`), causing
      `can't compare offset-naive and offset-aware datetimes` the first time a
      loaded value was compared against `utcnow()`. Fixed at the `Base` level via
      `type_annotation_map`.
- [x] Fixed a real bug: `network_nodes` had a hard unique constraint on
      `(organization_id, agent_id)`, which made a second (historical) row for the
      same agent impossible — broke every `move_agent()` call. Replaced with a
      partial unique index (`WHERE effective_to IS NULL`).

**Docker Compose — actually run on the target server, 4 more real bugs found and fixed**
- [x] `apps/dashboard/Dockerfile` created a group/user at gid/uid 1000, but
      `node:22-slim` already ships a `node` user at that exact id → build failure.
      Fixed by reusing the image's own `node` user instead of creating one.
- [x] Corepack fetched pnpm `latest` (11.x) inside the build, whose stricter
      default blocks native postinstall scripts (`sharp`, `unrs-resolver`) unless
      explicitly approved → build failure. Fixed by pinning
      `"packageManager": "pnpm@9.15.9"` in the root `package.json` so the container
      uses the exact version the lockfile was generated with.
- [x] `apps/dashboard/public/` didn't exist (never created) → `COPY` in the
      Dockerfile failed. Created an (empty, `.gitkeep`) directory.
- [x] `celery-beat` tried to write `celerybeat-schedule` into `/app`, which is
      root-owned (only files explicitly `COPY --chown`'d are not) → permission
      denied, crash loop. Fixed by pointing `--schedule` at `/tmp`.
- [x] `celery-worker`/`celery-beat` inherited the api image's `HEALTHCHECK`
      (`curl localhost:8000/health`), which is meaningless for a process with no
      HTTP server → both reported "unhealthy" even though they worked fine. Fixed
      with a real `celery inspect ping` check for the worker and `disable: true`
      for beat.
- [x] The dashboard's Next.js standalone `server.js` was binding to the
      container's own interface IP instead of the wildcard address, so anything
      probing `localhost:3000` from inside the same container (the healthcheck)
      got `ECONNREFUSED` even though the app was reachable fine from other
      containers via the `dashboard` service name. Fixed by setting `HOSTNAME=0.0.0.0`.
- [x] **The most consequential one**: nginx's `location /api/` forwarded straight
      to FastAPI, silently swallowing the dashboard's own BFF routes at
      `/api/auth/login` and `/api/proxy/*` — login appeared to "work" (no error)
      but never actually went through the BFF, so no session cookie was ever set
      and every protected page redirected back to `/login`. Fixed by moving direct
      backend access to `/backend/` and leaving `/api/*` exclusively to the
      dashboard, matching the BFF pattern the architecture actually calls for.

**Seed data** (`python -m app.seed`)
- [x] 1 organization, 7 demo logins (`SUPER_ADMIN`, `ADMIN`, `BACK_OFFICE_OPERATOR`,
      `ACCOUNTING_OPERATOR`, `SALES_MANAGER`, plus a real `PROMOTER` login linked to
      agent `MD5-ROSSI` and a real `CUSTOMER` login linked to a seeded customer, so
      every dashboard is actually logins-testable, not just role-labeled)
- [x] 20 agents, 2 parallel top-level branches, 6 levels deep in Branch A —
      demonstrates branch isolation (a promoter cannot read the parallel branch)
- [x] Ranks S1–S3/TL1–4/MD1–5 (placeholder figures, see `open-questions.md`)
- [x] 3 products (luce, gas, Energia Circolare/PMI), customers of 3 kinds, contracts
      in ACTIVE / DRAFT / REJECTED / CANCELLED states
- [x] Commission ledger populated by the real engine — verified by hand: chain
      `S1(4000)→S2(+500)→S3(+500)→TL2(+1000)→TL4(+1000)→MD5(+2500)` sums correctly
      to the top rank's token, no duplicated differential

**Tests** (26 passing — pure-function + Postgres-integration, see test list below)
- [x] `apps/api/app/domains/commissions/tests/test_entrepreneurial_difference.py` —
      producer-only, single/multiple ascendants, equal/lower rank ⇒ zero,
      full S→MD chain sums correctly, empty chain
- [x] `apps/api/app/domains/commissions/tests/test_branch_cap.py` — under/at/over the
      33% cap, multiple branches, zero production, no branches
- [x] `apps/api/tests/test_auth.py` — login success, enumeration-safe failure,
      lockout after N attempts, refresh token rotation/revocation
- [x] `apps/api/tests/test_network_isolation.py` — parallel-branch isolation, closure
      depth correctness, move-agent cycle prevention, whole-subtree relocation,
      multi-tenant isolation
- [x] `apps/api/tests/test_commission_engine_integration.py` — activation generates
      the expected movements, re-processing the outbox never duplicates them,
      calculations are organization-scoped

**Frontend (Next.js 16, verified with real installs/builds)**
- [x] BFF pattern: HttpOnly/Secure/SameSite=Lax session cookie holding the API
      access+refresh tokens; browser never sees either token
- [x] `proxy.ts` (Next 16's post-middleware convention) gates `/customer`,
      `/promoter`, `/admin` behind session presence; backend still re-checks
      authorization regardless (frontend is never the security boundary)
- [x] Login page, 3 role dashboards (customer: own contracts; promoter: own agent
      profile + branch table via TanStack Table + own commissions via TanStack
      Query against a same-origin proxy route; admin: org-wide contracts +
      status breakdown)
- [x] `pnpm typecheck`, `pnpm lint`, `pnpm build` all pass with zero errors

### Verification method (be explicit about what was and wasn't run)
This machine is the actual target server (a Hetzner VM, public IP
`46.225.127.164`), not a disposable sandbox. Verification happened in two passes:

1. **Host-level**, before Docker was installed: `postgresql`, `nodejs`/`npm`/`pnpm`
   installed directly; backend migrated/seeded/tested against a real local
   Postgres; frontend installed/typechecked/linted/built with real `next build`;
   both servers driven directly (`uvicorn`, `next dev`) via `curl` through the
   actual BFF login flow.
2. **Full Docker Compose**, once Docker was installed at the user's request:
   `docker compose -f docker-compose.dev.yml up --build` — all 8 containers
   (postgres, redis, minio, api, celery-worker, celery-beat, dashboard, nginx)
   came up healthy after fixing the 6 bugs listed above. Demo data was seeded
   into the running stack (`docker compose exec api python -m app.seed`), and the
   full login → session cookie → protected dashboard flow was verified through
   the **public IP** (`http://46.225.127.164/`), not just localhost — including
   confirming unauthenticated requests to `/admin` still redirect to `/login`
   when hit from outside the server.

**Caveat**: this is HTTP only (no TLS/certbot wired yet, Phase H), and the current
`.env` was generated with strong random secrets but the running stack still uses
**seed/demo data** — do not treat this as production-ready as-is. See "Next
recommended session" for the concrete gap list before this should be treated as
more than a live demo.

### Explicitly NOT in this session's scope (tracked for later phases)
- Payments beyond the `PaymentProvider` interface (no `MockPaymentProvider` class
  yet — the contract state machine supports the states, but there's no payment
  webhook handler in this slice)
- Document upload/storage (MinIO is wired in Docker Compose; no `documents` domain
  code yet)
- Notifications (Celery beat + outbox infra exists; no notification templates/tasks)
- Reporting/CSV export, reversals/renewals calculators (Energia Circolare bonus,
  reversal proration -- extension points documented, not implemented)
- AI/pgvector (design doc only, `docs/ai-architecture.md`)
- CI/CD pipeline, automated backup retention/off-server copy, monitoring stack
  (Prometheus/Grafana/Loki), MFA enforcement, full GDPR tooling
- Rest of the Hypothesis property-based test matrix from
  `commission-engine-specification.md`

### Known risks / assumptions
See `docs/open-questions.md`: rank thresholds, network move self-approval, Energia
Circolare formula, reversal proration formula, GDPR retention, 33% cap denominator,
MFA/lockout policy — all placeholders pending the real business-rules document.

### Next recommended session
1. If a real domain will point at this server: add a DNS A record to
   `46.225.127.164`, set `server_name` in `infrastructure/nginx/nginx.conf`
   accordingly, and wire certbot/Let's Encrypt for TLS (currently HTTP only).
2. Decide whether this server should keep running the demo/seed stack publicly or
   be reset before real customer data ever touches it — seed data and demo
   credentials (`DemoPass123!` for every seeded user) are live on the public IP
   right now.
3. Phase F: notifications (Celery tasks + templates) and a minimal reports domain.
4. Phase D hardening: `documents` domain (MinIO upload/download with signed URLs)
   and a real `PaymentProvider` + `MockPaymentProvider`.
5. Wire CI (lint/typecheck/test/build) once there's a git remote to attach it to.
