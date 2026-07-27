# Implementation Progress

Updated at the end of each work session. This is the authoritative "what's actually
done vs. planned" record — `architecture.md` describes the target, this file describes
reality.

## Session 19 — 2026-07-27 — Ticket search/filter, delete-when-resolved, and a proxy 204 bug found along the way

- **Ticket search & filter**: `AdminTicketsPanel` gained a free-text search
  (subject + opener name) and a category filter, alongside the existing
  opener/status filters -- all client-side over the already-fetched list
  (see `business-rules.md §Support tickets §Search, filter, and deletion`).
- **Ticket deletion, gated on RESOLVED status**: a new `DELETE
  /support/tickets/{id}` endpoint (`tickets.delete` permission, migration
  0012, granted to `SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN` only --
  deliberately not `BACK_OFFICE_OPERATOR`, same narrowing pattern as
  `network.approve`) deletes a ticket and its messages in one transaction,
  but only if `status == RESOLVED`; any other status raises
  `TicketDeletionError` -> `400`. The frontend disables the trash-icon
  button (in both the ticket list row and the detail view) for any
  non-resolved ticket and always shows a confirm dialog naming the ticket
  before calling the endpoint -- there is no direct-delete path.
- **Real bug, found and fixed**: the shared BFF proxy
  (`app/api/proxy/[...path]/route.ts`) built every response as `new
  NextResponse(body, {status: apiRes.status})`, including for a 204 No
  Content. The Fetch spec throws when a 204/205/304 response is
  constructed with a non-null body -- even `""` counts as non-null -- so
  every no-content response 500'd inside the proxy despite the upstream
  call already succeeding. This was invisible until now because the DELETE
  endpoint added this session was the **first ever 204 response** returned
  by any endpoint reachable through this proxy. Confirmed live: a ticket
  delete removed the row from the database while the UI reported
  "Impossibile eliminare il ticket." Fixed by special-casing
  204/205/304 to `new NextResponse(null, ...)`. Re-verified live after the
  fix: delete now both removes the ticket server-side and reflects it
  correctly in the UI.

## Session 18 — 2026-07-27 — Hide Organization ID from login/forgot-password

