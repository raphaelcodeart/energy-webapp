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
- `network.approve` (Session 17): a real example of a permission deliberately
  narrower than an existing one that looks like it should cover it. A plain
  `ADMIN` holds `network.manage` (create/edit any agent) but NOT
  `network.approve` (confirm a suggested agent into an active one) —
  `SUPER_ADMIN`/`ORGANIZATION_ADMIN` are the only roles that get it, since
  they're implicitly granted the full `PERMISSIONS` list rather than an
  explicit subset. See `business-rules.md §New promoter suggest-then-approve
  workflow`.
- `tickets.delete` (Session 19): same narrowing pattern applied again --
  `BACK_OFFICE_OPERATOR` holds `tickets.respond` (reply, change status) but
  not `tickets.delete` (permanently remove a resolved ticket and its
  messages); only `SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN` get it. The
  service layer also independently refuses to delete anything not in
  `RESOLVED` status regardless of who's asking. See `business-rules.md
  §Support tickets §Search, filter, and deletion`.
- `documentation.manage` (Session 20, migration `0015`): gates
  create/edit/archive of `documentation_posts` (the admin news/training
  feed). Same tier as `products.manage` --
  `SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN`. Reading the feed itself needs no
  permission check beyond authentication -- it's self-filtered by the
  viewer's own CUSTOMER/PROMOTER role against each post's `audience`.
- `commissions.evaluate_ranks` (Session 20, migration `0013`): gates `POST
  /commissions/rank-evaluation/run`, the manual trigger for the automatic
  monthly rank promotion/demotion. Same narrow tier as `network.approve` --
  `SUPER_ADMIN`/`ORGANIZATION_ADMIN` only, deliberately not plain `ADMIN`,
  since a mistaken run can move real agents' ranks (and therefore future
  commission amounts) in either direction. See `business-rules.md
  §Automatic monthly rank evaluation`.
- `network.approve` also now gates `POST /network/agents/root` (Session 20)
  -- creating a parentless "root" promoter is treated as the same
  sensitivity tier as approving a suggested agent, not the broader
  `network.manage`.

## Multi-tenancy
- Every tenant-scoped table carries `organization_id`. All repository queries filter on
  it explicitly; the frontend's org context is never trusted as the actual filter.
- Row-Level Security (RLS) was evaluated and deferred for v1: it would add real
  defense-in-depth, but also connection-pooling complexity (need `SET
  app.current_org_id` per request scope) and migration complexity (every table needs a
  policy). Revisit once the number of domains and engineers touching raw queries grows
  enough that "always filter by org_id in the repository" stops being a reliable
  guarantee by convention alone.

## Documents (identity, fiscal code, utility bill, chamber-of-commerce — Session 14)
- Uploads (`app/domains/documents/`) are validated by MIME whitelist
  (`application/pdf`, `image/jpeg`, `image/png` only) and a 15 MB size limit
  before storage; rejected content never reaches MinIO.
- **Private bucket, no public access of any kind**: `lial-documents`
  (`S3_BUCKET_DOCUMENTS`) is a SEPARATE MinIO bucket from the public
  `lial-media` photo bucket below, and deliberately gets **no bucket policy
  at all** — `ensure_documents_bucket()` only creates the bucket if missing,
  nothing else, because MinIO buckets are private-by-default until a policy
  explicitly grants anonymous access. There is no code path, in this project,
  that can make a document in this bucket publicly reachable.
- **Access is exclusively via short-lived presigned URLs**: every read goes
  through `GET /documents/{id}/url` (gated by `documents.download` +
  contract-ownership ABAC), which returns a SigV4-signed URL good for 5
  minutes (`generate_presigned_document_url()`, `PRESIGNED_URL_TTL_SECONDS =
  300`). There is no other way to fetch a document's bytes — no direct
  bucket URL, no static file path, nothing a search-engine crawler or a
  leaked link could reuse after the window expires.
- **Reverse-proxy signature mechanics**: nginx's `location /lial-documents/`
  (`infrastructure/nginx/nginx.conf`) forwards to MinIO with a **hardcoded**
  `Host: minio:9000` header, not `$host`. The presigning client inside the
  API signs the request against MinIO's internal Docker hostname
  (`http://minio:9000`); SigV4 signatures cover the `Host` header, so if
  nginx forwarded the public domain's Host instead, every presigned URL
  would fail `SignatureDoesNotMatch` regardless of validity. Verified live:
  the signed URL returns the file (200); the identical path with the
  signature stripped off, or a bare bucket-listing request, both return
  MinIO's own `403 AccessDenied`.
- Antivirus scan hook (`document_scan_results`) is a pluggable interface; no scanner is
  wired in v1 (documented gap, not silently assumed safe — downloads remain
  permission-gated regardless of scan status).
- Who can see what: `documents.upload` is granted to `CUSTOMER` (their own
  contract only, ABAC-checked) and every staff role; `documents.review`
  (approve/reject with a note) is staff-only — a customer can add documents
  but never mark their own as verified. Admin/back-office can also upload a
  document to any contract directly ("the customer sent it another way"),
  not just review what the customer submitted themselves.

## Profile / product photos — a deliberately different, PUBLIC bucket
- **Not the same bucket as the sensitive documents above** (Session 13,
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
