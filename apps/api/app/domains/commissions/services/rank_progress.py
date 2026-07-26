"""How close an agent is to their NEXT rank's promotion thresholds.

Placeholder feature: the actual promotion criteria (personal/group volume
figures, evaluation window) were never provided by the business
(docs/open-questions.md #1) -- the numbers seeded in migration 0010 /
seed/ranks.py are a reasonable placeholder the user explicitly asked us to
pick, not confirmed Lial Energy policy. Both volumes computed here are
CUMULATIVE ("lifetime") totals of contract value (product base price) on
ACTIVE/RENEWED contracts -- ranks.evaluation_window_months is not applied,
deliberately: a rolling window is a separate, not-yet-built axis of this
same placeholder (see docs/business-rules.md#rank-promotion-progress-placeholder)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.catalog.models import ProductVersion
from app.domains.commissions.models import Rank
from app.domains.contracts.models import Contract, ContractAttribution
from app.domains.network import service as network_service
from app.domains.network.models import AgentProfile

VOLUME_STATUSES = ("ACTIVE", "RENEWED")


@dataclass
class RankProgress:
    current_rank_code: str | None
    current_rank_name: str | None
    next_rank_code: str | None
    next_rank_name: str | None
    is_max_rank: bool
    personal_volume_cents: int
    personal_volume_threshold_cents: int
    group_volume_cents: int
    group_volume_threshold_cents: int


async def _volume_for_agents(db: AsyncSession, *, agent_ids: list[uuid.UUID]) -> int:
    if not agent_ids:
        return 0
    stmt = (
        select(func.coalesce(func.sum(ProductVersion.base_price_cents), 0))
        .select_from(Contract)
        .join(ContractAttribution, ContractAttribution.id == Contract.contract_attribution_id)
        .join(ProductVersion, ProductVersion.id == Contract.product_version_id)
        .where(
            ContractAttribution.producer_agent_id.in_(agent_ids),
            Contract.status.in_(VOLUME_STATUSES),
        )
    )
    return int((await db.execute(stmt)).scalar_one())


async def get_rank_progress(db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID) -> RankProgress:
    agent = await db.get(AgentProfile, agent_id)
    current_rank = (
        await db.get(Rank, agent.current_rank_id) if agent is not None and agent.current_rank_id else None
    )

    next_rank = None
    if current_rank is not None:
        next_stmt = (
            select(Rank)
            .where(
                Rank.organization_id == organization_id,
                Rank.rule_version == current_rank.rule_version,
                Rank.level > current_rank.level,
            )
            .order_by(Rank.level.asc())
            .limit(1)
        )
        next_rank = (await db.execute(next_stmt)).scalar_one_or_none()

    personal_volume_cents = await _volume_for_agents(db, agent_ids=[agent_id])

    # Group volume = this agent's entire downline INCLUDING themselves --
    # get_branch() already returns the root at depth 0, same descendant
    # lookup get_branch_summary()/get_branch_contracts() use.
    branch = await network_service.get_branch(db, organization_id=organization_id, root_agent_id=agent_id)
    branch_agent_ids = [row["agent_id"] for row in branch] or [agent_id]
    group_volume_cents = await _volume_for_agents(db, agent_ids=branch_agent_ids)

    return RankProgress(
        current_rank_code=current_rank.code if current_rank else None,
        current_rank_name=current_rank.name if current_rank else None,
        next_rank_code=next_rank.code if next_rank else None,
        next_rank_name=next_rank.name if next_rank else None,
        is_max_rank=current_rank is not None and next_rank is None,
        personal_volume_cents=personal_volume_cents,
        personal_volume_threshold_cents=next_rank.personal_volume_threshold_cents if next_rank else 0,
        group_volume_cents=group_volume_cents,
        group_volume_threshold_cents=next_rank.group_volume_threshold_cents if next_rank else 0,
    )
