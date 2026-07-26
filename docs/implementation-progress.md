# Implementation Progress

Updated at the end of each work session. This is the authoritative "what's actually
done vs. planned" record — `architecture.md` describes the target, this file describes
reality.

## Session 6 — 2026-07-26 — Admin dashboard expansion, Fase 2: summary dashboard

The user requested a full enterprise admin/promoter management overhaul (contracts,
promoters, commission network, settlements, audit log, public marketplace, etc.) --
scoped and sequenced into `docs/admin-dashboard-plan.md` (written and committed
first, per the user's own requested process: plan → implement one phase at a time →
verify before continuing). This session completed **Fase 2 — Dashboard riepilogativa**
only; Fasi 3-10 remain planned, tracked in that document's status table.

**Backend — new `reports` domain, read-only aggregations over existing tables:**
- [x] `GET /reports/dashboard-summary?period_from=&period_to=` -- contract counts
  by status (total/active/pending-approval/rejected/cancelled/suspended/expired,
  mapped from the real `state_machine.py` status set, not guessed), commission
  totals by status (accrued/payable/paid/reversed, summed in cents), active
  promoter and active-customer counts, period-scoped new-contracts and
  new-commissions figures. Defaults to the last 30 days if no range is given.
- [x] `GET /reports/attention-items` -- contracts sitting in a review-queue status
  (`SUBMITTED`/`DOCUMENTS_PENDING`/`UNDER_REVIEW`) for more than 7 days. Contracts
  have no `updated_at` column by design (state changes are append-only history,
  see `contract_status_history`), so "time in current status" is derived from
  that contract's latest status-history row via a window function, not a
  denormalized timestamp on the contract itself.
- [x] `GET /reports/recent-activity?limit=` -- last N rows from the existing
  append-only `audit_log`, no new table.
- [x] `GET /reports/contracts-timeseries?months=` and
  `GET /reports/commissions-timeseries?months=` -- monthly counts/sums for the
  last N months (zero-filled for months with no activity), source data for the
  new frontend charts.
