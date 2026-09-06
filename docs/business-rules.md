# Business Rules

Status: no source document (`Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf`)
was present in the repository at the time this was written. Every numeric threshold,
percentage and formula below is a **placeholder** used to make the system runnable and
testable. None of it should be treated as the real Lial Energy commercial policy until
confirmed. Every placeholder is also listed in `open-questions.md` with the exact
config location to change once real figures are available.

## Money

- All monetary amounts are stored as integer cents (`*_cents BIGINT`) in the database
  and as `Decimal` in Python at the API boundary. `float` is never used for money,
  percentages, or any economic quantity.
- Currency is EUR only in v1; a `currency` column exists on ledger rows for future
  multi-currency support but is not exercised.
- Rounding: half-up to the nearest cent, applied only at the point a figure is
  persisted to `commission_movements` — intermediate calculation steps keep full
  precision (`Decimal` with explicit context), see `commission-engine-specification.md`.

## Ranks / career plan (PLACEHOLDER — see open-questions.md #1)

Configured via the `ranks` table, not hardcoded. Seed values used for demo/tests:

| code | level | personal_token_cents | notes |
|---|---|---|---|
| S1 | 1 | 4000 | base seller |
| S2 | 2 | 4500 | |
| S3 | 3 | 5000 | |
| TL1..TL4 | 4-7 | 5500-7000 | Team Leader tiers |
| MD1..MD5 | 8-12 | 7500-9500 | Manager Director tiers |

`single_branch_cap_percentage` defaults to 33% for every rank (see "Regola del 33%"
below) but is per-rank, per-plan-version configurable.

### Rank promotion progress (PLACEHOLDER, added Session 15)

`personal_volume_threshold_cents` / `group_volume_threshold_cents` were present
in the schema since the very first migration but always left at 0 (never
populated, never read) until the user explicitly asked for real numbers
("procurati quei criteri qualifica e falli tu" -- go get those qualification
criteria and set them yourself) rather than leave the feature unbuilt.
Migration `0010` and `seed/ranks.py` seed the figures below; they are still a
placeholder pending the real `Allegato_A_Piano_Carriera_Regolamento_
Provvigionale.pdf` (see `open-questions.md #1`) -- reasonable, ascending,
demo-scale numbers picked by the assistant on explicit request, not confirmed
Lial Energy policy.

| code | personal_volume_threshold_cents | group_volume_threshold_cents |
|---|---|---|
| S1 | 0 | 0 |
| S2 | 1500 | 1500 |
| S3 | 3000 | 4000 |
| TL1 | 3000 | 8000 |
| TL2 | 3000 | 12000 |
| TL3 | 3000 | 16000 |
| TL4 | 3000 | 20000 |
| MD1 | 3000 | 25000 |
| MD2 | 3000 | 30000 |
| MD3 | 3000 | 35000 |
| MD4 | 3000 | 40000 |
| MD5 | 3000 | 45000 |

`GET /network/agents/{agent_id}/rank-progress`
(`commissions/services/rank_progress.py`) compares an agent's CUMULATIVE
("lifetime", not evaluated over `evaluation_window_months` -- that column
remains unused, a separate not-yet-built axis of this same placeholder)
contract value on `ACTIVE`/`RENEWED` contracts against the NEXT rank's
thresholds: `personal_volume_cents` is what the agent personally produced;
`group_volume_cents` is the same sum across their entire downline including
themselves (same descendant lookup as `get_branch_summary`). Surfaced as two
progress bars in the promoter's own "La mia Azienda" panel and in the admin's
per-promoter "Apri Rete" drill-down (same shared component). An agent already
at the top rank (no higher `level` exists for their `rule_version`) shows
"qualifica massima raggiunta" instead of a bar.

### Automatic monthly rank evaluation (PLACEHOLDER, added Session 20)

Separate axis from the progress display above, and from the same unconfirmed
placeholder thresholds: `commissions/services/rank_evaluation.py` actually
**writes** `AgentProfile.current_rank_id`, both up and down, instead of just
displaying progress toward it. Explicit user decisions behind this design,
pending the real `Allegato_A_...Regolamento_Provvigionale.pdf`:

- **Single-calendar-month window, uniform for every rank** -- not the
  cumulative lifetime total `rank_progress.py` uses, and not a per-rank
  rolling window via `evaluation_window_months` (still unused). Every ACTIVE
  agent's personal and group volume is recomputed from scratch for one
  month, and the rank ladder (`ranks` rows with `valid_to IS NULL` for the
  org) is walked to find the highest rank whose thresholds are both met.
- **Promotes AND demotes**: the rank is always realigned exactly to that
  month's production in either direction -- an agent who produced nothing
  that month can drop all the way back to the floor rank even after a strong
  track record in prior months. There is no rolling average or grace period.
