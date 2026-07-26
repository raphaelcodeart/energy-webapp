# Commission Engine Specification

Single authoritative implementation: `apps/api/app/domains/commissions/`. The Celery
worker calls this same code (imported, not reimplemented) to run batch/scheduled
calculations; it never re-derives the formulas.

```
commissions/
  models.py         # ORM: plans, rule versions, calculations, steps, movements
  schemas.py        # Pydantic I/O contracts
  repositories/      # persistence for plans, calculations, movements
  services/          # orchestration: run_calculation(), post_movements()
  calculators/       # pure functions: personal token, entrepreneurial difference
  policies/          # branch_cap (33% rule), eligibility
  evaluators/        # rank evaluation from production totals
  explainers/        # turn a calculation into a human-readable explanation string
  simulations/       # read-only simulate() entrypoint, never writes movements
  tasks/             # Celery task wrappers around services/
  tests/
```

## Trigger

A commission calculation is enqueued **only** on the `ContractActivated` domain event
(and on `ContractRenewed`), never on contract creation/submission. The event handler
lives in `contracts/service.py`'s `activate()` transaction — the event is only
dispatched after commit (outbox-style: see `adr/0005-outbox-for-domain-events.md`).

## Inputs

For a given `contract_id`:

1. `product_version` — pricing/eligibility snapshot pinned to the contract.
2. `commission_plan_version` — resolved from `product_version.commission_plan_version_id`.
3. `network_snapshot` — the frozen ancestor chain captured at activation
   (`network_snapshot_nodes` rows for this contract's `network_snapshot_id`).
4. `producer_agent_id` — from `contract_attributions`.
5. Each beneficiary's rank **as of the snapshot** (`rank_id_at_snapshot`), not their
   current live rank — this is what makes the calculation reproducible after later
   promotions/demotions.

## Algorithm

```
1.  load product_version, commission_plan_version, network_snapshot for contract
2.  producer = network_snapshot chain depth 0 (the contract's producer_agent_id)
3.  producer_rank = producer's rank_id_at_snapshot
4.  base_amount_cents = producer_rank.personal_token_cents
5.  already_distributed_cents = base_amount_cents
6.  emit step: producer receives base_amount_cents (movement_type = PERSONAL_TOKEN)
7.  for each ascendant in network_snapshot ordered by depth ascending (nearest first):
8.      ascendant_rank = ascendant's rank_id_at_snapshot
9.      eligible_amount = apply_branch_cap(ascendant, contract, policies.branch_cap)
10.     if ascendant_rank.personal_token_cents > already_distributed_cents:
11.         diff = ascendant_rank.personal_token_cents - already_distributed_cents
12.         diff = min(diff, eligible_amount)             # 33% rule may reduce it
13.         emit step: ascendant receives diff (movement_type = ENTREPRENEURIAL_DIFFERENCE)
14.         already_distributed_cents = ascendant_rank.personal_token_cents
15.     else:
16.         emit step: ascendant receives 0, explanation "already covered by lower rank"
17. apply any personal_bonus rules (product/plan-specific, additive, own movement_type = PERSONAL_BONUS)
18. apply Energia Circolare extension hook if product_version flags it (no-op today, see business-rules.md)
19. write commission_calculations (input_snapshot, output_snapshot, checksum = sha256 of both)
20. write commission_calculation_steps (one row per step above)
21. write commission_movements (one row per non-zero step), each with a unique
    idempotency_key = hash(contract_id, calculation trigger event id, beneficiary, movement_type)
22. commit transaction
23. after commit: emit CommissionCalculated event (for notifications) — never before commit
```

Steps 19–22 happen inside one DB transaction. If any step fails, nothing is persisted —
there is no partial ledger write. Re-running the same trigger event against the same
contract with the same idempotency key is a no-op (unique constraint on
`commission_movements.idempotency_key` + upsert-or-skip in the repository), which is
what makes step 21 safe to retry from Celery.

## Output shape

```json
{
  "contractId": "uuid",
  "producerAgentId": "uuid",
  "beneficiaryAgentId": "uuid",
  "networkSnapshotId": "uuid",
  "commissionPlanVersion": "2026.1",
  "rankAtCalculation": "S2",
  "producerRank": "S1",
  "baseAmountCents": 4500,
  "alreadyDistributedCents": 4000,
  "entrepreneurialDifferenceCents": 500,
  "personalBonusCents": 0,
  "grossAmountCents": 500,
  "currency": "EUR",
  "status": "ACCRUED",
  "explanation": "Differenza tra gettone S2 di 45,00 EUR e gettone S1 di 40,00 EUR"
}
```

## Simulator

`simulations/simulate()` accepts the same inputs plus optional overrides (alternate
plan version, alternate snapshot, alternate date) and returns the same output shape
without touching `commission_movements` or `commission_calculations`. Used by the admin
dashboard to preview a new plan version against historical contracts before publishing
it, and to diff two plan versions' outputs for the same contract.

## Ledger semantics

See `database-model.md §5` for `commission_movements` columns. Statuses:
`PENDING → ACCRUED → UNDER_REVIEW → PAYABLE → SCHEDULED → PAID`, with `REVERSED` /
`OFFSET` / `CANCELLED` as terminal alternates. Transitions between these statuses are
themselves new rows only when the amount changes (a reversal/offset); a pure status
change (e.g. `PAYABLE → SCHEDULED`) updates the same row's `status`/`scheduled_date` —
it is not a new economic fact, so it does not require append-only treatment. Only the
economic amount is immutable once `ACCRUED`.

## Test matrix (implemented subset in this phase; full matrix is the target)

Implemented now (`apps/api/app/domains/commissions/tests/`):
- producer-only contract (no ascendants) → single PERSONAL_TOKEN movement
- one ascendant with higher rank → correct ENTREPRENEURIAL_DIFFERENCE
- one ascendant with equal/lower rank → zero-amount step, explanation present
- chain of 3 ascendants, monotonically increasing rank → no duplicate differential
- same trigger event replayed twice → second run produces no new movements (idempotency)
- org isolation: calculation for org A never reads org B's ranks/snapshots

**Correction (`docs/paid-contract-commission-audit.md`, Problem #5):** the 33% branch
cap policy (`policies/branch_cap.py::apply_branch_cap`) is implemented and unit-tested
**in isolation** (`test_branch_cap.py`), but is **not** wired into `calculate_chain()` /
`run_calculation_for_contract()` — steps 9 and 12 of the algorithm above
(`eligible_amount = apply_branch_cap(...)`, `diff = min(diff, eligible_amount)`) do not
run in the live engine today. This line previously (incorrectly) claimed it was
"Implemented now" as part of the full engine; it is not. Wiring it in requires a
business decision on the "qualifying group production" denominator first (see
`docs/open-questions.md` #6) — implementing it on a guessed definition would just
replace an honest gap with a silently wrong one.

Deferred to Phase E hardening pass (tracked in `implementation-progress.md`):
33% branch cap integration (see correction above), Energia Circolare bonus formulas,
renewal/reversal calculators, Hypothesis
property-based invariants, multi-plan-version diffing in the simulator UI.
