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
- `wallet.manage` (Session 21, migration `0018`): gates every admin wallet
  route (list all wallets, view/credit any user's wallet, view the global
  transaction ledger, reverse a transaction). `SUPER_ADMIN`/
  `ORGANIZATION_ADMIN`/`ADMIN` only, deliberately not
  `BACK_OFFICE_OPERATOR` -- crediting a wallet is a real money-adjacent
  action (cashback), same tier as `commissions.evaluate_ranks`. Reading or
  spending from one's OWN wallet needs no permission beyond authentication
  (`GET /wallets/me`, `POST /wallets/transfer`) -- the source wallet is
  always resolved from the caller's own `user_id`, never from the request
  body, so there is no cross-user access surface to gate. See
  `business-rules.md §Internal wallet`.
  - **Financial-integrity controls, not just RBAC**: a wallet debit uses an
    atomic compare-and-swap `UPDATE ... WHERE balance_cents >= :amount`
    (checked via affected-row-count, not a pre-read-then-write race) plus a
    DB `CHECK (balance_cents >= 0)` as defense in depth -- the first CHECK
    constraint anywhere in this codebase. Every credit/transfer/reversal
    carries a client-generated `idempotency_key` (unique DB constraint) so a
    double-submitted request can never double-apply. `POST /wallets/transfer`
    is additionally rate-limited per IP (20/60s) against scripted abuse.
  - **Spending existing wallet credit needs a fresh OTP (Session 33)**: at
    self-checkout (`POST /orders/mine`), any `credit_applied_cents > 0`
    requires an `otp_code` matching one just emailed via `POST
    /orders/mine/request-credit-otp` (reuses the platform's generic OTP
    infrastructure -- `auth/service.py::request_otp`/`verify_otp`, single-use,
    10-minute expiry). A stolen session token alone can no longer drain a
    wallet at checkout. The staff endpoint (`POST /orders`, `wallet.manage`-
    gated) is exempt by design: an admin applying a customer's credit on
    their behalf is already an audited, permissioned action, and the OTP
    would land in the customer's inbox, not the admin's.
  - **Cashback can only ever be minted against a real, confirmed charge
    (Session 33)**: both the per-product "riscuoti subito cashback"
    (`orders`) and the partner-invoice redemption bonus
    (`invoice_redemptions`) compute the credited amount from the money
    actually paid in *that* transaction, never a higher pre-discount base
    (see `database-model.md` §11/§10 for the exact arithmetic) -- this is
    what prevents a customer from using credit to pay, then having cashback
    computed off the un-discounted price and manufacturing credit from
    credit. Crediting is idempotent (a status-column guard plus
    deterministic, non-client-supplied `idempotency_key`s). And critically:
    an admin's manual "confirm bank transfer received" action is refused
    server-side (`InvalidOrderStateError`/`InvalidRedemptionStateError`, not
    just a hidden button) for any order/redemption whose `payment_method`
    is `CARD` -- only the Stripe webhook, once Stripe itself confirms a real
    charge, may credit those. Verified live during Session 33: a CARD-method
    redemption manually "confirmed" by an admin is rejected and mints
    nothing; the same redemption is correctly credited once the webhook
    fires.

## Multi-tenancy
- Every tenant-scoped table carries `organization_id`. All repository queries filter on
  it explicitly; the frontend's org context is never trusted as the actual filter.
- Row-Level Security (RLS) was evaluated and deferred for v1: it would add real
  defense-in-depth, but also connection-pooling complexity (need `SET
  app.current_org_id` per request scope) and migration complexity (every table needs a
  policy). Revisit once the number of domains and engineers touching raw queries grows
  enough that "always filter by org_id in the repository" stops being a reliable
  guarantee by convention alone.

## Documents (identity, fiscal code, utility bill, chamber-of-commerce — Session 14; hardened Session 33)
- Uploads (`app/domains/documents/`) are validated by MIME whitelist
  (`application/pdf`, `image/jpeg`, `image/png` only) and a 15 MB size limit
  before storage; rejected content never reaches MinIO.
- **Magic-byte verification (Session 33)**: the `Content-Type` header an
  upload arrives with is client-supplied and trivially spoofable (rename
  `payload.html` to `bolletta.pdf`, send it with
  `Content-Type: application/pdf`, and a whitelist check alone would wave
  it through). `core/storage.py::_verify_magic_bytes()` additionally checks
  the file's actual leading bytes against the real signature for its
  claimed type (`%PDF-` for PDF, `\xff\xd8\xff` for JPEG, the PNG/GIF/WEBP
  signatures) before any upload reaches MinIO, for **every** bucket this
  module writes to: the public media bucket, the documentation attachment
  bucket, and the private documents bucket (KYC documents, order payment
  proofs, invoice-redemption uploads and their payment proofs -- see
  below). Not a full antivirus/content scan (that gap is still separate
  and deliberate, see `ensure_documents_bucket()`'s docstring below) --
  this only proves the bytes are *structurally* what they claim to be.
- **Rate limiting on upload endpoints (Session 33)**: `POST
  /contracts/{id}/documents`, `POST /orders/mine/{id}/payment-proof`, `POST
  /invoice-redemptions`, and `POST
  /invoice-redemptions/mine/{id}/payment-proof` are all rate-limited (20
  requests / 5 min per IP, `core/rate_limit.py`, same fail-open mechanism
  as the auth endpoints) as defense-in-depth against an authenticated
  session being used to spam-upload and fill storage.
- **Order payment proofs and invoice-redemption uploads reuse this same
  private bucket and access model (Sessions 28-33)**: a customer's
  bank-transfer receipt photo (`orders.payment_proof_storage_key`,
  `invoice_redemptions.payment_proof_storage_key`) and an invoice-
  redemption's own uploaded invoice photo (`invoice_redemptions.
  storage_key`) are never routed through the `documents` table (whose
  `contract_id` is NOT NULL by design) -- they call
  `core/storage.py::upload_document`/`generate_presigned_document_url`
  directly, under their own key prefixes
  (`order-payment-proofs/{customer_user_id}/`,
  `invoice-redemption-payment-proofs/{customer_user_id}/`,
  `invoice-redemptions/{customer_user_id}/`). Same private bucket, same
  no-bucket-policy-at-all default, same short-lived-presigned-URL-only
  access pattern, same ownership/permission checks in each domain's own
  router (`get_owned()` for the caller's own upload, `wallet.manage` for
  staff) as KYC documents below -- there is no separate, weaker code path
  for these.
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
