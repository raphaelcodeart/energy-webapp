"""Pure unit tests for the core commission calculator -- no DB, no I/O. Matches the
test matrix in docs/commission-engine-specification.md."""

from app.domains.commissions.calculators.entrepreneurial_difference import (
    ChainMember,
    calculate_chain,
)


def member(agent_id: str, rank_code: str, token_cents: int, depth: int) -> ChainMember:
    return ChainMember(agent_id=agent_id, rank_code=rank_code, personal_token_cents=token_cents, depth=depth)


def test_producer_only_no_ascendants():
    chain = [member("producer", "S1", 4000, 0)]
    steps = calculate_chain(chain)
    assert len(steps) == 1
    assert steps[0].movement_type == "PERSONAL_TOKEN"
    assert steps[0].gross_amount_cents == 4000


def test_single_ascendant_higher_rank_gets_correct_difference():
    chain = [member("producer", "S1", 4000, 0), member("sponsor", "S2", 4500, 1)]
    steps = calculate_chain(chain)
    assert steps[0].gross_amount_cents == 4000
    assert steps[1].movement_type == "ENTREPRENEURIAL_DIFFERENCE"
    assert steps[1].entrepreneurial_difference_cents == 500
    assert steps[1].gross_amount_cents == 500


def test_ascendant_equal_or_lower_rank_gets_zero():
    chain = [member("producer", "S2", 4500, 0), member("sponsor", "S1", 4000, 1)]
    steps = calculate_chain(chain)
    assert steps[1].gross_amount_cents == 0
    assert "gia'" in steps[1].explanation.lower() or "coperto" in steps[1].explanation.lower()


def test_full_chain_s_to_md_no_duplicate_differential():
    chain = [
        member("s1", "S1", 4000, 0),
        member("s2", "S2", 4500, 1),
        member("s3", "S3", 5000, 2),
        member("tl1", "TL1", 5500, 3),
        member("tl4", "TL4", 7000, 4),
        member("md5", "MD5", 9500, 5),
    ]
    steps = calculate_chain(chain)
    assert len(steps) == 6
    diffs = [s.gross_amount_cents for s in steps]
    assert diffs == [4000, 500, 500, 500, 1500, 2500]
    # Sum of all steps must equal the top rank's personal token -- no beneficiary is
    # ever paid the same marginal amount twice.
    assert sum(diffs) == 9500


def test_replaying_same_chain_is_deterministic_and_idempotent_at_the_pure_function_level():
    chain = [member("producer", "S1", 4000, 0), member("sponsor", "S3", 5000, 1)]
    first = calculate_chain(chain)
    second = calculate_chain(chain)
    assert [s.gross_amount_cents for s in first] == [s.gross_amount_cents for s in second]


def test_multiple_ascendants_each_gets_only_marginal_difference():
    chain = [
        member("producer", "S1", 4000, 0),
        member("a", "S2", 4500, 1),
        member("b", "S2", 4500, 2),  # same rank as 'a' -- must get zero, not another 500
        member("c", "S3", 5000, 3),
    ]
    steps = calculate_chain(chain)
    assert steps[1].gross_amount_cents == 500   # a: S2 over S1
    assert steps[2].gross_amount_cents == 0     # b: S2, already covered by a
    assert steps[3].gross_amount_cents == 500   # c: S3 over S2


def test_empty_chain_returns_no_steps():
    assert calculate_chain([]) == []
