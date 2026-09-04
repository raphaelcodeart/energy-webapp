# Open Questions / Assumptions Requiring Confirmation

Source document `docs/Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf` was not
present in the repository. Everything below is a placeholder that makes the system
runnable and testable; none of it is confirmed Lial Energy policy. Each item names the
exact config location to update once real figures/rules are available — no formula is
silently invented into unlabelled code.

## 1. Rank table (career plan) figures

**Placeholder**: `S1..S3`, `TL1..TL4`, `MD1..MD5` with linearly increasing
`personal_token_cents` (4000 → 9500), see `business-rules.md §Ranks`.
**Update (Session 15)**: `personal_volume_threshold_cents` /
`group_volume_threshold_cents` are no longer 0 -- populated with placeholder
ascending figures (migration `0010`) at the user's explicit request ("go get
those criteria and set them yourself"), used by the new rank-promotion-progress
feature (`business-rules.md §Rank promotion progress`). Still not confirmed
Lial Energy policy. `evaluation_window_months` remains unused/unknown -- the
progress calculation is lifetime-cumulative, not evaluated over any window.
**Where to fix**: `apps/api/alembic/versions/0010_rank_promotion_thresholds.py`
and `apps/api/app/seed/ranks.py` (both need updating together to stay in
sync), or a new `commission_rule_versions` row once the real plan document is
available — no application code change needed, only data.
**Also (Session 20)**: `network/service.py::AUTO_ACTIVATION_RANK_CODE = "S1"`
hardcodes the floor rank self-service "lavora con noi" applicants start at,
instead of deriving the lowest-`level` rank from the org's ladder. If code
`S1` is ever renamed/removed, this silently resolves to no rank
(`_get_current_rank_id()` returns `None`, no error) rather than failing loud.
**Where to fix**: same file, alongside item #1's other placeholder figures.
**Update (Session 20)**: a second, independent axis now exists —
`commissions/services/rank_evaluation.py` actually **writes** the agent's
rank (promotes or demotes) once a month, using a fixed single-calendar-month
window, explicitly NOT `evaluation_window_months` (still unused by anything).
This was an explicit user decision, not a resolution of this open question —
see `business-rules.md §Automatic monthly rank evaluation`. If the real plan
document specifies a genuine rolling window, both this and item #6 below need
updating together, since they'd likely share the same window definition.

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
**Note (Session 20)**: the rank re-evaluation that now actually exists
(`rank_evaluation.py`, see item #1) does NOT use `evaluation_window_months`
either — it's a fixed single calendar month. This assumption's cross-reference
to "the same evaluation window" is therefore still unresolved/unverified, not
contradicted; revisit both together once the real window is known.

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
