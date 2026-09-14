# Lial Energy Platform — Architecture

Status: Living document. Updated at the end of every implementation phase (see `implementation-progress.md`).

## 1. Context

Lial Energy is building a management platform for an energy reseller business: public
marketing site + marketplace, electricity/gas offers and subscriptions, a multilevel
commercial network of promoters/collaborators, contract lifecycle management, document
storage, payments, a multilevel commission engine, dashboards for customers/promoters/
admins, reporting, notifications, full audit, and AI-assisted document search.

The repository was empty at the start of this effort (no existing stack, no
`docs/Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf`). This is therefore a
greenfield build. Every commission/career-plan rule that would normally come from that
document is treated as **configurable and provisional** until the real document is
supplied — see `open-questions.md`.

## 2. Style: modular monolith, not microservices

One deployable backend (FastAPI) with clearly separated domain packages, one deployable
frontend (Next.js BFF), one worker (Celery) that imports the backend's domain code
directly rather than re-implementing it. Microservices are explicitly rejected for v1:
the commission engine must have exactly one authoritative implementation, and splitting
it across network-separated services would risk divergent logic and would add
operational cost (service discovery, distributed tracing, inter-service auth) with no
present benefit. This can be revisited if/when a specific bounded context needs
independent scaling or independent deploy cadence — see `adr/0001-modular-monolith.md`.

```
Browser
   │
   ▼
Next.js BFF (apps/dashboard)  ── same-origin cookie session, proxies to API
   │
   ▼
FastAPI (apps/api)
   │
   ▼
PostgreSQL 16+ ── relational data, commercial network, commission ledger, audit,
   │              full-text search, pgvector (AI, Phase G)
   ▼
Celery + Redis (apps/worker) ── async jobs: notifications, document processing,
   │                             commission batch runs, embeddings
   ▼
S3-compatible storage (MinIO in dev) ── documents
```

## 3. Domain boundaries (module map)

Each of these is a Python package under `apps/api/app/domains/<name>/` with its own
`models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`, `tests/`. Domains
depend on each other only through service-layer calls, never by reaching into another
domain's ORM internals directly from a router.

| Domain | Responsibility | Phase |
|---|---|---|
| `auth` | login, sessions, tokens, password reset, email verification | B |
| `users` | user accounts, profile | B |
| `organizations` | tenants, org membership | B |
| `rbac` | roles, permissions, policy evaluation (RBAC+ABAC) | B |
| `audit` | append-only audit log | B |
| `storage` | document upload/download, S3 client wrapper | B (stub), D (full) |
| `network` | agent nodes, edges, closure table, snapshots, moves | C |
| `referral` | promoter codes, referral events/sessions, attribution | C |
| `customers` | customer profiles, companies, addresses | D |
| `catalog` | products, product versions, pricing. **`pricing.py` is the single place VAT, who-may-buy-what, and where-a-LialCash-credit-comes-from are decided** — every money figure in the app derives from it, server-side only (see `business-rules.md#contract-economics`) | D |
| `imported_products` | the "Acquisti LialEnergy" plugin: a deliberately PARALLEL catalog + order table for externally-imported (dropshipping API) products, so they never mix with the hand-curated ones. Merged with `orders` only at the presentation layer (see `database-model.md §15`) | D (built) |
| `supply_points` | POD/PDR | D |
| `contracts` | contract state machine, events | D |
| `documents` | document metadata, versions, permissions | D |
| `payments` | Stripe checkout-session creation (orders, imported orders, invoice redemptions) + the per-organization webhook. Contract payment (unico / abbonamento 12 mesi / Klarna) is **not built yet** — see `server-migration-guide.md §9` | D |
| `ranks` | qualifications / career plan, versioned thresholds | E |
| `commissions` | plan versions, calculators, ledger, simulator | E |
| `renewals` / `reversals` | renewal & storno events | E |
| `notifications` | in-app notifications (approvals, rank changes, tickets) | E (built) |
| `documentation` | admin-authored news/training posts for customers & promoters | E (built) |
| `wallets` | internal EUR wallet per user, admin cashback, peer transfers | E (built) |
| `reports` | aggregate reporting endpoints | F |
| `ai` | pgvector ingestion, hybrid search, assistant | G |

## 4. Request flow & security boundary

The Next.js app never talks to Postgres/Redis directly. It holds an HttpOnly/Secure/
SameSite=Lax session cookie, and its Route Handlers proxy authenticated requests to
FastAPI, attaching the access token server-side. FastAPI is the **only** place
authorization is enforced — the frontend hiding a button is a UX nicety, never a
security control. Every domain query that touches org-scoped or branch-scoped data
applies the tenant/branch filter in the repository layer, not only in the router.

## 5. Data integrity rules (non-negotiable, see `business-rules.md` for detail)

- Money, percentages and quantities used in economic calculations: `Decimal` in Python,
  `NUMERIC` in Postgres, or integer cents. Never `float`.
- The commercial network's source of truth is Postgres (closure table). No graph
  database in v1 (see `adr/0002-no-graph-db-v1.md`). pgvector is used only for
  semantic/document search, never for the org chart (see `adr/0003-pgvector-scope.md`).
- Consolidated commission ledger movements are immutable; corrections are new movements.
- Contract attribution is frozen via `network_snapshot_id` at activation time; later
  network moves never rewrite historical attribution or past calculations.
- **A contract's economics are frozen at creation too** (`net_amount_cents`,
  `vat_rate`, `vat_amount_cents`, `gross_amount_cents`, `customer_kind`): editing a
  product's price or VAT rate can never restate a contract somebody already signed.
  Same rule, one layer down, as the network snapshot above.
- **No economic value is ever taken from the client.** Prices, VAT, commissions,
  cashback, bonuses and wallet amounts are computed from database rows inside the
  service layer; the browser sends identifiers and intent, never amounts.
- **Exactly-once for anything that moves money** is enforced by a UNIQUE constraint on
  a deterministic key, not by an application flag that could drift: `wallet_
  transactions.idempotency_key`, `commission_movements.idempotency_key`,
  `uq_commission_calculations_contract_trigger`. Readable guards (e.g.
  `contracts.cashback_credited_at`) exist on top of those, never instead of them.
- **A notification can never fail an operation that already committed.** Mail sent
  after a commit goes through `core/email.py::send_html_email_best_effort`, which
  never raises — the one exception being password-reset links and OTP codes, where the
  email IS the deliverable (see `server-migration-guide.md §8 #17` for the
  double-credit bug this rule exists to prevent).

## 6. Repository layout (target)

```
/apps
  /api         FastAPI backend (domains/, alembic/, tests/)
  /dashboard   Next.js 16 App Router BFF + UI
  /worker      Celery worker + beat, imports apps/api domain code
/packages
  /shared-types   Types shared between dashboard and worker/scripts (generated from OpenAPI where possible)
  /config         Shared lint/tsconfig bases
/infrastructure
  /docker
  /nginx
  /postgres
  /monitoring
/scripts       deploy/backup/restore/health-check/migrate/rollback
/docs          this documentation set
```

`packages/ui`, `packages/api-client`, `packages/eslint-config`, `packages/typescript-config`
are placeholders reserved for Phase F when the dashboard grows multiple apps; not
created empty in Phase B to avoid dead scaffolding (YAGNI — added the moment a second
consumer needs them).

## 7. What is implemented vs. planned

See `implementation-progress.md` for the authoritative, continuously-updated status.
This document describes target architecture, not necessarily current state.
