# Security Model

## Authentication
- Passwords hashed with Argon2id (`pwdlib[argon2]`).
- Access tokens: short-lived JWT (15 min default), signed, containing `sub`, `org_id`,
  `roles`, `jti`. Never stored client-side except in memory for the lifetime of a
  request cycle inside the BFF.
- Refresh tokens: opaque, random, hashed before storage in `sessions.refresh_token_hash`,
  rotated on every use (old one revoked the moment a new one is issued), persisted so a
  single session or all sessions for a user can be revoked server-side.
- Browser storage: HttpOnly + Secure + SameSite=Lax cookies only, set by the Next.js BFF.
  The BFF is the only party that ever sees the refresh token; FastAPI issues it to the
  BFF over the internal network, not to the browser directly.
- Rate limiting on `/auth/login`, `/auth/password-reset` (Redis token bucket per IP +
  per account) to blunt brute force and account enumeration; error responses are
  identical for "unknown email" and "wrong password".
- MFA: schema present (`sessions`, future `user_mfa_methods`), not enforced in v1 —
  see `open-questions.md #7`.
- Account lockout: placeholder policy, see `open-questions.md #7`.

## Authorization (RBAC + ABAC)
- RBAC: `roles` → `role_permissions` → `permissions`, assigned per user per
  organization via `user_roles`. Permission codes are dotted strings
  (`contracts.approve`, `network.manage`, ...) checked by a single dependency
  (`require_permission("contracts.approve")`) injected into routers — never
  reimplemented ad hoc per endpoint.
- ABAC: contextual checks layered on top of RBAC in the service layer, not the router:
  organization membership, branch ownership (via `network_closure` ancestor check),
  customer/contract ownership, document category, contract status. A promoter with
  `commissions.read_own` can only read `commission_movements` rows for their own
  `agent_id`; a Team Leader with `network.read_branch` can only read rows whose
  `agent_id` is a descendant of their own `agent_id` in `network_closure` for their
  organization.
- Every domain repository method that returns tenant- or branch-scoped data takes the
  caller's org/branch context as a mandatory argument — there is no "unscoped" query
  path available to routers. This is enforced by convention + code review today;
  Postgres Row-Level Security is deferred (see below) rather than assumed as a backstop.

## Multi-tenancy
- Every tenant-scoped table carries `organization_id`. All repository queries filter on
  it explicitly; the frontend's org context is never trusted as the actual filter.
- Row-Level Security (RLS) was evaluated and deferred for v1: it would add real
  defense-in-depth, but also connection-pooling complexity (need `SET
  app.current_org_id` per request scope) and migration complexity (every table needs a
  policy). Revisit once the number of domains and engineers touching raw queries grows
  enough that "always filter by org_id in the repository" stops being a reliable
  guarantee by convention alone.

## Documents
- Uploads validated by MIME whitelist and size limit before storage.
- Storage keys are opaque; the bucket is never exposed directly — all access is via
  short-lived signed URLs issued after an authorization check.
- Antivirus scan hook (`document_scan_results`) is a pluggable interface; no scanner is
  wired in v1 (documented gap, not silently assumed safe — downloads remain
  permission-gated regardless of scan status).

## Audit
- `audit_log` is append-only (no UPDATE/DELETE grants for the application role in
  production). Passwords, tokens, and full document contents are never written to
  audit rows — only entity references and before/after value diffs for fields that are
  safe to log.

## Secrets
- No secrets in the repository. `.env.example` lists required variable names with
  placeholder/empty values only. Real secrets are supplied via environment at deploy
  time (Docker secrets / platform secret store), never committed.
