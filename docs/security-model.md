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
- Rate limiting (Session 13) on `/auth/login`, `/auth/register`,
  `/auth/forgot-password`, `/auth/reset-password`: a fixed-window counter per
  (endpoint, client IP) in Redis (`core/rate_limit.py`) -- not a token bucket,
  and per-IP only, not per-account (per-account is the separate lockout
  mechanism below). Fails OPEN if Redis is unreachable: a rate-limiter outage
  must never take down login/registration. Requires uvicorn's
  `--proxy-headers --forwarded-allow-ips` (set in `docker-compose*.yml`) so
  `request.client.host` reflects the real visitor behind nginx, not nginx's
  own container IP -- without it every request looks like it comes from the
  same source and the limiter is blind (this was actually the case until
  Session 13; see `server-migration-guide.md`).
- Account lockout: exists and is enforced (`auth/service.py`,
  `MAX_FAILED_ATTEMPTS`/`LOCKOUT_WINDOW_MINUTES`) -- 5 failed attempts locks
  the account for 15 minutes. The specific threshold numbers are a
  placeholder pending real policy, see `open-questions.md #7`; the mechanism
  itself is real, not a stub.
- Error responses are identical for "unknown email" and "wrong password" (login),
  and for "email exists" vs "email doesn't exist" (password reset request) --
  both paths return the same generic success/failure shape so neither can be
  used to enumerate registered accounts. A password reset always revokes every
  existing session for that user on success.
- Password reset (Session 13): single-use, time-limited (60 min) opaque token,
  hashed at rest (`password_reset_tokens.token_hash`) -- same pattern as
  refresh tokens. Delivered by real SMTP when configured
  (`core/email.py`, `SMTP_*` in `.env`); if not configured, the reset link is
  written to the API process log only (`docker compose logs api`), NEVER to
  `audit_log` or anywhere a web-UI role (even `audit.read`) could read it --
  that would let any admin-tier account take over any user's account by
  reading their reset link. See `business-rules.md §Password reset`.
- MFA: schema present (`sessions`, future `user_mfa_methods`), not enforced in v1 —
  see `open-questions.md #7`.
- `/backend/docs`, `/backend/redoc`, `/backend/openapi.json` (full OpenAPI
  surface) are reachable directly from the internet by default
  (`ENABLE_API_DOCS=true`) -- convenient for development, a full API-surface
  disclosure for a real production deployment. Set `ENABLE_API_DOCS=false` in
  `.env` before treating a deployment as production-hardened.
- Baseline response headers (nginx, Session 13): `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy:
  strict-origin-when-cross-origin`, `Strict-Transport-Security`. No CSP yet --
  Next.js's inline hydration/RSC payload scripts need a nonce-based CSP to not
  break under a strict policy, which is a larger, separate change (tracked as
  a follow-up, not guessed at).

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
- **Not the same bucket as profile/product photos** (Session 13,
  `core/storage.py`): photos live in a SEPARATE, deliberately PUBLIC-read
  bucket (`lial-media`/`S3_BUCKET_MEDIA`) served directly by nginx, since
  they're not sensitive and need to be trivially embeddable as `<img src>`.
  Uploads there are still MIME-whitelisted (`image/jpeg|png|webp|gif` only)
  and size-limited (5 MB) before storage, same discipline as documents, but
  the *access model* is intentionally different (public, not signed-URL) —
  never put anything sensitive in this bucket.

## Audit
- `audit_log` is append-only (no UPDATE/DELETE grants for the application role in
  production). Passwords, tokens, and full document contents are never written to
  audit rows — only entity references and before/after value diffs for fields that are
  safe to log.

## Secrets
- No secrets in the repository. `.env.example` lists required variable names with
  placeholder/empty values only. Real secrets are supplied via environment at deploy
  time (Docker secrets / platform secret store), never committed.
