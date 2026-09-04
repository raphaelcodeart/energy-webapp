"""Automatic monthly rank evaluation: promotes OR demotes every ACTIVE agent to
match their production in a single calendar month. Run by Celery Beat at the
start of each month (see celery_app.py) or triggered on demand by an admin
(POST /commissions/rank-evaluation/run).

Deliberately not the same axis as rank_progress.py's cumulative "how close to
the next rank" display: that one is lifetime and promotion-only (informational),
this one is a strict single-month window and re-decides the rank in both
directions, per explicit user decision. ranks.evaluation_window_months stays
unused by both -- see docs/business-rules.md#rank-promotion-progress-placeholder."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.commissions.models import AgentRankHistory, Rank
from app.domains.commissions.services.rank_progress import volume_for_agents
from app.domains.network import service as network_service
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service

# Only a confirmed, currently-active promoter is re-evaluated -- PENDING_APPROVAL,
# SUSPENDED and TERMINATED agents are left untouched, same criterion already used
# by network/service.py::create_snapshot_for_contract for the commission chain.
EVALUATED_STATUSES = ("ACTIVE",)


@dataclass
class RankChange:
    agent_id: uuid.UUID
    display_name: str
    previous_rank_code: str | None
    new_rank_code: str
    direction: str  # "PROMOTED" | "DEMOTED"


def previous_calendar_month(reference: datetime) -> tuple[datetime, datetime]:
    """[start, end) of the calendar month before `reference`'s month, e.g.
    2026-08-25 -> (2026-07-01, 2026-08-01). Used as the automatic job's window
    (see celery_app.py, runs day 1 of each month) and as the manual trigger's
    default when no explicit ?month= is given."""
    first_of_this_month = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if first_of_this_month.month == 1:
        start = first_of_this_month.replace(year=first_of_this_month.year - 1, month=12)
    else:
        start = first_of_this_month.replace(month=first_of_this_month.month - 1)
    return start, first_of_this_month


async def _rank_ladder(db: AsyncSession, *, organization_id: uuid.UUID) -> list[Rank]:
    """The currently-in-force rank plan for this org -- 'open' rows (valid_to IS
    NULL), same convention as an open closure-table/effective_to row elsewhere
    in this codebase, rather than matching on rule_version (which would require
    the agent to already have a rank)."""
    stmt = (
        select(Rank)
        .where(Rank.organization_id == organization_id, Rank.valid_to.is_(None))
        .order_by(Rank.level.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


def _target_rank(ladder: list[Rank], *, personal_volume_cents: int, group_volume_cents: int) -> Rank:
    """Highest-level rank in the ladder whose personal AND group thresholds are
    both met this month. Ladder is ascending by level and thresholds are
    monotonically non-decreasing by design, so the last one that qualifies is
    the right one; ladder[0] (the floor rank, thresholds 0/0) always qualifies."""
    target = ladder[0]
    for rank in ladder:
        if (
            personal_volume_cents >= rank.personal_volume_threshold_cents
            and group_volume_cents >= rank.group_volume_threshold_cents
        ):
            target = rank
    return target


async def run_monthly_rank_evaluation(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
    actor_user_id: uuid.UUID | None = None,
    source: str = "AUTOMATIC",
) -> list[RankChange]:
    ladder = await _rank_ladder(db, organization_id=organization_id)
    if not ladder:
        return []
    rank_by_id = {rank.id: rank for rank in ladder}

    agents_stmt = select(AgentProfile).where(
        AgentProfile.organization_id == organization_id, AgentProfile.status.in_(EVALUATED_STATUSES)
    )
    agents = list((await db.execute(agents_stmt)).scalars().all())

    window_label = f"{window_start:%Y-%m}"
    changes: list[RankChange] = []
    for agent in agents:
        personal = await volume_for_agents(db, agent_ids=[agent.id], since=window_start, until=window_end)
        branch = await network_service.get_branch(db, organization_id=organization_id, root_agent_id=agent.id)
        branch_agent_ids = [row["agent_id"] for row in branch] or [agent.id]
        group = await volume_for_agents(db, agent_ids=branch_agent_ids, since=window_start, until=window_end)

        target = _target_rank(ladder, personal_volume_cents=personal, group_volume_cents=group)
        if target.id == agent.current_rank_id:
            continue

        previous_rank = rank_by_id.get(agent.current_rank_id) if agent.current_rank_id else None
        direction = "PROMOTED" if previous_rank is None or target.level > previous_rank.level else "DEMOTED"

        agent.current_rank_id = target.id
        db.add(
            AgentRankHistory(
                organization_id=organization_id,
                agent_id=agent.id,
                rank_id=target.id,
                effective_from=utcnow(),
                calculation_source=source,
                rule_version_id=f"{source.lower()}-{window_label}",
                approved_by=actor_user_id,
                reason=f"Valutazione {window_label}: personale {personal}c / gruppo {group}c",
            )
        )
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=actor_user_id,
            action="network.agent_rank_evaluated", entity_type="agent_profile", entity_id=str(agent.id),
            previous_value={
                "rank_id": str(previous_rank.id) if previous_rank else None,
                "rank_code": previous_rank.code if previous_rank else None,
            },
            new_value={"rank_id": str(target.id), "rank_code": target.code},
        )
        if agent.user_id is not None:
            if direction == "PROMOTED":
                title = f"Sei stato promosso a {target.name}"
            else:
                title = f"La tua qualifica è stata aggiornata a {target.name}"
            body = (
                f"In base al fatturato di {window_label}, la tua qualifica è passata da "
                f"{previous_rank.code if previous_rank else '-'} a {target.code}."
            )
            await notifications_service.notify_user(
                db, organization_id=organization_id, user_id=agent.user_id,
                type_="RANK_CHANGED", entity_type="agent_profile", entity_id=agent.id,
                title=title, body=body,
            )

        changes.append(
            RankChange(
                agent_id=agent.id,
                display_name=agent.display_name,
                previous_rank_code=previous_rank.code if previous_rank else None,
                new_rank_code=target.code,
                direction=direction,
            )
        )

    if changes:
        promoted = sum(1 for change in changes if change.direction == "PROMOTED")
        demoted = len(changes) - promoted
        await notifications_service.notify_roles(
            db, organization_id=organization_id, roles=notifications_service.APPROVAL_NOTIFY_ROLES,
            type_="RANK_EVALUATION_COMPLETED", entity_type="organization", entity_id=organization_id,
            title=f"Valutazione qualifiche {window_label} completata",
            body=f"{promoted} promozioni, {demoted} retrocessioni su {len(agents)} agenti valutati.",
        )

    await db.commit()
    return changes