- User asked what the "ID Organizzazione" field on login/forgot-password and
  the UUIDs shown elsewhere actually are, whether they're needed, and
  whether the platform is really one organization per reseller company or
  one per individual promoter. Answer: the data model is genuinely
  multi-tenant (`organizations` table, `User` has a
  `UniqueConstraint("organization_id", "email")` -- deliberately allows the
  same email across different orgs), but only ONE organization ("Lial
  Energy Demo") exists today, confirmed live against the database. An
  organization is a whole reseller company that could license this
  platform, never an individual promoter -- promoters are just agents
  inside one org's network.
- Given that today there is exactly one org and no near-term plan for a
  second, hardcoding it in the frontend was the lowest-friction fix with no
  backend/security change. Added `apps/dashboard/lib/config.ts` exporting
  `DEFAULT_ORGANIZATION_ID`; removed the "ID Organizzazione" field from
  `login/page.tsx` and `forgot-password/page.tsx`, both now silently send
  the constant. The backend endpoints are untouched -- they still require
  `organization_id` in the request body, so multi-tenant capability is
  fully preserved. If a second organization is ever onboarded, this
  shortcut must be reverted in favor of an org picker or server-side
  resolution from the email (noted directly in `config.ts`'s comment).
  Verified live with Playwright: both pages render with no Organization ID
  field, a real login and a real forgot-password submission both succeed.

## Session 17 — 2026-07-28 — In-app notifications, promoter suggest-then-approve workflow, promoter dashboard quick-links, rebuilt commission statement

- **New promoter approval workflow**: `POST /network/agents` (admin,
  org-wide) and `POST /network/agents/recruit` (a promoter enrolling their
  own direct collaborator) now only ever create `PENDING_APPROVAL` agents,
  never immediately `ACTIVE` -- a plain `ADMIN` can "suggest" a collaborator
  but only `SUPER_ADMIN`/`ORGANIZATION_ADMIN` (the "amministratore
  principale") can turn that into a real, contract-producing agent, via new
  `PATCH /network/agents/{id}/approve`/`/reject` endpoints gated on a new
  `network.approve` permission deliberately not granted to plain `ADMIN`
  (who already holds the broader `network.manage`). Rejecting is soft
  (`TERMINATED` + a kept reason), never a hard delete. See
  `business-rules.md §New promoter suggest-then-approve workflow`.
- **New in-app notifications domain** (`app/domains/notifications/`): a
  bell icon in the header (all three dashboards, shared `app-shell.tsx`)
  with an unread badge and dropdown, plus a small unread dot on whichever
  sidebar nav item is actually relevant to a given notification (each
  `NavItem` opts in via a `notificationTypes` array, so e.g. a promoter
  approval request only lights up "Anagrafiche Promoter", never "Tutti i
  Contratti"). Clicking a notification marks it read and navigates to the
  matching tab. Polled every 25s, no WebSockets. Wired into: contract
  creation, ticket creation, both promoter-approval creation paths, and
  every commission movement generated (notifies the specific beneficiary's
  linked user, if they have a login). See `database-model.md §7` and
  `business-rules.md §Notifications` for the full fan-out design (one row
  per recipient, never per role; the triggering actor is excluded from
  their own event's notifications).
- **Promoter dashboard: quick-link buttons + rebuilt "Estratto Conto
  Provvigioni"**. Added the same large quick-access button grid the admin
  Panoramica already had (Rete Commerciale, Prodotti da Condividere,
  Movimenti Provvigioni, Simulatore, Supporto) to the promoter's own "La
  mia Azienda" landing tab. `MyCommissions` (`my-commissions.tsx`) was a
  bare list of type/amount/status before this session -- rebuilt on a new
  `GET /commissions/mine/detailed` endpoint (reuses the admin ledger's
  `admin_ledger.get_commission_movements()`, hard-scoped to the caller's
  own `agent_id`, gated on `commissions.read_own` not `commissions.approve`)
  to show, per movement: customer name, product, and a plain-language
  "provenienza" ("Prodotto da te" / "Da un tuo diretto" / "Da N livelli
  sotto di te" -- `depth_from_producer` is already relative to the viewer
  when the row is their own), with a click-to-expand full breakdown
  (contract value, base token, already-distributed-below, the same
  human-readable explanation the admin ledger shows) -- the exact same
  traceability the admin gets, just permission-scoped to "yours only".
- **Real bug fixed while building this**: the admin contract "Recensisci"
  dropdown listed every one of the 14 contract statuses regardless of the
  contract's actual current status, so picking anything the state machine
  didn't allow from that status (e.g. `DRAFT` → `ACTIVE`) always 400'd with
  "Cannot transition contract from X to Y" -- confusing since nothing in
  the UI hinted which choices were valid. Fixed by mirroring
  `state_machine.py::ALLOWED_TRANSITIONS` as a frontend constant and
  filtering the dropdown to the contract's real valid next-states; a
  contract already in a terminal state (`REJECTED`/`CANCELLED`) now shows a
  clear "reached a final state" message instead of a dropdown with no
  valid choices.

Backend: 93 tests passing (was 87 -- 6 new: PENDING_APPROVAL creation,
approve/reject + idempotent re-decision rejection, notification fan-out
excludes the actor and only reaches the right role, mark-read/mark-all-read,
contract creation notifies staff). Frontend: clean tsc/eslint/next build.
Verified live over HTTPS with a headless browser end to end: admin creates a
promoter → PENDING_APPROVAL confirmed via API → SUPER_ADMIN sees the bell
badge and the "Anagrafiche Promoter" sidebar dot → clicking the notification
navigates there and marks it read → clicking "Approva" through the real UI
flips the agent to ACTIVE; a plain ADMIN's approve attempt correctly 403s;
the promoter dashboard's quick-links and the rebuilt commission statement
(including row expansion) all render real data correctly.

## Session 16 — 2026-07-27 (same day, continued) — Clickable KPI cards, admin commission traceability + payment tracking, CSV export

- Every KPI card on the admin Panoramica is now clickable and navigates to
  the relevant tab pre-filtered to exactly the rows that produced that
  number (`Contratti attivi` → contracts list filtered `ACTIVE`, `In attesa
  di approvazione` → the same status set `reports/service.py` already sums
  for that KPI, `Respinti / cessati` → a new combined `REJECTED`+`CANCELLED`
  filter value, `Promoter attivi`/`Clienti attivi` → their respective lists
  filtered to active, `Provvigioni maturate/pagate` → the new Provvigioni
  tab pre-filtered by status).
- New admin "Provvigioni" tab + `GET /commissions/movements`
  (`commissions/services/admin_ledger.py`, gated on `commissions.approve`
  -- org-wide, so it must NOT reuse `commissions.read_branch`, which
  `TEAM_LEADER`/`PROMOTER` also hold for their own branch only): full
  traceability per commission movement -- contract, customer, promoter,
  their depth below the contract's producer, rank at calculation vs. now,
  and the exact breakdown -- all of it already computed by
  `CommissionCalculationStep` at calculation time but never exposed by any
  endpoint before this. Plus `GET /commissions/movements/by-level` for a
  per-network-level rollup (contracts/revenue/commission at each depth).
- New `PATCH /commissions/movements/{id}/pay`: the missing write path for
  `commission_movements.status`/`paid_date`, present in the schema since
  migration 0001 but never set to anything but `ACCRUED` by any code path --
  "Provvigioni pagate" had always shown €0,00 for exactly that reason.
  Rejects re-paying an already-`PAID` movement.
- CSV export (`lib/csv-export.ts`, client-side, no backend endpoint needed)
  added to Tutti i Contratti, Anagrafiche Clienti, Anagrafiche Promoter, and
  the new Provvigioni tab.

Backend: 87 tests passing (was 83 -- 4 new). Frontend: clean tsc/eslint/next
build. Verified live: KPI clicks land pre-filtered correctly; a movement was
marked paid through the real UI and the "Provvigioni pagate" total updated.

## Session 15 — 2026-07-27 (same day, continued) — Rank promotion progress ("what's missing for the next qualification")

Requested, then explicitly authorized this session ("procurati quei criteri
qualifica e falli tu" -- go get those criteria and set them yourself) after
being told the real promotion thresholds were never defined anywhere
(`open-questions.md #1`). `ranks.personal_volume_threshold_cents`/
`group_volume_threshold_cents` existed in the schema since migration 0001
but were always 0, never read anywhere -- populated with reasonable,
ascending, demo-scale placeholder figures (migration 0010 +
`seed/ranks.py`), explicitly documented as not confirmed Lial Energy policy.
New `GET /network/agents/{id}/rank-progress` compares an agent's cumulative
(lifetime, not evaluation-windowed) contract value against the next rank's
thresholds -- personal (self-produced) and group (entire downline including
self) -- surfaced as two progress bars in `PromoterAziendaPanel`, shared by
both the promoter's own "La mia Azienda" tab and the admin's per-promoter
"Apri Rete" drill-down. An agent already at the top rank shows "qualifica
massima raggiunta" instead. Also fixed in this session: the promoter header
box showed the raw rank UUID instead of the rank code (backend never
returned `rank_code` on `GET /network/mine`) and was narrower than the
content below it.

Backend: 83 tests passing (was 79 -- 4 new). Frontend: clean tsc/eslint/next
build. Verified live: migration applied, real threshold figures on all 12
ranks, correct progress data for both a mid-tier and a max-tier agent.

## Session 14 — 2026-07-26 (same day, continued) — Sensitive document uploads (private storage), contract IBAN, demo data expanded to 12 full levels, network tree click-through popup

Continuation of another large multi-part request. All items below were built,
tested, and verified live:

- **Sensitive contract documents, built end-to-end** (identity, fiscal code,
  utility bill, and — for companies/condominiums — chamber-of-commerce
  registration). New `documents` domain (`app/domains/documents/`): a
  `Document` model with an explicit state machine
  (`PENDING_REVIEW → APPROVED/REJECTED`), org- and contract-scoped everywhere,
  snapshotting the uploader's role at upload time (same "frozen at the moment
  it happens" pattern used elsewhere in this project). Endpoints:
  `POST /contracts/{id}/documents` (multipart, customer-own-contract-or-staff),
  `GET /contracts/{id}/documents` (one row per *required* type for that
  customer's kind, `null` if not yet uploaded — so the UI can show "missing"
  as a first-class state, not just absence of data), `GET
  /documents/{id}/url` (short-lived presigned view link), `PATCH
  /documents/{id}/review` (admin/back-office only, approve or reject with a
  note). Required types are `IDENTITY`/`FISCAL_CODE`/`UTILITY_BILL` for
  everyone, plus `CHAMBER_OF_COMMERCE` for `COMPANY`/`CONDOMINIUM` customers.
  Both the customer (their own contract) and admin/back-office (any contract,
  e.g. "the customer emailed me the file, I'm uploading it for them") can
  upload; only admin/back-office can review. New RBAC permissions
  `documents.upload` (also granted to `CUSTOMER`) and `documents.review`,
  seeded via an idempotent data migration (`0009`) using the same
  `on_conflict_do_nothing()` pattern as migration `0006` — declaring a
  permission in code alone never reaches an already-seeded live database.
- **Private document storage — the actual security requirement driving this
  feature**: the user was explicit that these files must never be reachable
  by search engines or anyone outside the organization, "solo dall'amministratore",
  with a real protected storage design, not just "don't link to it". Built as
  a *second*, entirely separate MinIO bucket (`lial-documents`) alongside the
  existing public `lial-media` bucket from Session 13 — this one gets **no
  bucket policy at all** (MinIO buckets are private-by-default; the fix here
  was writing *less* code, not more). The only access path is a server-side,
  time-limited (5-minute) presigned SigV4 URL
  (`storage.py::generate_presigned_document_url()`), generated after the
  `documents.download`/ownership check already ran — never a direct or
  guessable link. New nginx location `/lial-documents/` reverse-proxies to
  MinIO with a **hardcoded** `Host: minio:9000` header (not `$host`) — SigV4
  signatures are computed over the exact host the signing client used
  (MinIO's internal Docker name), so forwarding the public domain's Host
  instead would make every presigned URL fail with `SignatureDoesNotMatch`
  regardless of validity; this is the same "static `proxy_pass` target,
  documented trade-off" pattern used for `/backend/` and `/media/` in earlier
  sessions. Verified live, all three ways: (1) a valid presigned URL returns
  the real file (200), (2) the identical path with the signature query
  string stripped off returns MinIO's own `403 AccessDenied`, and (3) listing
  the bucket directly also 403s. No indexable, guessable, or unauthenticated
  path to a sensitive document exists anywhere in this design.
- **Real bug found and fixed — every PATCH-based save in the app had been
  silently broken since the feature it belonged to was first built**: the
  BFF's generic proxy (`app/api/proxy/[...path]/route.ts`) only ever
  implemented `GET` and `POST` handlers. Discovered while wiring the new
  `PATCH /documents/{id}/review` endpoint, which 405'd through the proxy;
  checked whether this was a new regression by hitting `PATCH
  /api/proxy/customers/{id}` directly — also 405, confirming this had been
  broken for customer edit, promoter edit, product edit, supply-point label
  edit, and (from this same session) contract IBAN update, the entire time
  those "save" buttons existed. Fixed by extracting a shared
  `proxyWithBody()` helper and adding real `PATCH`/`PUT`/`DELETE` handlers
  alongside the existing `POST`. Verified live, before and after: `PATCH
  /api/proxy/customers/{id}` went from 405 to 200 with the fix in place.
- **Contract IBAN**: `contracts.iban` column (migration `0009`, basic format
  validation — `^[A-Z]{2}[0-9A-Z]{13,32}$`, not a full mod-97 checksum),
  editable by the customer on their own contract or staff on any contract via
  `PATCH /contracts/{id}/iban`. Added to the admin's new-contract form and to
  an inline editor on the customer's own contract card.
  `ContractDocumentsPanel` (new shared component) renders the
  required-document checklist with upload/view/approve/reject, wired into
  both the customer's contract card (upload-only) and the admin's contract
  review modal (adds approve/reject with a note).
- **Demo data expanded to a real, fully-branching 12-level tree**: the live
  network had already reached depth 12 from earlier ad-hoc testing, but as
  two bare, single-file chains (2 people at most depths) — not a tree anyone
  could look at and understand. An additive script
  (`app/seed/expand_demo.py`, run once against the *existing* live
  organization, never a fresh seed) added 30 more agents broadening every
  level from 0 to 12 (new root branches, extra siblings at mid-tree and
  deep-tree nodes) and 50 more customers with contracts spread across the
  whole tree (old and new agents alike) in a realistic status mix — active,
  draft, submitted, under review, rejected, cancelled, and
  `DOCUMENTS_PENDING` (some with a partial document upload, some with none at
  all, to demonstrate the "missing documentation" flow end-to-end). Resulting
  live totals: 71 agents across 13 depth levels (0–12), 56 customers, 57
  contracts, 90 documents (85 approved, 5 still pending review). Every row
  this script creates is tagged for easy removal before production —
  `promoter_code` starting with `DEMO-`, customer email domain
  `@demo-expansion.lial`, contract notes containing the literal
  `[DEMO-EXPANSION]` — see `server-migration-guide.md` for the deletion
  queries keyed off these markers.
- **Network tree: click-through detail popup**. Every node in both the
  admin's org-wide tree and a promoter's own branch view now has a clickable
  name + info icon (propagated through `TreeNodeRenderer` via a new
  `onNodeClick` prop) that opens `NetworkNodeDetailModal`, showing: people
  below that node, levels below, contract counts by bucket (in progress,
  closed, rejected), total value created, and a per-contract table
  (customer, product, status, value). This reuses the existing
  `get_branch_summary`/`get_branch_contracts` service functions rooted at
  *whichever* node was clicked, not just the branch root — no new backend
  concept needed, since the existing ABAC check (`_assert_branch_access`)
  already permits any ancestor to query any descendant's branch. One
  genuinely new piece: **"provvigione presa da me per quel contratto"** — the
  commission the *specific viewing user* earned from each contract, which is
  different from that contract's total commission across every beneficiary
  in the multilevel plan. `get_branch_contracts()` now accepts an optional
  `viewer_agent_id` and returns a `my_commission_cents` field per contract
  (`null`, not `0`, when the viewer has no agent profile at all — e.g. an
  org admin browsing someone else's branch, who was never a commission
  beneficiary; distinguishing "not a beneficiary" from "earned zero" was
  deliberate). Verified live: a promoter viewing a contract 12 levels down
  their own tree correctly saw their own smaller cut (e.g. €25 of a €95
  total commission payout), while an org admin viewing the same contract saw
  `my_commission_cents: null`.
- Backend: 79 tests passing (was 65 at the end of Session 13 — new tests for
  the documents domain: required-document-types-per-customer-kind, upload +
  read-back, unknown-document-type rejection, approve/reject, presigned-URL
  properties, and org-scoping). Frontend: clean `tsc --noEmit`, clean
  `eslint`, clean `next build`. Verified live over HTTPS: the full
  document-upload → presigned-view → approve round trip (both as the
  uploading customer and as the reviewing admin), the private bucket
  rejecting every unsigned/public request, IBAN update from both the
  customer and admin side, the expanded 12-level tree's real counts via the
  live API, the tree popup's branch-summary/branch-contracts data for both
  an admin and a promoter viewer (including the `my_commission_cents`
  difference above), and that pre-existing isolation still holds — a
  customer still gets 403 on another customer's contract documents, a
  promoter still gets 403 on a branch they're not an ancestor of.

## Session 13 — 2026-07-26 (same day, continued) — Network tree bug fix, password reset, photo uploads (customer/promoter/product), promoter reassignment, security hardening, three real nginx/MinIO bugs found and fixed

Continuation of another large multi-part request. All items below were built,
tested, and verified live:

- **Real bug fixed -- network tree navigation**: `network/service.py::get_branch()`
  had no `ORDER BY` and the frontend (`branch-visualizer.tsx::buildTree()`)
  assumed the flat row list came back in pre-order traversal order to
  reconstruct the parent/child hierarchy. Postgres never guarantees that for a
  plain `WHERE id IN (...)`, so whenever it didn't, most of the tree silently
  failed to attach to its real parent -- exactly the reported symptom ("only
  see the first name, opening a level shows nothing"). Fixed by joining
  `network_nodes.direct_parent_agent_id` into `BranchMemberRead` as
  `parent_agent_id` and rebuilding the tree strictly from that field via a
  map, never row order. Also changed `TreeNodeRenderer` so each level starts
  collapsed by default (only the root/level-1 boundary starts open), giving
  real "open one level, then the next" navigation instead of one giant
  all-levels-expanded dump -- `forceOpen` still cascades for the admin's
  "espandi tutto"/search.
- **Referral share link display bug fixed**: the `/r/[code]` landing page read
  the `product` query param (a raw UUID) for "Offerta consigliata" display --
  the share button had always set BOTH `product` (id) and `product_name`
  (the actual name) but the landing page only ever read the former. Now shows
  the name prominently with the id small below, matching the "name
  prominent, id small below" rule applied everywhere else.
- **Password confirmation** added to the referral registration form
  (client-side match validation) and to the new reset-password form.
- **Password recovery, built end-to-end**: `password_reset_tokens` table
  (migration `0007`), `POST /auth/forgot-password` (always enumeration-safe)
  and `POST /auth/reset-password` (single-use, 60-min expiry, revokes every
  session on success), `/forgot-password` and `/reset-password` pages. Real
  SMTP delivery when configured (`core/email.py`, new `SMTP_*` settings);
  when not configured, the reset link is logged to the API process log only
  -- deliberately never to `audit_log` or anywhere a web-UI role could read
  it (that would let staff take over any account). Verified live: request →
  log fallback → reset → new password works → old password rejected → token
  correctly single-use.
- **Rate limiting** (`core/rate_limit.py`, Redis fixed-window per client IP,
  fails open) on login/register/forgot-password/reset-password. Required
  fixing uvicorn to run with `--proxy-headers --forwarded-allow-ips` so
  `request.client.host` reflects the real visitor behind nginx instead of
  nginx's own container IP -- previously every request looked like it came
  from the same source, silently defeating both rate limiting and
  `audit_log.ip_address`. Verified live: 11th login attempt in a window
  correctly 429s.
- **`/backend/docs` gating**: `ENABLE_API_DOCS` setting (default true, keeping
  today's behavior) controls whether `/docs`/`/redoc`/`/openapi.json` exist at
  all -- set false for a real production deployment.
- **Baseline nginx security headers**: `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Strict-Transport-Security`. No CSP
  yet (would need a nonce-based policy to not break Next.js's inline
  hydration scripts -- tracked as a follow-up, not guessed at).
- **Real bug found and fixed -- `/backend/*` returned 500 on every request**:
  discovered while verifying the docs-gating control actually worked.
  `location /backend/` combined a `rewrite ... break` with a VARIABLE in
  `proxy_pass` -- a genuine nginx bug (confirmed live, not theoretical),
  distinct from the prefix-stripping behavior a variable-based `proxy_pass`
  actually has (it forwards the ORIGINAL unstripped URI, which was the first,
  also-broken fix attempt). Resolved with a static `proxy_pass` target for
  this location specifically (trading the dashboard proxy's zero-downtime
  re-resolution for simplicity, acceptable since `/backend/` is developer
  convenience, not the app's own request flow).
- **Photo uploads, built end-to-end** for customers, promoters, and products:
  new public-read MinIO bucket `lial-media` (`core/storage.py`), separate
  from the private documents bucket, auto-created with its anonymous-read
  policy on API startup. Served to browsers via a new nginx `location
  /media/` proxying directly to MinIO (MinIO itself isn't internet-reachable).
  New `photo_url` columns on `customers`/`agent_profiles` (migration `0008`),
  upload endpoints (`POST .../photo`, multipart), a shared `PhotoUpload`
  React component (preview, fallback person icon when no photo), wired into
  the customer edit modal, a brand-new promoter edit modal (promoters were
  not editable in the admin UI at all before this), and the product edit
  modal (alongside the existing paste-a-URL field, with a live thumbnail
  preview).
  - **Two real infrastructure bugs found and fixed while wiring this up**:
    (1) `S3_ACCESS_KEY`/`S3_SECRET_KEY` in `.env` were NOT actually identical
    to `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` (same length, different
    values -- silently wrong since nothing had ever authenticated against
    MinIO with them before this session). (2) MinIO had no `MINIO_REGION`
    set (defaults to `us-east-1`) while the app signs requests for
    `eu-central-1`, breaking SigV4 signature verification regardless of
    credentials. Both fixed; documented in `server-migration-guide.md §8` so
    a fresh server setup doesn't reintroduce either.
  - The BFF's generic proxy route (`/api/proxy/[...path]`) needed a fix too:
    it unconditionally read every POST body as text and forced
    `Content-Type: application/json`, which would have corrupted a multipart
    upload's binary body and dropped its boundary. Now branches on the
    incoming content-type.
- **Admin: customer edit graphically improved** (photo upload section) and
  a working "Riassegna Promoter" control wired to a new
  `POST /customers/{id}/reassign-promoter` endpoint
  (`referral/service.py::reassign_customer_promoter()`) -- the customer
  keeps *some* promoter always; reassignment is rejected if there's no
  existing attribution to correct, or if the target is the same promoter
  already attributed. Writes an `attribution_corrections` row (a
  pre-existing, previously-unused schema table, same story as
  `customer_attributions` before Session 10).
- **Admin: customer view -- contract summary table** added (product, supply
  point, status color-coded green/amber/red/grey, expiry date), clicking a
  row expands an inline detail (created/activated dates, notes, id) --
  simpler than a second stacked modal, still gets to "click through to the
  contract's detail" without a dedicated contract-detail route that doesn't
  exist yet.
- Backend: 57 tests passing (was 46 at the end of Session 12 -- new tests for
  the `get_branch()` parent-linkage fix, the password reset flow, and
  promoter reassignment). Frontend: clean `tsc --noEmit`, clean `eslint`,
  clean `next build`. Verified live over HTTPS: photo upload for all three
  entity types (with the uploaded object confirmed publicly fetchable
  through nginx), promoter reassignment both directions with the audit trail
  confirmed in the database, the full password-reset round trip, and the
  rate limiter actually triggering a 429.

## Session 12 — 2026-07-26 (same day, continued) — Contract expiry/renewal, supply point labels, support tickets, network stats + drill-down, admin-to-promoter notes, font + section banners

Continuation of another large multi-part request. All items below were built,
tested, and verified live (not deferred):

- **Contract renewal bug fix**: `RENEWED` was a dead-end state in
  `contracts/state_machine.py` (empty `ALLOWED_TRANSITIONS` set) -- a renewed
  contract could never be renewed again the following year, suspended,
  cancelled, or left to expire. Since energy contracts renew every year of
  their life, not once, this was a real defect, found by reading
  `business-rules.md §Renewals` before writing any code. Fixed: `RENEWED` now
  has the same onward transitions as `ACTIVE`; `EXPIRED → RENEWED` also added
  (reviving a lapsed contract).
- **Contract term/expiry**: `product_versions.contract_duration_months`
  (nullable, no ORM-level default -- see the "real bug found by a test" note
  below), `contracts.activated_at`/`expires_at` (migration `0005`). Set/reset by
  `transition_contract()` on every entry into `ACTIVE`/`RENEWED`, computed via a
  stdlib `_add_months()` helper (no dateutil dependency). Existing live
  ACTIVE contracts backfilled from their real `contract_status_history`
  timestamp, not an approximation.
  - **Real bug found while writing the test for "product with no duration
    leaves expires_at null"**: the model had `mapped_column(..., default=12)`.
    SQLAlchemy's Python-side column default fires even when the ORM
    constructor is given an *explicit* `None` -- it can't distinguish "field
    omitted" from "field explicitly nulled" once the value reaches Core's
    insert-defaults processing. This would have silently turned every
    DIGITAL/PHYSICAL product's "no renewal" `None` into `12`. Fixed by
    removing the model-level default entirely; "12 unless told otherwise"
    now lives only in `ProductCreate`/`ProductVersionCreate` (the Pydantic
    layer, where omitted vs. explicit-null are still distinguishable).
- **Supply point labels**: `supply_points.label`, auto-computed from
  energy_type + address when not given explicitly (e.g. "Energia elettrica -
  Via Roma 12, Milano"), always editable after. Generalizes the "name
  prominent, id small below" rule that already applied to customers/products/
  network agents to the one remaining raw-ID display the user pointed out
  (POD/PDR codes shown bare).
- **Contract list enrichment**: `ContractRead` gained `product_name` and
  `supply_point_label` (denormalized, populated by a new
  `contracts/service.py::to_read_dicts()` bulk join) so every contract list in
  the app shows names, not raw UUIDs, without each caller re-deriving it.
- **Admin contract list**: expiry/renewal column with urgency color-coding
  (red if past due, amber if <30 days), year filter dropdown for "storico
  separato per anni".
- **New `support` domain**: `Ticket`/`TicketMessage` models (migration `0006`,
  which also seeds the new `tickets.create`/`tickets.respond` permissions and
  grants them to existing roles in the live DB -- a genuine data migration,
  not just schema). Customer/promoter open tickets and see only their own
  (`tickets.create`); staff see and reply to every ticket in the org
  (`tickets.respond`), and a staff reply on an `OPEN` ticket auto-transitions
  it to `IN_PROGRESS`. Replaced the previous fake "Supporto & Assistenza" form
  in the customer page (generated a random ticket number client-side, did
  nothing real) with the real thing.
- **Promoter/admin network + contract statistics**: `get_branch_summary()`'s
  `totals` gained `contracts_closed`/`contracts_rejected`/`contracts_pending`/
  `contracts_in_progress`/`levels_below`/`people_total`/`contracts_by_status`.
  New `get_organization_network_levels()` (whole-org headcount per depth-from-
  own-root -- no single root_agent_id exists for a whole org, unlike a
  promoter's branch) powers a new admin-only `GET /network/organization/levels`
  endpoint. Promoter "La mia Azienda" panel got a recharts bar chart + clickable
  per-level drill-down; admin overview got an analogous whole-company widget.
- **Admin notes surfaced to promoters**: `get_branch_contracts()` now also
  returns the latest non-null `contract_status_history.notes` per contract
  (`admin_note`) -- what an admin wrote when moving a contract to e.g.
  `DOCUMENTS_PENDING` now shows directly under that contract in the promoter's
  network-contracts table, folded into the "Contatta" mailto body too.
- **Font**: replaced Outfit with Inter (`next/font/google`) across the whole
  dashboard -- a more standard, professional admin/dashboard typeface.
- **Section header banners**: new reusable `SectionBanner` component, one
  small (h-20/h-24) themed decorative image per major tab across
  admin/promoter/customer dashboards (energy, customers, network, products,
  commissions, support), sourced from Wikimedia Commons (same method used
  earlier for product photos) with a dark gradient overlay for contrast.
  Purely decorative -- degrades silently if the image is slow/unreachable.
- Backend: 46 tests passing (was 14 at the start of this session -- 5 new test
  files/additions covering the renewal chain, expiry computation, supply point
  label defaults, the support ticket domain, and the network stats). Frontend:
  clean `tsc --noEmit`, clean `eslint`, clean `next build`. Verified live over
  HTTPS with real authenticated sessions (admin/promoter/customer demo logins)
  for every new endpoint.

## Session 11 — 2026-07-26 (same day, continued) — Promoter "azienda" view, referral sharing + invite-only registration, real contract creation form, product types

Large, multi-part user request. Scoped deliberately: built the concrete,
safely-implementable pieces in full (tested, verified live); explicitly
deferred the full PIN/email-verification registration refinement rather than
fake it, since this project has no email-sending infrastructure at all yet.

**Header/logo overlap bug (also user-reported).** Root cause: the top header
was a full-width block using left *padding* to visually clear the sidebar, but
its semi-transparent background still extended under the sidebar at `z-40`
(above the sidebar's `z-30`), covering the logo. Fixed with `margin-left`
instead of padding, so the header's box genuinely starts after the sidebar
instead of merely indenting its content.

**Promoter "azienda" dashboard (new default landing tab).** New backend
aggregations in `network/service.py`: `get_branch_summary()` (per-agent and
per-level contract-count/commission-total rollup across a promoter's whole
downline, using the existing branch/closure data -- no new tables) and
`get_branch_contracts()` (flat, contract-level rows linking customer name/
email, product name, status, and commission earned -- the "collegamento tra
cliente/prodotto/stato/guadagno" the request asked for). Both reuse the same
branch-ownership ABAC check as the existing `/branch` endpoint (factored into
a shared `_assert_branch_access()` helper). New `PromoterAziendaPanel`: KPI
cards, per-level table, per-agent table (contracts total/processed/in-progress/
problem, commission), and a contract list with a **Contatta** button
(`mailto:`, pre-filled subject/body for problem contracts) so a promoter can
act on "documenti mancanti" without leaving the page.

**Referral link sharing.** `promoter_codes`/`referral_events`/
`referral_sessions`/`customer_attributions` existed since Session 1 but had no
live write path beyond the public click-resolver -- orphaned tables. Added
`referral_service.get_or_create_promoter_code()` (reuses the agent's existing
`promoter_code` as the referral code, created lazily on first request) and a
new authenticated `GET /referral/mine` endpoint (on a **separate** router from
the public `GET /r/{code}` -- `/r/mine` would otherwise collide with
`/r/{code}` where `code="mine"`). `CustomerProductsPanel` gained an optional
`referralCode`/`organizationId` prop: when set, each product card gets a
**Condividi** button that copies a link straight to that product, pre-attributed
to the sharing promoter. The promoter dashboard header also has a generic
"Condividi il tuo link" button.

**Invite-only public registration.** New `POST /auth/register`
(`auth/service.py::register_with_referral()`): validates the referral code
*first* (before creating anything, so an invalid/expired code never leaves a
half-created account), then creates the User + role grant + Customer +
profile/company + `CustomerAttribution` in one transaction, one commit --
closed circuit enforced at the data layer, not just the UI ("nessuno può stare
senza promoter che lo invita"). New public page `/r/[code]` (reads `org` +
optional `product`/`product_name` query params) with a single-step
email+password+profile form, and two public (no session) BFF proxy routes.
**Explicitly not built**: PIN-via-email verification, forced profile
completion on first login, promotion memory across logins, multi-activation
with location choice -- this project has zero email-sending infrastructure
today, and faking "email sent" or skipping verification silently would be
dishonest; this is real, scoped follow-up work, not cut corners.

**Real contract creation form.** Previously four raw UUID text inputs typed
by hand. New `AdminCreateContractPanel`: toggle between an existing customer
(dropdown, then a dropdown of *that* customer's supply points) or a new one
(kind, fiscal code/VAT, first+last name or company name, email, mobile, PEC,
plus inline supply-point address fields -- creates the customer and supply
point via the existing endpoints, then the contract), a dropdown for the
offer (not a UUID), a dropdown for the promoter/venditore, and an optional
free-text note. `notes` added to `Contract` (new column, migration `0004`)
and `pec` added to `Customer` (same migration) -- both exposed end-to-end
(schemas, service, create form, edit form, detail popup).

**Product types.** `Product.energy_type` was `NOT NULL`, meaning every
product had to pretend to be an energy contract. Added `Product.product_type`
(`ENERGY_CONTRACT`/`DIGITAL`/`PHYSICAL`/`SUBSCRIPTION`, default
`ENERGY_CONTRACT` for every existing row) and relaxed `energy_type` to
nullable (migration `0004`, same one as notes/pec). Admin create/edit forms
show the energy-type field only when `product_type=ENERGY_CONTRACT`. Catalog
badges (admin grid, customer/promoter shop) show the right label for either
case.

**Tests.** 7 new tests, all against real Postgres: 5 for registration
(valid referral succeeds and attributes correctly, invalid code rejected with
no half-created account, duplicate email rejected, expired code rejected,
`get_or_create_promoter_code` is idempotent) and 2 for the branch aggregations
(contract counts/commission totals correct per agent, contract-level detail
correctly links customer/product/status/commission). Full suite: **40/40
passing**.

Verified live end-to-end over the real HTTPS deployment: full contract
creation (new customer → supply point → contract with notes) through the BFF
proxy; promoter `branch-summary`/`branch-contracts`/`referral/mine` through an
authenticated promoter session; the public `/r/{code}` page resolving a real
promoter code and a real registration completing (new user could log in
immediately after); header/logo fix present in rendered HTML.
`tsc`/`eslint`/`next build` clean, full backend test suite green, both images
rebuilt and redeployed.

## Session 10 — 2026-07-26 (same day, continued) — Expired-session crash fix, admin network tree, deep seed, product photos, customer view/edit

**Bug fix (user-reported: "se apro il sito mi dice rebuild pagina"):** `/admin`,
`/promoter`, `/customer` all threw Next.js's generic 500 error page for any
session older than 15 minutes (the access token TTL; no silent refresh yet).
`apiFetch()` throws on a non-2xx response and none of the three pages caught
it. Root cause confirmed live by forging a `Cookie: lial_session=...` header
carrying a token the API actually rejects with 401. Fixed with a new
`apiFetchOrRedirectToLogin()` that redirects to `/login` on 401 instead of
throwing -- first attempt also tried to clear the stale cookie, which threw a
*different* 500 ("Cookies can only be modified in a Server Action or Route
Handler" -- illegal from a plain Server Component render), caught while
testing the fix live and fixed by leaving the stale cookie in place (a
subsequent login just overwrites it).

**Admin network tree restored + rebuilt properly.** The admin dashboard had
no org-wide network view at all (only the flat `AdminPromotersPanel` table) --
Fase 5 from `admin-dashboard-plan.md`, not yet built, which is what the user
was actually missing ("non vedo più l'albero"). Extracted the tree-rendering
pieces from `branch-visualizer.tsx` into a shared `components/network-tree.tsx`
(`TreeNodeRenderer`, `LevelLegend`, depth-color logic) and built a new
`AdminNetworkPanel` on top of it: fetches the existing org-wide
`GET /network/agents` list, builds a full forest client-side from
`direct_parent_agent_id` pointers (multiple independent root branches, not
just one), with search/highlight and expand-all/collapse-all controls (starts
collapsed for a big org tree, matching "navigare la rete nei vari livelli").
New "Rete Commerciale" tab + a quick-link button on the overview panel.

**Network depth extended to 12 levels with real agents at every level.** The
existing demo network topped out at depth 5 and was a pure linear chain (one
agent per level, no branching) -- neither satisfied "albero a 12 livelli" nor
"ogni livello deve avere uno o più clienti". Seeded 19 new agents directly via
`network_service.create_agent()` (same code path the API uses): one sibling
added at each of levels 1-5 (so those levels have 2+ agents instead of 1), and
7 new levels (6-12) added below the existing leaf, 2 agents per level. Verified
live: `network_closure` now shows depth 0-12, every level with ≥2 agents,
41 agents total org-wide (was 22).

**Product renames + real photos.** "Gas Semplice" -> "Luce Family", "Luce
Flex" -> "Luce Company" (both via the existing `PATCH /products/versions/{id}`
-- note: this only renames the display name, the underlying `energy_type`
column on `Product` has no update endpoint, so "Luce Family" is still
technically a GAS-typed product under the hood; flagged, not silently
pretended otherwise). All 5 active products got a real, free, theme-matched
photo sourced from Wikimedia Commons (public domain / CC-licensed, no API key
needed, verified reachable before use): glowing Edison bulbs for Luce
Semplice, a solar-roofed house for Luce Family, a glass office tower for Luce
Company, an offshore wind farm for Luce Green 100%, a mixed solar+wind
building for Energia Circolare PMI.

**Customer admin CRUD: view/edit icons.** `AdminCustomersPanel` rows gained a
"Mostra" icon (popup with full customer detail -- addresses, supply points,
fiscal data, via the existing `GET /customers/{id}`) and a "Modifica" icon
(edit form via the existing `PATCH /customers/{id}`, previously wired
backend-side with no UI). Deliberately did NOT add a delete action: no soft-
delete concept exists on `Customer` (no status column, unlike `AgentProfile`/
`Product`) and no delete endpoint exists; a real delete would either need a
new schema concept or risk orphaning `contracts`/`supply_points` FKs --
inventing one silently would violate "no fake buttons without real
functionality." Verified RBAC already correctly restricts `customers.update`
to ADMIN/BACK_OFFICE_OPERATOR-tier roles -- PROMOTER/TEAM_LEADER only have
`customers.read`/`customers.create`, matching "solo amministratore può
editare" (no code change needed there, confirmed by reading `rbac/models.py`).

Verified live end-to-end over the real HTTPS session for every piece above.
`tsc`/`eslint`/`next build` clean.

## Session 9 — 2026-07-26 (same day, continued) — Names above IDs, product edit + VAT, shop as customer home

User-driven: lists showing raw UUIDs must show the real associated name above
the (still-present, small) id; the shop needs real electricity examples and a
proper create/edit flow with photo/price/VAT; the customer's home should be
the shop, not the contract list.

- [x] Admin contract list and the transition modal now show the customer's
  real name (fetched via a `customers` lookup, same pattern as
  `AdminPromotersPanel`'s sponsor lookup) with the UUID kept small underneath,
  instead of two raw UUID columns.
- [x] Customer's own contract cards now show the product's real name (from a
  `product_version_id -> name` lookup built off `GET /products`) as the
  heading, with the contract UUID demoted to small mono text below it.
  `AdminCustomersPanel`/`AdminPromotersPanel` already led with real names
  (verified, no change needed).
- [x] Backend: `ProductVersion.tax_configuration` (existing, previously-unused
  JSONB column) now carries a `vat_percentage`, exposed as a top-level field
  via `ProductVersionRead.from_version()` (a `from_attributes=True` model
  can't compute a field out of a JSONB blob, so this replaces `model_validate`
  at all 4 call sites) and accepted on create/update. No migration needed --
  the column already existed, unused.
- [x] `AdminProductsPanel` gained a real Edit flow (`PATCH
  /products/versions/{id}`, already existed backend-side but had no UI) --
  same form fields as create, refactored into a shared `ProductFormFields`
  component. VAT % field added to both create and edit.
- [x] Shop now has 3 real, distinct electricity offers (`LUCE-STD`/"Luce
  Semplice", plus two new ones created live via the API: `LUCE-FLEX`/"Luce
  Flex" -- indexed/variable rate, and `LUCE-GREEN`/"Luce Green 100%" --
  renewable, 12-month fixed price). The `TEST-SMOKE` product created as a
  throwaway artifact during Session 8's live verification was retired
  (`status="RETIRED"`) so it no longer appears in admin or customer views.
- [x] Customer app: "Shop" (the products panel) is now the first nav item and
  the default landing tab, per "l'home dei clienti deve mostrare lo shop" --
  previously "I miei Contratti" was both first and default.

Verified live: customer session shows exactly 3 ACTIVE electricity products
with correct prices/VAT through the real BFF proxy path; admin session's
`/customers` lookup returns real display names that the frontend map resolves
correctly. `tsc`/`eslint`/`next build` clean, dashboard rebuilt and redeployed.

## Session 8 — 2026-07-26 (same day, continued) — Commission-trigger audit + fixes, admin quick-links, orange brand pass

Two independent pieces of work, done back to back.

**1. Full audit of "paid contract → commission distribution", per explicit user
request.** Report: `docs/paid-contract-commission-audit.md`. Method: read the
actual running code first, then compared against `docs/business-rules.md` and
`docs/commission-engine-specification.md` to find real gaps rather than assuming
the docs were accurate.

Confirmed correct (no changes needed): the producer's ancestor chain is built
from real `network_snapshot_nodes` data frozen at activation (no placeholders);
all N levels are walked (no hardcoded cap -- the finite 12-rank ladder makes any
cap moot); the entrepreneurial-difference algorithm is incremental and correctly
tested (7 unit tests, all green); `PaymentConfirmed` (the `PAID` transition) does
**not** trigger commission calculation, only `ContractActivated`/`ContractRenewed`
do -- this matches `business-rules.md` line 55-56 exactly and is intentional, not
a bug.

Five real problems found and fixed:
- [x] **Problem #1 (critical)**: `create_contract()` accepted `producer_agent_id`
  from the client with zero validation. An invalid/nonexistent id produced an
  empty network snapshot, which made `run_calculation_for_contract()` silently
  `return None` -- no error, no record, no audit entry, event marked processed
  as if nothing was wrong. A contract could activate and pay nobody, forever,
  with no trace. Fixed: `create_contract()` now verifies the agent exists,
  belongs to the organization, and is `ACTIVE`, raising `InvalidProducerAgentError`
  (→ HTTP 400) otherwise. Defense in depth: an empty ancestor chain at
  calculation time (any other cause) now writes a `CommissionCalculation` with
  `status="FAILED"` plus an audit log entry instead of silently skipping.
- [x] **Problem #2 (serious)**: `process_pending_outbox_events()` had no
  try/except around the calculation call -- one failing event (a "poison pill")
  aborted the whole batch, blocking every *other* unrelated contract's
  commissions too, retried (and re-blocking) every minute forever. Fixed: each
  event is now processed in isolation (event data extracted to plain values up
  front, since a rollback after a failure expires the whole session's identity
  map and a later bare attribute read on another event's ORM object would itself
  crash with `MissingGreenlet` -- hit this for real while writing the isolation
  test, see below); a failure is logged, audited, and the loop continues.
- [x] **Problem #3 (medium)**: the `(contract_id, trigger_event_id)` idempotency
  check in `run_calculation_for_contract()` was application-level only
  (SELECT-then-INSERT), with a real race window on overlapping dispatches.
  Fixed: DB-level `UniqueConstraint` (migration `0003`) plus explicit
  `IntegrityError` handling at the actual insert point (the `db.flush()` right
  after `db.add(calculation)`, not just the later `db.commit()` -- the first
  attempt at this fix only wrapped the commit and missed the real conflict
  point, caught by the concurrency test below).
- [x] **Problem #4 (medium)**: nothing surfaced a contract stuck at `PAID` or
  `ACTIVATION_PENDING` -- money collected, commissions not yet triggered, and
  two more manual clicks required with no prompt. Fixed: the admin "Richiede
  attenzione" widget now also flags these, with a 2-day threshold (shorter than
  the 7-day review-queue threshold, since money already changed hands) and a
  distinct reason message.
- [x] **Problem #5 (low)**: `commission-engine-specification.md`'s test matrix
  claimed the 33% branch-cap rule was "Implemented now" -- verified false:
  `apply_branch_cap()` exists and is unit-tested in isolation but is never
  called from `calculate_chain()`/`run_calculation_for_contract()`. Corrected the
  doc. Not wired in this session: `business-rules.md` marks the cap percentage
  as PLACEHOLDER and `open-questions.md` #6 leaves the "qualifying group
  production" denominator undefined -- implementing against a guessed
  definition would trade an honest gap for a silently wrong one.

Tests added (all against a real Postgres, not mocks):
`apps/api/tests/test_contract_producer_validation.py` (4 tests: unknown agent,
cross-org agent, non-active agent, valid agent happy path) and 3 new tests in
`test_commission_engine_integration.py` (empty-chain → FAILED record, not
silent skip; dispatcher isolates a poisoned event from a healthy one in the
same batch; a **real** concurrency test using two independent DB connections
racing via `asyncio.gather` -- not the shared savepoint-rollback fixture, which
cannot exercise genuine concurrency -- confirmed the DB constraint actually
fires under a real race and is handled gracefully). Fixed one pre-existing
regression from Session 7 along the way: `test_network_isolation.py` still
unpacked `network_service.get_branch()`'s old tuple return shape. Full suite:
**33/33 passing.**

Also fixed live, not just in tests: reused the Session 7 nginx fix to verify
`create_contract` now rejects a bogus producer with a real HTTP 400, then ran a
full contract through every transition to `ACTIVE` against the live API and
confirmed real `PERSONAL_TOKEN`/`ENTREPRENEURIAL_DIFFERENCE` movements landed
in the ledger for the right agents.

**2. Admin quick-links + orange brand pass (user-requested, same session).**
- [x] `AdminOverviewPanel` gained a row of large "pulsantoni" (Contratti, Nuovo
  Contratto, Clienti, Promoter, Prodotti) above the KPI cards, wired to the same
  tab-switching the sidebar uses -- the most common destinations are now one
  click away without hunting in the sidebar, per explicit user request.
  Also caught two leftover violet/cyan spots in this file (the time-filter
  active state, the chart line/bar colors) that Session 7's brand pass had
  skipped, and remapped the two former-cyan KPI card accents to sky (not amber)
  to avoid colliding with the "In attesa di approvazione" card, which was
  already amber.

## Session 7 — 2026-07-26 (same day, continued) — Network tree readability, customer marketplace, nginx root-cause fix

Three user-driven fixes, done live between Fase 2 and Fase 3 of the admin
dashboard plan (not itself a numbered phase):

**Network tree: real names + per-level colors.** `GET
/network/agents/{id}/branch` returned only `(agent_id, depth)`, so the tree/
table UI rendered raw truncated UUIDs -- unusable for a non-technical user
trying to read their own downline. The endpoint now joins `agent_profiles`/
`ranks` and returns `display_name`, `promoter_code`, `status`, `rank_code`.
`BranchVisualizer` shows "Nome C." (given name + surname initial) per node and
gives each depth (0=root, 1-12=career-plan levels) a distinct color (left
rail + badge chip) with a legend at the top, so levels are recognizable at a
glance. `BranchTable` got the same underlying fields.

**Customer-facing product catalog ("ecosystem").** The admin could create
products/versions but customers had no way to see them -- the customer app
only had "I miei Contratti" and "Supporto". Added `image_url` to
`product_versions` (migration `0002_product_version_image_url`, first
migration since the initial schema) and a `ProductCatalogRead` schema that
pairs each product with its current version's display fields (name,
description, photo, price) so `GET /products` serves both the admin catalog
grid and the new customer marketplace from one call, no N+1 detail fetch.
`products.read` granted to the `CUSTOMER` role (previously only
`contracts.read`/`documents.download`) -- patched into the live DB the same
way as prior new-permission sessions. New `CustomerProductsPanel` ("Prodotti
& Servizi" tab): ecommerce-style cards, photo/name/description/price, filtered
to `ACTIVE` products only. Admin's `AdminProductsPanel` gained a photo-URL
field on the create form and the same card styling. No purchase/checkout flow
was added -- this is read-only catalog visibility for an already-registered
customer, distinct from the still-deferred Fase 10 (public, invite-only
marketplace for anonymous visitors).

**Real bug found and root-cause fixed: nginx stale upstream IP on container
recreation.** After rebuilding/recreating the `dashboard` container, nginx
kept proxying to the *old* container IP (`connect() failed (111: Connection
refused)`, 502s on every route) until manually reloaded -- `upstream {
server dashboard:3000; }` blocks resolve the hostname once, at nginx
startup/reload, and never again. This is the same class of bug as Session 3's
"Docker bind mount points at an orphaned inode," just for DNS instead of
filesystem, and it will keep recurring on every future deploy that recreates
a container. Root-cause fixed instead of just working around it this time:
`infrastructure/nginx/nginx.conf` now uses `resolver 127.0.0.11 valid=10s;`
(Docker's embedded DNS) with a `set $upstream ...; proxy_pass
http://$upstream;` pattern instead of static `upstream {}` blocks -- this
forces nginx to re-resolve the container's current IP on every request
(bounded by the 10s TTL), so container recreation no longer requires a manual
`nginx -s reload`. Verified by force-recreating the dashboard container (IP
changed `172.18.0.7` -> `172.18.0.6`) and confirming the live HTTPS site kept
working with zero nginx intervention.

Verified end-to-end: live curl with real JWTs (branch endpoint returns real
names, CUSTOMER role can read `/products`, other roles still can't reach
admin-only catalog actions), full browser-session path over HTTPS for both
the network tree and the customer marketplace, `tsc`/`eslint`/`next build`
clean, alembic migration applied to the live DB before the new api image was
deployed.

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
