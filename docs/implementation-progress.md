# Implementation Progress

Updated at the end of each work session. This is the authoritative "what's actually
done vs. planned" record — `architecture.md` describes the target, this file describes
reality.

## Session 1 — 2026-07-25

### Phase A — Analysis & documentation
- [x] Repository analysis (repo was empty — greenfield build)
- [x] `docs/architecture.md`
- [x] `docs/database-model.md` (+ ER diagram)
- [x] `docs/business-rules.md` (placeholders flagged, see open-questions.md)
- [x] `docs/commission-engine-specification.md`
- [x] `docs/open-questions.md`
- [x] `docs/security-model.md`
- [x] `docs/network-model.md`
- [x] `docs/ai-architecture.md` (design only, Phase G not implemented)
- [x] `docs/deployment.md`
- [x] `docs/adr/0001..0005`

### Phase B/C/D/E — Vertical slice (in progress this session)
Status filled in at the end of this session — see the running checklist below,
updated as each part lands.

- [ ] Monorepo scaffold (pnpm workspace)
- [ ] Docker Compose (postgres, redis, minio, api, dashboard, worker, nginx)
- [ ] Auth (Argon2id, JWT access + refresh, sessions, revoke)
- [ ] Organizations + RBAC + audit log
- [ ] Network domain (nodes/edges/closure/snapshot, move transaction)
- [ ] Referral domain (promoter codes, referral events, attribution)
- [ ] Catalog + customers + supply points + contracts (state machine)
- [ ] Commission engine (personal token + entrepreneurial difference + 33% cap) + ledger
- [ ] Alembic migrations
- [ ] Seed demo data
- [ ] Minimal dashboards (customer/promoter/admin)
- [ ] Tests (commission engine, auth, org/branch isolation)
- [ ] `docker compose up --build` verified end-to-end
- [ ] README with exact run/verify commands

### Explicitly NOT in this session's scope (tracked for later phases)
- Payments beyond `MockPaymentProvider` interface stub
- Document antivirus scanning, full document permission matrix beyond basic ownership
- Notifications (Celery task skeleton only, no templates/providers wired)
- Reporting/export beyond what's trivially derivable from the slice's data
- AI/pgvector (design doc only, `docs/ai-architecture.md`)
- CI/CD pipeline, backup/restore automation, monitoring stack
- MFA enforcement, full GDPR tooling
- Full test matrix from `commission-engine-specification.md` (only the subset listed
  there under "Implemented now")

### Known risks / assumptions
See `docs/open-questions.md` for the full list (rank thresholds, network move
approval, Energia Circolare formula, reversal formula, GDPR retention, 33% cap
denominator, MFA/lockout policy) — all are placeholders pending real business input.