- Celery Beat (`celery_app.py`, `monthly-rank-evaluation`) runs this on day 1
  of each month at 02:00 UTC for every organization, evaluating the calendar
  month that just closed (`previous_calendar_month()`). An admin holding
  `commissions.evaluate_ranks` (SUPER_ADMIN/ORGANIZATION_ADMIN only, same
  restriction as `network.approve`) can also trigger the identical logic on
  demand via `POST /commissions/rank-evaluation/run` (optional `?month=
  YYYY-MM`, the admin promoter panel's "Valuta gradi ora" button) -- useful
  if the scheduled run needs to be re-run or previewed. Every change is
  recorded in `agent_rank_history` (`calculation_source` AUTOMATIC or
  MANUAL) and `audit_log`, and the affected agent gets an in-app
  notification.

## Contract state machine

```
DRAFT → SUBMITTED → DOCUMENTS_PENDING → UNDER_REVIEW → APPROVED
      → PAYMENT_PENDING → PAID → ACTIVATION_PENDING → ACTIVE
ACTIVE → SUSPENDED → ACTIVE
ACTIVE → CANCELLED
ACTIVE → EXPIRED
ACTIVE → RENEWED
RENEWED → SUSPENDED / CANCELLED / EXPIRED / RENEWED   (a renewed contract is still
                                                        in force -- it renews again
                                                        every subsequent term, not once)
EXPIRED → RENEWED / CANCELLED                          (a lapsed contract can be revived)
any pre-ACTIVE state → REJECTED
```

Only the transitions enumerated in `apps/api/app/domains/contracts/state_machine.py`
are permitted; every other transition raises `InvalidTransitionError`. Every transition
is recorded in `contract_status_history` with actor, reason, and correlation id, and
emits a domain event (`ContractSubmitted`, `ContractApproved`, `PaymentConfirmed`,
`ContractActivated`, `ContractCancelled`, `ContractRenewed`).

**Rule**: creating a contract (`DRAFT`/`SUBMITTED`) never generates a commission.
Commissions are generated exactly once, when a contract transitions into `ACTIVE`
(see `commission-engine-specification.md §Trigger`).

**Term / expiry**: entering `ACTIVE` or `RENEWED` sets `contracts.activated_at` to
that moment and computes `contracts.expires_at` as `activated_at +
product_versions.contract_duration_months` (12 by default for an energy contract;
`NULL` for a one-off `DIGITAL`/`PHYSICAL` product with no renewal concept). Every
renewal restarts both fields from the renewal's own timestamp — `expires_at` is never
retroactively recomputed if the product version's duration later changes, matching the
"frozen at the moment it happens" pattern used for network snapshots and commission
calculations elsewhere in this document.

**Who can move a contract through this pipeline (confirmed, then extended,
Session 29)**: `PATCH /contracts/{id}/status` (manual, per-hop transitions)
still requires `contracts.review`, held by
ADMIN/BACK_OFFICE_OPERATOR/SUPER_ADMIN/ORGANIZATION_ADMIN, **never** by
CUSTOMER or PROMOTER (see `rbac/models.py`'s `DEFAULT_ROLE_PERMISSIONS`) --
a customer still cannot approve or activate a contract by taking a status-
transition action directly. What changed: a customer CAN now originate and
carry a Lial Energy contract most of the way there themselves, through a
dedicated self-service path -- see "Self-service contract activation"
below. The two surfaces coexist: `POST /contracts` (staff, any producer)
and `POST /contracts/mine` (self-service, own account only, own referring
promoter only) both land on the exact same `Contract` row shape and the
exact same state machine.

### Self-service contract activation ("Attiva Contratto", Session 29) {#contract-self-service}

Per explicit request, a customer can now activate a Lial Energy (`category
= INTERNAL`) product without any promoter/admin action to get it started:

- **`POST /contracts/mine`** (`contracts/router.py::create_my_contract`,
  no special permission -- `get_current_user` only, same "self-checkout,
  own account only" shape as `POST /orders/mine`): takes a
  `product_version_id` plus the supply-point details (address, POD/PDR,
  meter number) collected by the new `contract-activation-wizard.tsx`.
  `contracts/service.py::create_contract_self_service`:
  1. Resolves the customer's own record from `current_user.user_id`.
  2. Rejects anything that isn't an `INTERNAL` product (DROPSHIPPING/
     PARTNER products go through `orders`, never here).
  3. Resolves the commission producer from the customer's own referral
     attribution (`_resolve_referring_agent_id_for_customer` -- same
     `CustomerAttribution`→`PromoterCode` lookup "lavora con noi"
     auto-activation uses) -- there is no self-service way to pick a
     different one; registration being invite-only is exactly what
     guarantees this attribution always exists. No attribution found ->
     `SelfServiceContractError`, loudly, rather than silently attributing
     to nobody and breaking commissions later.
  4. Creates the `SupplyPoint`/`Address` (reusing
     `customers/service.py::add_supply_point` directly -- bypassing its
     normal `customers.update`-gated router, the same "call the service,
     skip the staff-only endpoint" pattern used elsewhere for self-service).
  5. Creates the `Contract` (`DRAFT`) and immediately transitions it
     `SUBMITTED` → `DOCUMENTS_PENDING` -- self-service has no "save as
     draft, decide whether to send it later" step the way a promoter/admin
     building one up by hand does.
- The customer then uploads the required documents through the same
  `ContractDocumentsPanel` every contract already used (no new upload
  mechanism) -- embedded directly in the wizard's second step, and always
  available again later from "I miei Contratti".
- **Auto-advance to `UNDER_REVIEW`** (`documents/service.py::
  upload_document` → `_maybe_advance_to_under_review`): once every required
  document type for the contract's customer kind has at least one uploaded
  document (any status -- this only means "the customer is done", not "a
  human already approved them"), the contract advances itself
  `SUBMITTED|DOCUMENTS_PENDING` → `UNDER_REVIEW` with no staff action. Not
  self-service-specific: a staff-created contract gets the identical
  courtesy advance once its documents are all in.
- **Two staff clicks left, by explicit product decision** (the user was
  asked: auto-approve documents entirely, or keep one human check before
  payment -- chose the latter): `contracts/service.py::transition_contract`
  gained `AUTO_CASCADE_AFTER = {"APPROVED": "PAYMENT_PENDING", "PAID":
  "ACTIVATION_PENDING", "ACTIVATION_PENDING": "ACTIVE"}` -- every hop is
  still a real, individually audited `transition_contract()` call (network
  snapshot, outbox event, `ContractStatusHistory` row, all per-hop, exactly
  as if a human had clicked each one), just chained automatically. So:
  - Staff clicks **"Approva"** (`UNDER_REVIEW`→`APPROVED`) after actually
    looking at the uploaded documents -- the contract lands in
    `PAYMENT_PENDING` without a second click.
  - Staff clicks **"Conferma pagamento"** (`PAYMENT_PENDING`→`PAID`) once
    the initial-fee bank transfer arrives -- the contract cascades through
    `ACTIVATION_PENDING` straight into `ACTIVE` (which is exactly the hop
    that enqueues the `ContractActivated` event and triggers commission
    calculation, unchanged from before).
  - This cascade is general, not gated to self-service-originated
    contracts -- a staff-created contract gets the same two-click path.
  - The admin contracts panel's status-transition dropdown needed **no
    changes**: it already only ever offers the next state-machine-valid
    target for a manual click; the cascade happens server-side, so picking
    "APPROVED" there simply comes back already at `PAYMENT_PENDING`.

## Commercial network rules

- No cycles, no self-parenting, no duplicate active edges, no cross-organization
  edges. Enforced in `network` domain service before any closure-table write.
- Every move of an agent to a new parent is a single DB transaction: update
  `network_nodes.direct_parent_agent_id`, insert a closed-off `network_edges` row and
  a new one, recompute affected `network_closure` rows, insert
  `network_assignment_history`, write an audit row, invalidate branch-count caches.
  Moves require `requested_by`; `approved_by` is required unless the mover has
  `network.manage` and self-approval is explicitly allowed for that role (PLACEHOLDER —
  see open-questions.md #2).
- A contract's commercial chain is frozen at activation via `network_snapshots` /
  `network_snapshot_id` on the contract. Subsequent moves of any agent in that chain
  never retroactively change attribution, past calculations, or past ledger entries.

### New promoter suggest-then-approve workflow (added Session 17)

Every new collaborator, however they're created, only ever gets SUGGESTED --
never immediately live:

- `POST /network/agents` (an ADMIN adding a promoter anywhere in the org
  tree) and `POST /network/agents/recruit` (a promoter enrolling their own
  direct collaborator) both now create the agent with
  `status = PENDING_APPROVAL`, not `ACTIVE`.
- A `PENDING_APPROVAL` agent already exists and is visible in the network
  tree (it's a real row, a real node) but cannot be used as a contract
  producer -- `contracts/service.py::create_contract()` already rejected any
  non-`ACTIVE` producer before this feature existed, so no new guard was
  needed there; the approval workflow rides entirely on a check that was
  already correct.
- Only `network.approve` holders can turn a suggestion into a real
  collaborator: `PATCH /network/agents/{id}/approve` (→ `ACTIVE`) or `PATCH
  /network/agents/{id}/reject` (→ `TERMINATED`, with an optional reason kept
  on the row, never a hard delete). `network.approve` is granted only to
  `SUPER_ADMIN`/`ORGANIZATION_ADMIN` -- the "amministratore principale" the
  user asked for -- deliberately NOT to a plain `ADMIN`, who already holds
  `network.manage` (can suggest) but not `network.approve` (cannot confirm
  their own suggestion). Re-approving/re-rejecting an already-decided agent
  is rejected (`AgentApprovalError`), not silently accepted.
- Both creation paths and both approval outcomes fire a notification (see
  `database-model.md §7`) -- `PROMOTER_APPROVAL_REQUESTED` to every
  `network.approve` holder when something needs a decision,
  `PROMOTER_APPROVED`/`PROMOTER_REJECTED` back to the suggested agent's own
  `user_id` if they already have a login.

## Entrepreneurial Difference ("Differenza Imprenditoriale")

Defined as the difference between the personal token that a given rank would earn on a
contract and the amount already recognized to the rank(s) below it in the same
ascendant chain for that same contract. Walking the chain from the producer upward:

```
already_distributed_cents starts at producer's own personal_token_cents
for each ascendant beneficiary (by increasing distance):
    if beneficiary.rank.personal_token_cents > already_distributed_cents:
        entrepreneurial_difference_cents = beneficiary.rank.personal_token_cents - already_distributed_cents
        already_distributed_cents = beneficiary.rank.personal_token_cents
    else:
        entrepreneurial_difference_cents = 0
```

This guarantees the same differential is never paid twice up the chain — each
ascendant is only credited the marginal amount their rank adds over what has already
been recognized below them. See `commission-engine-specification.md` for the full
algorithm including the 33% cap and Energia Circolare handling.

## Commission payment tracking (added Session 16)

`commission_movements.status`/`paid_date` existed since the very first migration
but nothing ever set anything other than `ACCRUED` -- the admin dashboard's
"Provvigioni pagate" KPI always showed €0,00 because there was no code path
that could ever produce a `PAID` row. `PATCH
/commissions/movements/{id}/pay` (admin-tier only, `commissions.approve`)
is the missing write path: transitions one movement `ACCRUED -> PAID`, stamps
`paid_date`, and writes an audit row. Re-paying an already-`PAID` movement is
rejected (`CommissionPaymentError`), not silently accepted -- this is a
manual "I sent the bank transfer" confirmation per movement, not a batch
payroll run; there is no bulk-pay-everything-for-this-promoter action yet
(a reasonable next iteration once real payout batching requirements exist).

### Admin commission traceability (`GET /commissions/movements`)

Every `CommissionMovement` already had a matching `CommissionCalculationStep`
row (contract → calculation → per-beneficiary step, computed at activation
time by `run_calculation_for_contract`) carrying `rank_at_calculation`,
`base_amount_cents`, `already_distributed_cents`,
`entrepreneurial_difference_cents`, and a human-readable `explanation` string
-- none of it was ever exposed through any endpoint before this. The new
endpoint (admin-tier only -- it is org-wide, unlike `commissions.read_branch`
which `TEAM_LEADER`/`PROMOTER` also hold for their own branch, so it cannot
reuse that permission) joins all of this together per movement: which
contract, which customer, which promoter earned it, their depth below the
contract's producer (`network_snapshot_nodes.depth`, frozen at activation --
0 is the producer themselves), their rank AT calculation time vs. their rank
NOW, and the full breakdown of how the amount was derived. Surfaced in the
admin "Provvigioni" tab (`admin-commissions-panel.tsx`) as an expandable
ledger row per movement, plus `GET /commissions/movements/by-level`
(`commissions/services/admin_ledger.py::get_commission_totals_by_level`) for
the per-network-level rollup (contracts / revenue / commission generated at
each depth).

## Regola del 33%

No single first-level branch under a beneficiary may contribute more than
`single_branch_cap_percentage` (default 33%, PLACEHOLDER) of that beneficiary's
qualifying group production for rank-evaluation and volume-based bonus purposes.
Excess production from one branch beyond the cap is excluded (not moved to another
branch, not carried over) from that evaluation period's eligible total. This is
implemented as an isolated, independently testable policy —
`apps/api/app/domains/commissions/policies/branch_cap.py` — not inlined into the main
calculator, so it can be unit tested against the matrix in
`commission-engine-specification.md §33% rule test matrix` without invoking the full
engine.

## Energia Circolare (PLACEHOLDER — see open-questions.md #3)

Treated in v1 as a product flag (`products.code` / `product_versions` metadata) that
can carry its own `commission_plan_version_id`, so Energia Circolare contracts can use
different rules without touching the shared calculator code. No Energia-specific bonus
formula is implemented yet — only the extension point.

## Renewals & reversals

- A renewal is a status transition on the **same** contract row (`ACTIVE`/`EXPIRED` →
  `RENEWED`, or `RENEWED` → `RENEWED` for the year after that), not a new contract --
  see "Term / expiry" above for how `activated_at`/`expires_at` are recomputed each
  time. It is also a new `contract_events` row of type `RENEWED` plus a new commission
  calculation; it does not mutate the original calculation or its movements.
- A reversal ("storno") never deletes or edits a prior `commission_movements` row. It
  creates a new movement with `movement_type = REVERSAL`, linked via
  `commission_reversals.original_movement_id`, carrying a negative amount, an
  explanation, and the recovered period. Formula for partial-period recovery
  (PLACEHOLDER — see open-questions.md #4):
  `refund_cents = original_amount_cents * remaining_months / total_contract_months`.

## Support tickets

- Anyone opening a ticket (a `CUSTOMER` or `PROMOTER`) can only ever see and reply to
  their **own** tickets -- there is no shared inbox between a customer and the
  promoter who referred them. Staff (any admin-tier role with `tickets.respond`) sees
  every ticket in the organization and can reply to any of them.
- `Ticket.opened_by_role` and `TicketMessage.author_role` are snapshots taken at
  creation time, not derived from the user's current roles at read time -- the same
  "frozen at the moment it happens" rule used for network snapshots and commission
  calculations. A later role change never rewrites who a past ticket/message
  "belongs to".
- A staff reply on an `OPEN` ticket automatically moves it to `IN_PROGRESS` -- the
  ticket owner should see "someone is looking at this" without the admin having to
  remember a separate status update. Only staff (`tickets.respond`) can set
  `RESOLVED`/`CLOSED`; the ticket owner can only imply it's solved via a message.
- A ticket can optionally reference a `contract_id`, letting a customer or promoter
  open a ticket directly "about this contract" instead of the admin having to guess
  which one they mean from free text.

### Search, filter, and deletion (added Session 19)

- The admin ticket list (`AdminTicketsPanel`) can be filtered by opener
  (customer/promoter), category, and status, plus a free-text search over
  subject and opener name. Filtering is entirely client-side (the ticket
  list for one organization is small enough that this is simpler than
  adding query params to `GET /support/tickets`) -- if the dataset grows
  large enough to matter, move this filtering server-side rather than
  fetching the whole list.
- A ticket can be **permanently deleted only once its status is
  `RESOLVED`** (not `CLOSED` -- deliberately narrower, matching exactly
  what was asked for; revisit if `CLOSED` should also be eligible). The
  delete control (in both the ticket list row and the ticket detail view)
  is disabled for any other status, so there is no way to trigger the
  attempt from the UI on a non-resolved ticket. The backend enforces the
  same rule independently (`support/service.py::delete_ticket`, raising
  `TicketDeletionError` -> `400`) -- the frontend disabled-state is a UX
  courtesy, not the actual guard.
- Deletion always shows a confirmation dialog naming the ticket subject
  before calling `DELETE /support/tickets/{id}`; there is no direct delete
  with no confirmation step anywhere in the UI.
- Gated by a new `tickets.delete` permission, deliberately narrower than
  `tickets.respond` (granted to `SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN`
  only, not `BACK_OFFICE_OPERATOR`) -- same "narrower than the capability
  that looks like it should cover it" pattern as `network.approve` (see
  `security-model.md`), since permanently destroying a ticket is more
  consequential than replying to one.
- Deleting a ticket also deletes its `TicketMessage` rows in the same
  transaction (no FK `ondelete` cascade exists at the DB level) and
  records an audit entry (`action="ticket.deleted"`, with the subject/
  category/status snapshotted into `previous_value`) before the rows are
  removed -- the audit trail survives even though the ticket itself no
  longer does.

## Notifications (added Session 17)

See `database-model.md §7` for the table shape. Behavior:

- **Who gets what**: `CONTRACT_CREATED`/`TICKET_CREATED`/
  `PROMOTER_APPROVAL_REQUESTED` fan out to every user holding a role in a
  fixed set (`notifications/service.py::STAFF_NOTIFY_ROLES` for the first
  two, the narrower `APPROVAL_NOTIFY_ROLES` for the third -- only
  `network.approve` holders can act on an approval request, so only they
  are told about one). `COMMISSION_EARNED`/`PROMOTER_APPROVED`/
  `PROMOTER_REJECTED` go to exactly one specific user -- the beneficiary
  agent's own `user_id`, when they have a login at all (an agent with no
  `user_id` -- a collaborator who predates having their own account --
  simply generates no notification for that event, not an error).
- **The actor never notifies themselves**: whoever triggered the event
  (created the contract, opened the ticket) is excluded from that event's
  own fan-out (`notify_roles(..., exclude_user_id=actor_user_id)`) -- an
  admin creating a contract doesn't need to be told they just did that.
- **Read state is per person**: marking a notification read only affects
  the row for that recipient; a fanned-out event that reached five admins
  produces five independent rows, so one admin dismissing it doesn't
  silently clear it for the other four.
- **No push, no email** -- notifications are in-app only, polled every 25s
  by the frontend. Real-time delivery (WebSockets/SSE) and email digests are
  future work, not built here.

## Promoter reassignment

- An admin can move a customer's attribution from one promoter to another
  (`POST /customers/{id}/reassign-promoter`) -- but a customer can never end up
  with NO promoter ("nessuno può stare senza promoter che lo invita" is a closed
  circuit both at registration and afterward): reassignment is rejected if the
  customer has no existing `customer_attributions` row to correct in the first
  place (e.g. a customer created directly by admin, never through a referral
  link, has none).
- Reassigning to the SAME promoter the customer is already attributed to is
  rejected as a no-op, not silently accepted -- it would create a meaningless
  `attribution_corrections` audit row.
- Every reassignment writes an `attribution_corrections` row (previous promoter,
  new promoter, who requested it, why) -- this table existed since the first
  session's schema but had no code path writing to it until this feature.
- Reassignment only changes future commission attribution going forward; it never
  retroactively touches `network_snapshots` or past `commission_movements` for
  contracts already activated under the previous promoter (same "frozen at
  activation" rule as everywhere else commission chains are involved).

## Photo uploads

- Customer, promoter, and product photos are stored in a bucket
  (`lial-media`/`S3_BUCKET_MEDIA`) that is deliberately SEPARATE from and less
  restrictive than the documents bucket (`lial-documents`): public-read, no
  signed URLs, because these are ordinary profile/product photos, not sensitive
  documents. Never put anything sensitive in this bucket -- see
  `security-model.md §Documents`.
- Uploads are validated server-side regardless of what the browser claims:
  content-type must be one of `image/jpeg|png|webp|gif`, max 5 MB
  (`core/storage.py::upload_media()`). A new upload never overwrites the
  previous photo's object in place -- it gets a fresh random key and the
  `photo_url` column is repointed; the old object is simply orphaned (not worth
  a cleanup job for a handful of KB-sized images).
- If no photo has been uploaded, `photo_url` is `NULL` and every list/detail view
  shows a generic person icon -- never a broken `<img>` tag.

## Contract documents (added Session 14)

- Every contract requires `IDENTITY`, `FISCAL_CODE`, and `UTILITY_BILL`
  (`documents/service.py::BASE_REQUIRED_DOCUMENT_TYPES`); a customer of kind
  `COMPANY` or `CONDOMINIUM` additionally requires `CHAMBER_OF_COMMERCE`
  (`COMPANY_LIKE_KINDS`). This is a hardcoded, honest default in the service
  layer, not read from the pre-existing `product_versions.required_documents`
  jsonb column -- that column has never actually been populated or wired to
  any behavior, so treating it as configurable today would be pretending.
- `GET /contracts/{id}/documents` always returns one row per *required* type
  for that customer's kind, with `document: null` when nothing has been
  uploaded yet -- "missing" is a first-class, visible state, not silence.
- Either the customer (their own contract only) or staff can upload a
  document; only staff can review (approve/reject with a note). This covers
  both the normal flow (customer uploads, admin reviews) and the exception
  the user specifically asked for: a customer sends a document some other
  way (email, in person) and an admin uploads it into the system on their
  behalf.
- Uploading a document does not, by itself, change contract status --
  reviewing/transitioning is a separate, explicit action. The state machine's
  `SUBMITTED`/`UNDER_REVIEW` → `DOCUMENTS_PENDING` transition is how staff
  flags "this contract can't proceed until the customer completes their
  paperwork"; the transition's `notes` field is where staff records *which*
  document is missing, surfaced back to the promoter's own network view
  (`get_branch_contracts()`'s `admin_note` field) so they know what to chase.
- See `security-model.md §Documents` for how these files are stored --
  private bucket, presigned-URL-only access, never a public or guessable
  link.

## Password reset

- `POST /auth/forgot-password` always returns success regardless of whether the
  email exists for that organization -- the same enumeration-safety principle as
  login. If the account is real, a `password_reset_tokens` row is created: an
  opaque random token (only its sha256 hash persisted), expiring in 60 minutes,
  single-use (`used_at`).
- Email delivery is real SMTP when `SMTP_HOST` is configured (`core/email.py`); if
  not, the reset link is written to the API process log only
  (`docker compose logs api`) -- **never** to `audit_log` or any other place a
  web-UI role could read it, since that would let staff take over any account by
  reading its reset link. This is a genuine, working fallback, not a stub: the
  link is real and valid the moment it's generated, only its delivery channel
  differs.
- `POST /auth/reset-password` (token + new password) revokes every active session
  for that user on success -- a password reset is exactly the moment to assume the
  old password may have leaked, so anyone still logged in with it is logged out.
- Both endpoints are rate-limited per client IP (`core/rate_limit.py`, Redis
  fixed-window counter) -- 5 requests/5min for `forgot-password`, 10/5min for
  `reset-password` -- independent of the per-account lockout in `authenticate()`.

## Internal wallet (added Session 21)

Every user (customer or promoter, whether or not they also hold the other
role) has an internal EUR wallet, styled after a cryptocurrency wallet: an
address (`0x` + 40 hex chars, cosmetic only -- no real blockchain), an
integer-cents balance, and a global append-only transaction ledger
(`wallets`/`wallet_transactions`, see `database-model.md §9`). This is a
purely internal, virtual balance -- there is no connection to real banking
rails, no payment provider integration, and no withdrawal path to real
money, by design.

- **Cashback / top-up**: after a customer buys a product, an admin can
  credit ("bonifica") an arbitrary amount to that customer's wallet,
  optionally linked to the contract that earned it (`reference_contract_id`)
  -- or as a plain, purchase-unrelated recharge. Gated by `wallet.manage`
  (`SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN` only, deliberately not
  `BACK_OFFICE_OPERATOR` -- same sensitivity tier as
  `commissions.evaluate_ranks`). The wallet is created lazily on first
  credit if the recipient never had one.
- **Peer-to-peer transfer**: any wallet holder can send money to any other
  wallet in the same organization by address, no relationship required
  (like a real crypto wallet) -- self-transfer and cross-organization
  transfers are both rejected. Self-service, gated only by authentication
  (the caller's own wallet is always the source, resolved from their own
  login, never from the request body) plus a per-IP rate limit (20
  requests/60s on `POST /wallets/transfer`) against scripted abuse.
- **Balance integrity**: a debit can never take a wallet below zero --
  enforced both by an atomic compare-and-swap `UPDATE` at write time and by
  a DB `CHECK (balance_cents >= 0)` constraint as defense in depth. Every
  credit/transfer/reversal request carries a client-generated
  `idempotency_key`; a retried request with the same key returns the
  original result instead of double-applying.
- **Reversal**: an admin can correct a mistaken `ADMIN_CREDIT` or `TRANSFER`
  (`wallet.manage`-gated `POST /wallets/admin/transactions/{id}/reverse`).
  This inserts a new, linked `REVERSAL` row -- the original is never
  mutated, same append-only discipline as `commission_reversals`. Reversing
  a `TRANSFER` re-debits the original recipient, which can itself fail with
  "saldo insufficiente" if they've since spent the funds; this is an
  accepted, documented outcome, not a bug. A `REVERSAL` row can never itself
  be reversed.
- **Notifications**: the recipient of a credit or transfer gets an in-app
  notification (`CASHBACK_RECEIVED` / `WALLET_TRANSFER_RECEIVED`).
- **Admin visibility**: `GET /wallets/admin` lists every wallet's balance
  org-wide; `GET /wallets/admin/{user_id}` and
  `GET /wallets/admin/{user_id}/transactions` show one user's wallet and
  history (does **not** lazily create a wallet just by viewing -- an admin
  looking at a user who never transacted sees "no wallet yet");
  `GET /wallets/admin/transactions` is the global ledger, filterable by
  type/user, with CSV export in the dashboard.
- **Peer-to-peer transfer is denied by default** (`Wallet.can_transfer`,
  added Session 23) for every wallet, customer or promoter -- an admin must
  enable it individually per promoter (`PATCH
  /wallets/admin/{user_id}/transfer-permission`, `wallet.manage`-gated).
  Deliberately per-wallet, not a role grant: opening it for "all promoters"
  would be wrong the first time only some of them should have it, which is
  exactly today's situation.

## Partner-invoice cashback (added Session 23)

A second, entirely separate way wallet credit enters the system, alongside
the plain admin `ADMIN_CREDIT` top-up above -- see
`docs/cashback-partner-invoices-plan.md` for the full design rationale and
`database-model.md` for the schema. Summary:

- **What it is**: Lial Energy brokers for external energy suppliers
  (`partners`, e.g. Eviso). A customer or promoter who already pays one of
  these directly can redeem part of that spend as internal wallet credit,
  by uploading proof of payment (`invoice_redemptions`) and then paying Lial
  3% of the confirmed amount by bank transfer. Once that 3% is confirmed
  received, the wallet is credited 100% + a further 3% bonus.
- **Cardinal rule**: credit is minted **only** against a real, admin-confirmed
  external bank transfer (the 3%) -- never against spending existing credit.
  Paying a Lial product with wallet credit (once Phase 4/checkout exists)
  must never itself generate more credit, or the system would create value
  from nothing.
- **Lifecycle**: `SUBMITTED` (uploaded) → `PAYMENT_PENDING` (an admin
  confirmed the real amount and a payment reference code was generated) →
  `CREDITED` (an admin confirmed the 3% arrived; two `wallet_transactions`
  rows are written -- `INVOICE_REDEMPTION_BASE` and `INVOICE_REDEMPTION_BONUS`,
  never one combined row, both carrying `reference_invoice_redemption_id`).
  `REJECTED` is reachable from `SUBMITTED` or `PAYMENT_PENDING`.
- **No OCR today**: the customer types the amount they read; an admin always
  verifies against the uploaded document before anything is unlocked. This
  is a deliberate simplification, not a stub -- the flow is fully functional
  without automated reading, just slower per-request for the admin.
- **Where the document lives**: NOT the `documents` table (that one's
  `contract_id` is NOT NULL by design, for contract KYC documents) --
  `invoice_redemptions` carries its own `storage_key` in the same private
  bucket via `core/storage.py`.
- **Spending side (Phase 4, added Session 24; self-checkout + card payments
  added Session 26)**: `Product.category` (`INTERNAL`/`DROPSHIPPING`/
  `PARTNER`) and `ProductVersion.credit_discount_percentage` (0-100,
  enforced to 0 for `INTERNAL`) gate a new `orders` domain -- deliberately
  NOT `Contract` (`Contract.supply_point_id` is NOT NULL by design, every
  contract is an energy supply; an order for e.g. a partner t-shirt has no
  equivalent). Either an admin or the customer themselves (self-checkout)
  picks a DROPSHIPPING/PARTNER product version and how much wallet credit
  to apply (capped by both the product's percentage and the customer's
  balance, previewed via `GET /orders/quote` or `/orders/quote/mine` first);
  that amount is debited immediately via a `PURCHASE_DEBIT` wallet-transaction
  type (the mirror of `ADMIN_CREDIT`: `to_wallet_id` NULL instead of
  `from_wallet_id` NULL). The residual is paid one of two ways: **bank
  transfer**, confirmed by an admin exactly like a contract's `PAID`
  transition, or **card via Stripe** (`app/domains/payments/`), confirmed
  automatically by a webhook once `checkout.session.completed` fires -- the
  only case in this domain where `PAID` is reached with no human actor. If
  credit alone covers 100%, the order skips straight to `PAID` regardless of
  payment method. Cancelling an `AWAITING_PAYMENT` order reverses the exact
  `PURCHASE_DEBIT` row via `reverse_transaction()` (extended to handle a
  debit with no recipient wallet), refunding the customer precisely.
- **Payment method availability is gated, not just visually disabled**:
  bank transfer requires an IBAN set in `Organization.settings`
  (`bank_iban`, admin-editable, `organization.manage` permission); card
  requires BOTH a Stripe secret key and publishable key set (a separate,
  stricter `organization.manage_payments` permission -- **SUPER_ADMIN
  only**, deliberately narrower than the bank IBAN's permission tier). A
  frontend must never render a payment-method button for an unconfigured
  method; `create_order()` independently rejects the request server-side
  regardless (`PaymentMethodNotAvailableError`), so this is enforced even if
  the frontend were bypassed. Stripe secret/webhook keys are never returned
  in full by any endpoint, only "configured yes/no" plus the secret key's
  last 4 characters -- same principle as a password never round-tripped in
  plaintext.
- **Stripe webhook is per-organization and unauthenticated by design**:
  `POST /payments/stripe/webhook/{organization_id}` takes no auth
  dependency -- the Stripe signature, verified against THAT organization's
  own webhook secret, is the authentication. The organization id in the URL
  is what a SUPER_ADMIN pastes into their own Stripe Dashboard's webhook
  config, and is what keeps one endpoint correct for every tenant in
  principle, even though this deployment currently has one organization.

## Account gates (Session 27)

Three independent, self-service gates block dashboard use until satisfied,
each with its own acceptance state persisted on `users`/`agent_profiles` and
visible to admins (Anagrafiche Clienti/Promoter, small badges next to each
account). None of these are enforced client-side only -- every corresponding
backend action independently requires the same state.

- **Privacy consent**: `users.privacy_accepted_at`, set once at
  self-registration (`RegisterRequest.accept_privacy`, a required checkbox --
  the request is rejected server-side if unticked). NULL for every account
  that predates this field (admin-created accounts, or self-registered
  before Session 27) -- there is no retroactive consent to backfill, so it
  simply stays NULL for those.
- **Email verification** (new registrations only): `users.email_verified_at`
  (a column that already existed, previously unused). Registration sends a
  branded confirmation email (`core/email_templates.py`) with a link to
  `/verify-email?token=...`, backed by `email_verification_tokens` (opaque
  token, hashed at rest, 24h expiry, single-use -- same pattern as
  password-reset tokens). **Explicit product decision**: every account that
  existed before this feature shipped is grandfathered as already-verified
  (the 0026 migration backfills `email_verified_at = COALESCE(email_verified_at,
  created_at)` for every NULL row) -- nobody who was already using the
  product gets a surprise "confirm your email" wall. The rule applies only
  going forward, to accounts created after Session 27.
- **Profile completion** (fiscal code + residence address): `users.fiscal_code`
  + `residence_street/city/province/postal_code/country`. Unlike email
  verification, this one is deliberately retroactive -- **every** account,
  existing or new, sees the blocking popup at next login until filled in
  (`PATCH /auth/me/profile`, `users/service.py::is_profile_complete`).
  Demo/seed accounts are pre-filled so they're never blocked.
- **Promoter collaboration agreement + OTP** ("lavora con noi"):
  `agent_profiles.collaboration_accepted_at` /
  `collaboration_contract_version` / `collaboration_otp_verified_at`.
  Becoming a promoter now requires ticking a collaboration-agreement
  checkbox (`accept_contract`) AND typing back a 6-digit code emailed via
  `POST /network/agents/apply/request-otp` (`otp_codes` table, purpose
  `PROMOTER_APPLICATION_OTP_PURPOSE`, 10-minute expiry, single-use, verified
  server-side in `apply_as_promoter()` before any of the existing
  auto-activation/reapplication branching runs) -- proof the account holder,
  not just whoever is logged in, actually agreed.
- All four gates apply only to CUSTOMER/PROMOTER accounts, not admin-tier
  roles (`account-gate.tsx` checks live roles from `GET /auth/me` before
  rendering the blocking modal) -- there is no scenario where blocking a
  SUPER_ADMIN's own dashboard behind a fiscal-code popup makes sense.

**Notification emails** (also Session 27, same branded-HTML-shell mechanism):
cashback credited (`invoice_redemptions/service.py::confirm_payment`, fires
after the wallet credit) and a new support ticket opened
(`support/service.py::create_ticket`, sent to
`Organization.settings.admin_notification_email`, defaulting to
`info@lialenergy.it` -- `organizations/service.py::DEFAULT_ADMIN_NOTIFICATION_EMAIL`,
admin-editable via the existing company-settings PATCH). All best-effort:
an SMTP hiccup is logged, never blocks the underlying action (ticket
creation, cashback crediting, registration all already committed by the
time the email send is attempted).

## Store orders vs. Lial Energy contracts -- and the Session 28 e-commerce pass

Two structurally different things both live under "products", and this
distinction is load-bearing, not cosmetic:

- **Lial Energy (`category=INTERNAL`) products** are the matrix a real
  energy-supply **Contract** is created from (`POST /contracts`) -- these
  are what a promoter earns commissions on, and what shows up in the
  network/commission engine. They never go through the `orders` domain at
  all (`orders/service.py::_get_sellable_product_version` explicitly
  rejects INTERNAL products with a "si acquistano come contratto" error).
- **DROPSHIPPING/PARTNER products** are a separate, purely additional perk:
  a customer's cashback wallet balance can be spent on them via the `orders`
  domain (self-checkout, `POST /orders/mine`) -- no commission, no network
  effect, just an e-commerce-style purchase paid partly in wallet credit and
  partly by bank transfer or card.

**Session 28** brought the store/order side of this up to a real e-commerce
standard, per explicit request ("rendilo un ecommerce professionale"):

- **Product photo everywhere a product/order shows one**: `ProductVersion.
  image_url` (already existed, admin-uploadable since an earlier session)
  now also flows through to `OrderRead.product_image_url`
  (`orders/service.py::to_read_dict` joins it in) -- the same photo appears
  as a thumbnail on every order row, admin or customer side, not just the
  shop grid. A shared `product-thumbnail.tsx` component renders it (or a
  neutral package-icon placeholder when there is none) everywhere, so the
  "no photo yet" look is consistent instead of each screen inventing its
  own fallback.
- **Product detail page before checkout**: clicking a purchasable
  (DROPSHIPPING/PARTNER) product card opens `product-detail-modal.tsx`
  first -- full description, price breakdown, photo -- rather than jumping
  straight from the grid card into the checkout flow, matching how a real
  storefront works. INTERNAL (Lial Energy) products never get this
  treatment; those stay contract-only.
- **"I miei Ordini"** (`customer-orders-panel.tsx`, new customer-dashboard
  tab): every order the customer has placed, with its status (in attesa di
  pagamento / pagato / annullato) and a "Paga ora" action on an unpaid one
  -- exactly the "reservation list" the request asked for, so a customer
  never has to remember what they bought or track down how to finish
  paying for it. The existing `admin-orders-panel.tsx` (already a full
  gestionale -- create, confirm bank transfer, cancel, filter by status)
  gained the same photo thumbnails for consistency.
- **Order-confirmation email** (`orders/service.py::_send_order_confirmation_email`,
  fires at the end of `create_order()`, after the order is already
  committed): summarizes what was bought and explains exactly how to pay --
  the IBAN + causale for a bank-transfer residual, or a real, freshly-minted
  Stripe payment link for a card residual, or a simple "no payment needed"
  confirmation when credit covered everything. Best-effort like every other
  email in this project: both `EmailNotConfiguredError` (SMTP off) and any
  `stripe.error.StripeError` (bad/revoked key, Stripe outage) are caught so
  a payment-provider hiccup can never take an already-created order down
  with it -- the customer can still get a fresh Stripe link later from "I
  miei Ordini".
- **Stripe checkout opens in a new tab, never a full-page redirect**
  (`window.open(checkout_url, "_blank", "noopener,noreferrer")` in both
  `product-checkout-modal.tsx` and `customer-orders-panel.tsx`) -- per
  explicit request: if Stripe fails or the customer changes their mind
  mid-payment, the dashboard tab they were already on is never lost.
- **Dashboard header images**: the Wikimedia-hotlinked `SectionBanner`
  images (dim/dark, and "commissions"/"wallets" sharing one photo) were
  replaced with brighter, distinct, locally-bundled photos per section
  (`apps/dashboard/public/images/header-*.jpg`) -- same "bundle it locally,
  don't hotlink" convention `documentation-header.jpg` already established.

### Session 29 follow-up: verified, then polished further

The user asked to re-verify two things before continuing -- both checked
against the live database, not just the code:

- **Per-product credit-discount percentage**: confirmed correct end-to-end,
  no bug found. `ProductVersion.credit_discount_percentage` is clamped to 0
  for `INTERNAL` products and 0-100 for DROPSHIPPING/PARTNER
  (`catalog/service.py::_clamp_credit_discount`); `orders/service.py::
  get_quote()`/`max_creditable_cents()` read that product's own value, never
  a global constant. Live-verified: a 69,00€ PARTNER product with a
  30%-in-credits version correctly quoted `max_creditable_cents: 2070`
  (exactly 30% of 6900) via `GET /orders/quote/mine`.
- **Contract flow authority**: see "Who can move a contract through this
  pipeline" above -- confirmed staff-only, not a customer self-service
  flow; documented since the user asked to double check their own mental
  model of it.

Then, cosmetic/UX polish on top of the already-correct backend:

- **Product showcase redesign** (`customer-products-panel.tsx`): bigger,
  bolder price and "crediti usabili" (computed from that product's own
  price × discount %, shown in euro, not just a percentage badge) side by
  side at the bottom of each card; a discount ribbon and category chip
  overlaid on the photo; hover zoom on the image, card lift + glow, and a
  staggered fade-in on the grid; the whole photo stays clickable through to
  `product-detail-modal.tsx`, which got the same bigger price/credits
  treatment plus a full-width gradient "Acquista ora" button.
- **Energy header photo swapped again**: from a ground-level solar-panel
  row to a bright aerial shot of a full solar farm (blue sky, vivid green)
  -- more strikingly "energia" and more luminous than the previous pick,
  per explicit feedback that the header art should lean into energy/light
  themes and brightness specifically.
- **Cashback-redemption camera capture upgraded to a real live viewfinder**
  (`camera-capture-modal.tsx`, `getUserMedia` + a `<video>` preview +
  canvas-frame capture) -- the previous "Scatta foto" button (Session 27)
  used a plain `<input capture="environment">`, which only opens a camera
  on some mobile browsers and does nothing at all on desktop (no webcam
  access). The new modal opens an actual live camera preview everywhere a
  camera exists, with a clear error+fallback state (close and use "Carica
  file") when it can't get camera access at all.
- **Desktop top nav bar added** alongside the existing sidebar
  (`app-shell.tsx`) -- big pill buttons for every nav item, pinned under
  the header on every page, mirroring the mobile bottom bar's "always one
  tap away" idea; the mobile bottom bar's own touch targets were also
  enlarged. This closes the gap left after Session 27 only shipped the
  mobile half of "primary tools as big buttons, bottom on mobile / top on
  desktop."

## Account freeze (Session 28)

`PATCH /users/{id}/freeze` / `/unfreeze`, gated by a new, deliberately
narrow `users.manage_lifecycle` permission (**SUPER_ADMIN only** -- the
user's own explicit request, since this is more sensitive than the
ADMIN/ORGANIZATION_ADMIN tier that already manages day-to-day
customer/promoter records). Freezing sets `users.status = "FROZEN"`,
which `auth/service.py::authenticate()` now checks before even looking at
the password (reuses `AccountLockedError`/423, same as the existing
too-many-failed-attempts lock, just with a different message) -- AND
revokes every one of that user's existing sessions immediately
(`revoke_all_sessions`), so an already-logged-in frozen account is kicked
out right away, not just blocked on its next fresh login. Deliberately
does **not** touch any other data -- contracts, orders, wallet history,
network position all stay exactly as they were; unfreezing is a full,
lossless undo. An admin cannot freeze their own account.

**"Elimina utente" (hard delete/anonymize) was explicitly deferred by the
user** after being shown the tradeoff: a true cascading delete of
contracts/orders/wallet transactions risks breaking other promoters'
commission history (their network position and commission chain reference
this user) and conflicts with Italian fiscal record-retention requirements
for contracts/invoices. Freeze-only ships for now; a real delete/anonymize
flow is future work, to be designed once the user decides how to reconcile
those two constraints (most likely: anonymize personal data while
preserving the underlying ledger rows, not a literal `DELETE`).

## GDPR notes

Consent versions, retention periods, and the legal basis for each processing purpose
are **not** implemented as final policy in this phase — schema hooks exist
(`documents.expires_at`, audit of all document access) but retention windows and the
lawful basis registry require legal sign-off before being treated as authoritative.
See `open-questions.md #5`.
