"""33% branch cap ('Regola del 33%') test matrix, per
docs/business-rules.md#regola-del-33-percento and
docs/commission-engine-specification.md's test matrix."""

from app.domains.commissions.policies.branch_cap import BranchProduction, apply_branch_cap


def test_single_branch_under_cap_fully_eligible():
    # Four equal branches (25% of gross each) -- all under the 33% cap.
    branches = [
        BranchProduction("branch-a", 20_000),
        BranchProduction("branch-b", 20_000),
        BranchProduction("branch-c", 20_000),
        BranchProduction("branch-d", 20_000),
    ]
    result = apply_branch_cap(branches, cap_percentage=33)
    assert result.per_branch_eligible_cents["branch-a"] == 20_000
    assert result.excluded_production_cents == 0


def test_single_branch_is_entire_production_so_it_hits_the_cap():
    # One branch = 100% of gross production; the cap cuts it down to 33%.
    branches = [BranchProduction("branch-a", 30_000)]
    result = apply_branch_cap(branches, cap_percentage=33)
    assert result.gross_production_cents == 30_000
    assert result.eligible_production_cents == 9_900  # 33% of 30_000
    assert result.excluded_production_cents == 20_100


def test_branch_exactly_at_cap_boundary_not_excluded():
    # Two equal branches: each is exactly 50%, cap is 33% -- both exceed and get capped.
    branches = [BranchProduction("a", 10_000), BranchProduction("b", 10_000)]
    result = apply_branch_cap(branches, cap_percentage=50)
    # cap_amount = 50% of 20_000 = 10_000 -- each branch is exactly at the cap, not over it.
    assert result.per_branch_eligible_cents["a"] == 10_000
    assert result.per_branch_eligible_cents["b"] == 10_000
    assert result.excluded_production_cents == 0


def test_one_branch_over_cap_excess_excluded_not_redistributed():
    branches = [BranchProduction("dominant", 27_000), BranchProduction("small", 3_000)]
    result = apply_branch_cap(branches, cap_percentage=33)
    gross = 30_000
    cap_amount = int(gross * 33 / 100)  # 9_900
    assert result.per_branch_eligible_cents["dominant"] == cap_amount
    assert result.per_branch_eligible_cents["small"] == 3_000
    assert result.excluded_production_cents == 27_000 - cap_amount
    # The excluded amount must not appear anywhere in the eligible total.
    assert result.eligible_production_cents == cap_amount + 3_000


def test_multiple_branches_none_over_cap():
    branches = [BranchProduction("a", 5_000), BranchProduction("b", 5_000), BranchProduction("c", 5_000)]
    result = apply_branch_cap(branches, cap_percentage=50)
    assert result.excluded_production_cents == 0
    assert result.eligible_production_cents == 15_000


def test_no_branches_returns_zero_eligible():
    result = apply_branch_cap([], cap_percentage=33)
    assert result.gross_production_cents == 0
    assert result.eligible_production_cents == 0
    assert result.excluded_production_cents == 0


def test_zero_total_production_returns_zero_eligible():
    branches = [BranchProduction("a", 0), BranchProduction("b", 0)]
    result = apply_branch_cap(branches, cap_percentage=33)
    assert result.eligible_production_cents == 0
