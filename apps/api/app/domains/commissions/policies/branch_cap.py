"""Regola del 33%: no single first-level branch under a beneficiary may contribute
more than `cap_percentage` of that beneficiary's qualifying group production. Excess
from one branch is EXCLUDED from the eligible total for that evaluation period (not
redistributed to other branches, not carried over). Pure function, no I/O -- see
docs/business-rules.md#regola-del-33 and docs/open-questions.md#6 for the
denominator assumption this encodes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BranchProduction:
    branch_root_agent_id: str
    production_cents: int


@dataclass(frozen=True)
class BranchCapResult:
    gross_production_cents: int
    eligible_production_cents: int
    excluded_production_cents: int
    per_branch_eligible_cents: dict[str, int]
    explanation: str


def apply_branch_cap(
    branches: list[BranchProduction], *, cap_percentage: float
) -> BranchCapResult:
    gross_total = sum(b.production_cents for b in branches)

    if gross_total == 0 or not branches:
        return BranchCapResult(
            gross_production_cents=0,
            eligible_production_cents=0,
            excluded_production_cents=0,
            per_branch_eligible_cents={},
            explanation="Nessuna produzione da valutare",
        )

    cap_amount_cents = int(gross_total * cap_percentage / 100)

    per_branch_eligible: dict[str, int] = {}
    excluded_total = 0
    for branch in branches:
        if branch.production_cents > cap_amount_cents:
            per_branch_eligible[branch.branch_root_agent_id] = cap_amount_cents
            excluded_total += branch.production_cents - cap_amount_cents
        else:
            per_branch_eligible[branch.branch_root_agent_id] = branch.production_cents

    eligible_total = sum(per_branch_eligible.values())

    capped_branches = [b.branch_root_agent_id for b in branches if b.production_cents > cap_amount_cents]
    if capped_branches:
        explanation = (
            f"Produzione lorda {gross_total / 100:.2f} EUR; rami {capped_branches} "
            f"limitati al {cap_percentage:.0f}% ({cap_amount_cents / 100:.2f} EUR ciascuno); "
            f"produzione ammessa {eligible_total / 100:.2f} EUR, esclusa "
            f"{excluded_total / 100:.2f} EUR"
        )
    else:
        explanation = (
            f"Produzione lorda {gross_total / 100:.2f} EUR, nessun ramo oltre il "
            f"{cap_percentage:.0f}%; produzione ammessa integralmente"
        )

    return BranchCapResult(
        gross_production_cents=gross_total,
        eligible_production_cents=eligible_total,
        excluded_production_cents=excluded_total,
        per_branch_eligible_cents=per_branch_eligible,
        explanation=explanation,
    )
