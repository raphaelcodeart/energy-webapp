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

## Contract state machine

```
DRAFT → SUBMITTED → DOCUMENTS_PENDING → UNDER_REVIEW → APPROVED
      → PAYMENT_PENDING → PAID → ACTIVATION_PENDING → ACTIVE
ACTIVE → SUSPENDED → ACTIVE
ACTIVE → CANCELLED
ACTIVE → EXPIRED
ACTIVE → RENEWED
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

- A renewal is a new `contract_events` row of type `RENEWED` plus a new commission
  calculation; it does not mutate the original calculation or its movements.
- A reversal ("storno") never deletes or edits a prior `commission_movements` row. It
  creates a new movement with `movement_type = REVERSAL`, linked via
  `commission_reversals.original_movement_id`, carrying a negative amount, an
  explanation, and the recovered period. Formula for partial-period recovery
  (PLACEHOLDER — see open-questions.md #4):
  `refund_cents = original_amount_cents * remaining_months / total_contract_months`.

## GDPR notes

Consent versions, retention periods, and the legal basis for each processing purpose
are **not** implemented as final policy in this phase — schema hooks exist
(`documents.expires_at`, audit of all document access) but retention windows and the
lawful basis registry require legal sign-off before being treated as authoritative.
See `open-questions.md #5`.
