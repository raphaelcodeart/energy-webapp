import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.commissions.calculators.entrepreneurial_difference import (
    CalculationStep,
    ChainMember,
    calculate_chain,
)
from app.domains.commissions.models import Rank
from app.domains.commissions.services.run_calculation import _build_chain
from app.domains.contracts.models import Contract


async def simulate_for_contract(
    db: AsyncSession,
    *,
    contract_id: uuid.UUID,
    rank_overrides: dict[str, str] | None = None,
) -> list[CalculationStep]:
    """Read-only preview: same algorithm as the live engine, but NEVER writes to
    commission_calculations/commission_movements. `rank_overrides` maps agent_id ->
    rank code, letting the admin dashboard preview 'what if this agent were promoted
    to X' without mutating agent_rank_history."""
    contract = await db.get(Contract, contract_id)
    if contract is None or contract.network_snapshot_id is None:
        raise ValueError("Contract has no network snapshot to simulate against")

    chain = await _build_chain(db, network_snapshot_id=contract.network_snapshot_id)

    if rank_overrides:
        organization_id = contract.organization_id
        override_codes = set(rank_overrides.values())
        ranks_stmt = select(Rank).where(
            Rank.organization_id == organization_id, Rank.code.in_(override_codes)
        )
        ranks_by_code = {r.code: r for r in (await db.execute(ranks_stmt)).scalars().all()}
        new_chain = []
        for member in chain:
            override_code = rank_overrides.get(member.agent_id)
            if override_code and override_code in ranks_by_code:
                rank = ranks_by_code[override_code]
                new_chain.append(
                    ChainMember(
                        agent_id=member.agent_id,
                        rank_code=rank.code,
                        personal_token_cents=rank.personal_token_cents,
                        depth=member.depth,
                    )
                )
            else:
                new_chain.append(member)
        chain = new_chain

    return calculate_chain(chain)
