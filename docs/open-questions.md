# Open Questions / Assumptions Requiring Confirmation

Source document `docs/Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf` was not
present in the repository. Everything below is a placeholder that makes the system
runnable and testable; none of it is confirmed Lial Energy policy. Each item names the
exact config location to update once real figures/rules are available — no formula is
silently invented into unlabelled code.

## 1. Rank table (career plan) figures

**Placeholder**: `S1..S3`, `TL1..TL4`, `MD1..MD5` with linearly increasing
`personal_token_cents` (4000 → 9500), see `business-rules.md §Ranks`. Real thresholds
for `personal_volume_threshold_cents`, `group_volume_threshold_cents`, and
`evaluation_window_months` are unknown.
**Where to fix**: seed data in `apps/api/app/seed/ranks.py`, or a new
`commission_rule_versions` row once the plan document is available — no code change
needed, only data.

## 2. Network move approval

**Assumption**: a role with `network.manage` may self-approve a branch move
(`approved_by` optional in that case); all other moves require a second approver.
**Where to fix**: `apps/api/app/domains/network/service.py::move_agent()` — the
self-approval check is a single `if` guarded by this assumption; flip it once the real
approval policy is confirmed.

## 3. Energia Circolare bonus formula

**Assumption**: no distinct bonus formula exists yet; Energia Circolare contracts only
have the extension point (`product_versions` can point at a distinct
`commission_plan_version_id`), with a no-op hook in the calculator
(`commission-engine-specification.md §Algorithm` step 18).
**Where to fix**: implement the real formula in
`apps/api/app/domains/commissions/calculators/energia_circolare.py` (file reserved but
not yet created) once the rule is known.

## 4. Reversal ("storno") refund formula

**Assumption**: linear proration —
`refund_cents = original_amount_cents * remaining_months / total_contract_months`.
**Where to fix**: `apps/api/app/domains/commissions/calculators/reversal.py`.

## 5. GDPR retention & legal basis

**Assumption**: none finalized. Schema hooks exist (`documents.expires_at`, full audit
of document access/download) but retention windows per document category and the
lawful-basis registry require legal sign-off, not an engineering guess.
**Where to fix**: this requires a decision from Lial Energy's legal counsel, then a
`retention_policies` table (not yet created) keyed by document category.

## 6. 33% branch cap — exact denominator

**Assumption**: the cap applies to production aggregated at first-level-branch
granularity under the evaluated beneficiary, using the same evaluation window as the
beneficiary's rank re-evaluation (`ranks.evaluation_window_months`).
**Where to fix**: `apps/api/app/domains/commissions/policies/branch_cap.py` — the
aggregation query is isolated there specifically so the denominator can change without
touching the main calculator.

## 7. MFA and account lockout policy

**Assumption**: MFA schema is present (session/device tables support it) but not
enforced in v1; account lockout threshold is a placeholder (5 failed attempts / 15
minute window) pending a real security policy decision.
**Where to fix**: `apps/api/app/domains/auth/service.py` constants
`MAX_FAILED_ATTEMPTS`, `LOCKOUT_WINDOW_MINUTES`.

---

When `Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf` (or an equivalent
written policy) becomes available, re-open this file item by item, update the
corresponding code/data location, delete the resolved item, and record the change as a
new ADR if it affects architecture (e.g. a genuinely new bonus category that doesn't
fit the current calculator extension points).