- [x] New `reports.read` permission (distinct from the pre-existing
  `reports.export`), granted to SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN/
  ACCOUNTING_OPERATOR/SALES_MANAGER/AUDITOR in `rbac/models.py` **and** patched
  directly into the live `permissions`/`role_permissions` tables (seeded data,
  same pattern as Session 5's new permissions) -- confirmed with a live 403 test
  using the CUSTOMER-role demo account before touching the frontend.
- [x] No new tables. Everything reads existing `contracts`, `commission_movements`,
  `agent_profiles`, `customers`, `audit_log`, `contract_status_history`.

**Frontend:**
- [x] `AdminOverviewPanel` -- new default landing tab ("Panoramica") in the admin
  sidebar: 8 KPI cards (contracts total/active/pending/rejected, commissions
  accrued/paid, active promoters, active customers), a time-range filter
  (oggi/7gg/mese/trimestre/anno) that re-queries `dashboard-summary` with the
  matching date range, two Recharts charts (12-month contract volume area chart,
  12-month commission value bar chart), an "richiede attenzione" list and a
  recent-activity feed. Built with `useQuery` from the start (the pattern Session
  5 had to retrofit into three panels after hitting React's `set-state-in-effect`
  lint rule).
- [x] `recharts` added as a dependency (first use in this codebase; MinIO and
  Recharts were the two dependencies flagged as not-yet-installed in the plan doc).

**Honest data note:** "Provvigioni pagate" (paid_cents) legitimately reads 0 today
-- the commission engine only ever writes `ACCRUED` movements right now; the
`PAYABLE`/`PAID` lifecycle transitions are Fase 7 (Liquidazioni/Pagamenti), not yet
built. This is real current behavior, not a placeholder.

Verified end-to-end: curl against the live API with a real JWT (dashboard-summary,
both timeseries endpoints, attention-items, recent-activity all returned correct
data derived from the actual seeded database), a live 403 confirming RBAC is
enforced server-side, then the full browser path (login → BFF session cookie →
`/api/proxy/reports/*` → FastAPI) over the real HTTPS domain. `tsc --noEmit`,
`eslint`, and `next build` all clean before the image rebuild/redeploy.

## Session 5 — 2026-07-26 — Admin CRUD (customers/promoters/products), recruiting, top bar

The user asked for: a persistent top bar with a corner icon cluster (day/night
toggle moved there, "classic dashboard" style); full admin management of customer
records, promoter/agent records, and marketplace products; promoters managing
their own network and enrolling their own recruits; and confirmation the network
view supports the full 12-level career-plan depth.

**Backend — three new CRUD surfaces, all org-scoped and RBAC-gated:**
- [x] `customers` domain gained a real `service.py`/`router.py` (previously only
  `models.py` existed, used internally by `contracts`): list/get/create/update,
  plus `POST /customers/{id}/supply-points` since a customer isn't usable in a
  contract without one. `PRIVATE`/`SOLE_PROPRIETOR` create a `CustomerProfile`,
  `COMPANY`/`CONDOMINIUM` create a `Company`, in the same transaction as the `Customer`.
- [x] `network` domain gained org-wide agent management: `GET/POST /network/agents`,
  `PATCH /network/agents/{id}` (rank changes write `AgentRankHistory`, matching
  the existing manual-qualification-change pattern), gated by `network.manage`
  (admin-level, org-wide) -- deliberately separate from the already-existing
  branch-scoped `network.read_branch`.
- [x] `POST /network/agents/recruit` -- lets a promoter enroll a new *direct*
  collaborator under themselves specifically (parent is resolved server-side from
  the caller's own agent, never client-supplied), gated by a new `network.recruit`
  permission distinct from `network.manage` so a promoter can grow their own
  branch without being able to place agents anywhere else in the tree.
- [x] `catalog` domain gained `service.py`/`router.py`: product+first-version
  created together (a product with zero versions can't be sold), later versions
  only ever added (never mutate a version live contracts already point to,
  per `docs/business-rules.md`), `products.read`/`products.manage` permissions.
- [x] `GET /commissions/ranks` -- reference data (the 12-rank ladder, S1-S3/TL1-4/MD1-5)
  needed by the new agent-creation forms and already used by the simulator;
  gated by authentication only, not a specific permission (harmless read).
- [x] RBAC: 3 new permission codes (`network.recruit`, `products.read`,
  `products.manage`), granted per role in `rbac/models.py` **and** patched
  directly into the running database's `role_permissions` table (seeded data,
  not a schema migration) so the existing deployment didn't need a full reseed.
- [x] All 26 existing tests still pass; new endpoints smoke-tested live over
  HTTPS (create customer/product, admin agent list, promoter recruit landing at
  depth 1, ranks list returning exactly 12 rows) before touching the frontend.

**Frontend:**
- [x] `AppShell` restructured: a persistent top bar (not just the old mobile-only
  one) now spans every screen size, sitting to the right of the desktop sidebar.
  Page title on the left, theme toggle + an avatar button (opens a small
  email/role/logout menu, click-outside-to-close) in the top-right corner --
  "classic dashboard" layout. The sidebar footer lost the theme toggle and user
  card it used to carry (moved to the top bar) and now just shows the role label.
- [x] Three new admin sidebar sections, each a self-contained panel component:
  `AdminCustomersPanel` (search, table, create modal with kind-conditional
  fields), `AdminPromotersPanel` (table showing rank/sponsor/status resolved
  from the agent list, create modal with a parent-agent and rank dropdown),
  `AdminProductsPanel` (card grid, create modal with EUR-to-cents conversion).
- [x] `RecruitForm` -- a promoter-facing "+ Aggiungi Collaboratore" button in the
  Rete Commerciale tab, calling the scoped recruit endpoint; triggers
  `router.refresh()` on success so the branch view (a server-fetched prop)
  updates without a full reload.
- [x] Confirmed (by reading the code, not assuming) that `BranchVisualizer` and
  `BranchTable` have no hardcoded depth cap -- the closure table and the UI both
  already support arbitrary depth, so "12 livelli" was a labeling/badge
  addition (`Profondità massima: N / 12 livelli`), not a new capability to build.

**Bugs found and fixed while building this:**
- [x] All three new admin panels originally fetched data with a raw
  `useEffect(() => { loadX() }, [])` -- React's newer lint rules correctly flag
  calling `setState` (even indirectly, through an async function) inside a plain
  effect. Refactored to `useQuery`/`useQueryClient` (already the established
  pattern in this codebase via `my-commissions.tsx`), which is both lint-clean
  and gives free caching/invalidation instead of manual refetch plumbing.

Verified end-to-end over the live HTTPS deployment after rebuilding both the
`api`/`celery-*` and `dashboard` images: all three new admin sections render
with live data, the promoter recruit flow adds a real depth-1 descendant, and
the top-bar theme toggle/avatar menu are present in the rendered HTML.

## Session 4 — 2026-07-26 — App shell, sidebar navigation, light/dark theme

The user pulled a redesign from GitHub (glassmorphism UI, admin contract
management, promoter network visualizer + commission simulator) and asked to
run it, then asked for a further redesign: a persistent left sidebar
("strumento di lavoro moderno") and a working light/dark toggle.

- [x] `lib/theme.tsx` — `ThemeProvider` + `useTheme()`, persisted to
  `localStorage`, defaults to system `prefers-color-scheme` on first visit. An
  inline script (`themeInitScript`, injected in `app/layout.tsx`'s `<head>`
  before hydration) sets `data-theme` on `<html>` pre-paint to avoid a flash of
  the wrong theme.
- [x] `app/globals.css`: added `@custom-variant light` (Tailwind v4) so `light:`
  prefixed classes apply only under `[data-theme="light"]` — dark stays the
  unprefixed default, matching the existing design's starting point. `.glass-card`
  / `.glass-input` and all core CSS variables now flip via this attribute.
- [x] `components/theme-toggle.tsx` — sun/moon switch, in the sidebar and on
  the login page.
- [x] `components/app-shell.tsx` — the actual "sidebar with everything": fixed
  desktop sidebar / mobile drawer, logo, role-scoped nav items, user card +
  theme toggle + logout at the bottom. Replaces each dashboard's old sticky
  header + horizontal tab bar; the existing tab sections (promoter:
  Rete/Provvigioni/Simulatore, admin: Contratti/Nuovo, customer:
  Contratti/Supporto) became sidebar nav items 1:1 -- no new fake nav items
  invented for sections that don't exist yet.
- [x] Applied the light theme across every existing component (~2000 lines):
  ran an automated pass (regex substitution with strict word-boundary
  matching, not naive sed) to append `light:` variants to every hardcoded dark
  Tailwind class, then manually reviewed and fixed ~9 false positives it
  introduced -- cases like button text sitting on a *solid* colored badge
  (e.g. `bg-violet-600`), which must stay white in both themes and should
  never have gotten a `light:text-slate-900` override.
- [x] Hoisted `QueryProvider` to the root layout (was being remounted, and its
  cache lost, every time a dashboard's internal tab changed).
- [x] Fixed a real, live RBAC bug surfaced by the new promoter-facing
  simulator tab: `PROMOTER` had no `commissions.simulate` permission, so the
  new UI 403'd. Added it (read-only, never touches the ledger) to
  `rbac/models.py` and to the running database's `role_permissions` table
  directly (seeded data, not a schema migration).
- [x] Fixed 3 real lint/correctness issues surfaced by `eslint`'s
  React Compiler rules while rebuilding: unescaped apostrophes/quotes in JSX
  text (`react/no-unescaped-entities`), `Math.random()` called during render
  in the customer support-ticket confirmation (moved into the submit handler
  so the ticket number is stable instead of changing on every re-render), and
  a justified (commented, suppressed) exception for syncing theme state from
  a pre-hydration DOM attribute in a `useEffect`.
- [x] Verified end-to-end over the live HTTPS URL after rebuilding both the
  `dashboard` and `api`/`celery-*` images: login, sidebar navigation and theme
  attribute present in all three dashboards, and the promoter's commission
  simulator returning real 200 results post-fix.

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
1. ~~Wire HTTPS~~ — done in Session 3, see below. If a *permanent* domain
   replaces the temporary Hetzner rDNS hostname, redo the certbot procedure in
   `docs/server-migration-guide.md` §4.6 for the new name.
2. Decide whether this server should keep running the demo/seed stack publicly or
   be reset before real customer data ever touches it — seed data and demo
   credentials (`DemoPass123!` for every seeded user) are live on the public
   internet right now.
3. Phase F: notifications (Celery tasks + templates) and a minimal reports domain.
4. Phase D hardening: `documents` domain (MinIO upload/download with signed URLs)
   and a real `PaymentProvider` + `MockPaymentProvider`.
5. Wire CI (lint/typecheck/test/build) — the repo now has a remote
   (`github.com/raphaelcodeart/energy-webapp`, branch `main`), so this is unblocked.

## Session 3 — 2026-07-25 (same day, continued) — HTTPS wired

The user tried logging in over plain HTTP and hit exactly the security behavior
`docs/security-model.md` describes: the browser silently discards the `Secure`
session cookie on a non-HTTPS connection, so login looked like it did nothing
(no visible error, page just reloads to `/login`). The correct fix was never to
weaken the cookie — it was to actually wire the TLS termination this project had
deferred to "Phase H".

- [x] Real Let's Encrypt certificate issued for the server's temporary Hetzner
  rDNS hostname (`static.164.127.225.46.clients.your-server.de`), via certbot in
  webroot mode, non-standard config dir (`./certbot/`, not `/etc/letsencrypt`)
  so it lives alongside the project rather than in host-global state.
- [x] `infrastructure/nginx/nginx.conf`: HTTP (80) now serves only the ACME
  challenge and 301-redirects everything else to HTTPS; HTTPS (443) terminates
  TLS and proxies exactly as before (`/backend/` → API, everything else →
  dashboard).
- [x] `docker-compose.dev.yml`: nginx now publishes 443, mounts
  `./certbot/conf` (read-only) and `./certbot/www` (read-only, ACME challenge
  webroot).
- [x] `scripts/renew-cert.sh` + a crontab entry (daily at 03:00) — **the
  certbot package's own systemd renewal timer does NOT cover this certificate**
  because it uses a non-default config directory; without this script, the
  cert would silently expire in 90 days.
- [x] `.env`'s `NEXT_PUBLIC_APP_URL` updated to the `https://` hostname.
- [x] `certbot/` added to `.gitignore` — it holds private keys, must never be committed.
- [x] Verified end-to-end over the real HTTPS URL: HTTP→HTTPS redirect, real
  cert served (not self-signed), login issues a cookie the browser will
  actually keep, and the admin dashboard renders live data through it.

Two more real bugs found and fixed while wiring this (bringing the running
total to 9 — see `docs/server-migration-guide.md` §8 for the full list with
symptoms, so they're recognized immediately if hit again on a future server):
- Certbot refuses to issue a certificate into a `live/<domain>` directory that
  already exists (even if it's just a manually-placed bootstrap/dummy cert) —
  has to be removed first.
- A Docker bind mount established before a host directory is `rm -rf`'d and
  recreated stays attached to the old (now-orphaned) inode; the container sees
  an empty directory even though the host has fresh files. `nginx -s reload`
  doesn't fix this — the container itself must be recreated.

## Session 2 — 2026-07-25 (same day, continued)

- [x] Pushed the full repository to `git@github.com:raphaelcodeart/energy-webapp.git`
  (branch `main`), via a dedicated deploy-key SSH identity generated on this server.
- [x] `docs/server-migration-guide.md` — step-by-step server rebuild/migration
  runbook: prerequisites, `.env` generation, data migration from an existing
  server (`scripts/backup.sh` output restored into a fresh Postgres), domain/TLS
  setup, a code map, and the full list of the 7 real deployment bugs found in
  Session 1 (so they're not rediscovered from scratch on a new server).
- [x] `docs/database-schema.sql` — ground-truth schema dump (`pg_dump
  --schema-only`) of the actual running database, 43 tables, generated from the
  live stack rather than hand-written. `docs/database-model.md` now points to it
  explicitly as the authority in case of drift.
- [x] `docs/user-guide.md` (Italian) — end-user guide for the three dashboards as
  they exist today, written to match actual behavior rather than aspirational
  scope (explicitly lists what each dashboard does *not* yet do).
