"""Pure, deterministic calculator for the personal-token + entrepreneurial-difference
algorithm described in docs/commission-engine-specification.md. No I/O, no DB access
-- takes plain data in, returns plain data out, so it is trivially unit-testable and
usable from both the live engine and the read-only simulator."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChainMember:
    agent_id: str
    rank_code: str
    personal_token_cents: int
    depth: int  # 0 = producer, 1 = direct sponsor, ...


@dataclass(frozen=True)
class CalculationStep:
    beneficiary_agent_id: str
    rank_code: str
    base_amount_cents: int
    already_distributed_cents: int
    entrepreneurial_difference_cents: int
    gross_amount_cents: int
    movement_type: str
    explanation: str


def calculate_chain(chain: list[ChainMember]) -> list[CalculationStep]:
    """`chain` must be ordered by depth ascending, chain[0] is the producer.
    Returns one step per chain member (including zero-amount steps, which are kept
    for auditability/explainability -- they are simply not posted as ledger
    movements downstream)."""
    if not chain:
        return []

    steps: list[CalculationStep] = []

    producer = chain[0]
    already_distributed_cents = producer.personal_token_cents
    steps.append(
        CalculationStep(
            beneficiary_agent_id=producer.agent_id,
            rank_code=producer.rank_code,
            base_amount_cents=producer.personal_token_cents,
            already_distributed_cents=0,
            entrepreneurial_difference_cents=producer.personal_token_cents,
            gross_amount_cents=producer.personal_token_cents,
            movement_type="PERSONAL_TOKEN",
            explanation=(
                f"Gettone personale {producer.rank_code}: "
                f"{producer.personal_token_cents / 100:.2f} EUR"
            ),
        )
    )

    for member in chain[1:]:
        if member.personal_token_cents > already_distributed_cents:
            diff = member.personal_token_cents - already_distributed_cents
            steps.append(
                CalculationStep(
                    beneficiary_agent_id=member.agent_id,
                    rank_code=member.rank_code,
                    base_amount_cents=member.personal_token_cents,
                    already_distributed_cents=already_distributed_cents,
                    entrepreneurial_difference_cents=diff,
                    gross_amount_cents=diff,
                    movement_type="ENTREPRENEURIAL_DIFFERENCE",
                    explanation=(
                        f"Differenza tra gettone {member.rank_code} di "
                        f"{member.personal_token_cents / 100:.2f} EUR e quanto gia' "
                        f"riconosciuto ai livelli inferiori "
                        f"({already_distributed_cents / 100:.2f} EUR)"
                    ),
                )
            )
            already_distributed_cents = member.personal_token_cents
        else:
            steps.append(
                CalculationStep(
                    beneficiary_agent_id=member.agent_id,
                    rank_code=member.rank_code,
                    base_amount_cents=member.personal_token_cents,
                    already_distributed_cents=already_distributed_cents,
                    entrepreneurial_difference_cents=0,
                    gross_amount_cents=0,
                    movement_type="ENTREPRENEURIAL_DIFFERENCE",
                    explanation=(
                        f"Nessuna differenza: gettone {member.rank_code} "
                        f"({member.personal_token_cents / 100:.2f} EUR) gia' coperto "
                        f"dal livello inferiore ({already_distributed_cents / 100:.2f} EUR)"
                    ),
                )
            )

    return steps
