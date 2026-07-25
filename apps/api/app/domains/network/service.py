import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.network.models import (
    AgentProfile,
    NetworkAssignmentHistory,
    NetworkClosure,
    NetworkEdge,
    NetworkNode,
    NetworkSnapshot,
    NetworkSnapshotNode,
)


class NetworkError(Exception):
    pass


class CycleError(NetworkError):
    pass


async def _get_active_ancestors(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID
) -> list[tuple[uuid.UUID, int]]:
    """Ancestors of agent_id (including itself, depth 0), currently active."""
    stmt = select(NetworkClosure.ancestor_agent_id, NetworkClosure.depth).where(
        NetworkClosure.organization_id == organization_id,
        NetworkClosure.descendant_agent_id == agent_id,
        NetworkClosure.effective_to.is_(None),
    )
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def _get_active_descendants(
    db: AsyncSession, *, organization_id: uuid.UUID, agent_id: uuid.UUID
) -> list[tuple[uuid.UUID, int]]:
    """Descendants of agent_id (including itself, depth 0), currently active."""
    stmt = select(NetworkClosure.descendant_agent_id, NetworkClosure.depth).where(
        NetworkClosure.organization_id == organization_id,
        NetworkClosure.ancestor_agent_id == agent_id,
        NetworkClosure.effective_to.is_(None),
    )
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def create_agent(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    display_name: str,
    promoter_code: str,
    parent_agent_id: uuid.UUID | None,
    joined_at: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
    current_rank_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AgentProfile:
    """Register a brand-new agent (no pre-existing subtree) under an optional parent.
    Use move_agent() to relocate an agent that already has descendants."""
    joined_at = joined_at or utcnow()

    agent = AgentProfile(
        organization_id=organization_id,
        display_name=display_name,
        promoter_code=promoter_code,
        status="ACTIVE",
        joined_at=joined_at,
        current_rank_id=current_rank_id,
        user_id=user_id,
    )
    db.add(agent)
    await db.flush()

    if parent_agent_id is not None:
        parent_node = (
            await db.execute(
                select(NetworkNode).where(
                    NetworkNode.organization_id == organization_id,
                    NetworkNode.agent_id == parent_agent_id,
                    NetworkNode.effective_to.is_(None),
                )
            )
        ).scalar_one_or_none()
        if parent_node is None:
            raise NetworkError("Parent agent has no active network node")

    node = NetworkNode(
        organization_id=organization_id,
        agent_id=agent.id,
        direct_parent_agent_id=parent_agent_id,
        status="ACTIVE",
        effective_from=joined_at,
    )
    db.add(node)

    # Reflexive closure row: every agent is its own ancestor at depth 0.
    db.add(
        NetworkClosure(
            organization_id=organization_id,
            ancestor_agent_id=agent.id,
            descendant_agent_id=agent.id,
            depth=0,
            effective_from=joined_at,
        )
    )

    if parent_agent_id is not None:
        db.add(
            NetworkEdge(
                organization_id=organization_id,
                parent_agent_id=parent_agent_id,
                child_agent_id=agent.id,
                effective_from=joined_at,
            )
        )
        ancestors = await _get_active_ancestors(db, organization_id=organization_id, agent_id=parent_agent_id)
        for ancestor_id, depth in ancestors:
            db.add(
                NetworkClosure(
                    organization_id=organization_id,
                    ancestor_agent_id=ancestor_id,
                    descendant_agent_id=agent.id,
                    depth=depth + 1,
                    effective_from=joined_at,
                )
            )

    await audit_service.record(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="network.agent_created",
        entity_type="agent_profile",
        entity_id=str(agent.id),
        new_value={"parent_agent_id": str(parent_agent_id) if parent_agent_id else None},
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def move_agent(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    new_parent_agent_id: uuid.UUID | None,
    requested_by: uuid.UUID,
    approved_by: uuid.UUID | None,
    reason: str,
    effective_at: datetime | None = None,
) -> None:
    """Reparents agent_id (and its whole subtree) under new_parent_agent_id.

    Single transaction: closes the old node/edge/closure rows, opens new ones for
    the entire moving subtree, writes assignment history + audit. Never touches
    network_snapshots of already-activated contracts -- those keep pointing at the
    frozen chain that existed at activation time (see database-model.md).
    """
    effective_at = effective_at or utcnow()

    if new_parent_agent_id == agent_id:
        raise CycleError("An agent cannot be its own parent")

    node = (
        await db.execute(
            select(NetworkNode).where(
                NetworkNode.organization_id == organization_id,
                NetworkNode.agent_id == agent_id,
                NetworkNode.effective_to.is_(None),
            )
        )
    ).scalar_one_or_none()
    if node is None:
        raise NetworkError("Agent has no active network node")

    old_parent_agent_id = node.direct_parent_agent_id

    if new_parent_agent_id is not None:
        new_parent_ancestors = await _get_active_ancestors(
            db, organization_id=organization_id, agent_id=new_parent_agent_id
        )
        if any(ancestor_id == agent_id for ancestor_id, _ in new_parent_ancestors):
            raise CycleError("Move would create a cycle: new parent is a descendant of the agent")

    # The whole moving subtree (agent_id included, depth 0 = itself).
    subtree = await _get_active_descendants(db, organization_id=organization_id, agent_id=agent_id)
    subtree_ids = {a for a, _ in subtree}

    # Internal closure of the subtree (paths that stay valid regardless of the move).
    internal_rows = [
        row
        for row in (
            await db.execute(
                select(
                    NetworkClosure.ancestor_agent_id,
                    NetworkClosure.descendant_agent_id,
                    NetworkClosure.depth,
                ).where(
                    NetworkClosure.organization_id == organization_id,
                    NetworkClosure.ancestor_agent_id.in_(subtree_ids),
                    NetworkClosure.descendant_agent_id.in_(subtree_ids),
                    NetworkClosure.effective_to.is_(None),
                )
            )
        ).all()
    ]

    # Close every closure row that connects an old (non-subtree) ancestor to anything
    # inside the moving subtree.
    old_external_rows = (
        await db.execute(
            select(NetworkClosure).where(
                NetworkClosure.organization_id == organization_id,
                NetworkClosure.descendant_agent_id.in_(subtree_ids),
                NetworkClosure.ancestor_agent_id.not_in(subtree_ids),
                NetworkClosure.effective_to.is_(None),
            )
        )
    ).scalars().all()
    for row in old_external_rows:
        row.effective_to = effective_at

    # Close the old direct edge and node.
    if old_parent_agent_id is not None:
        old_edge = (
            await db.execute(
                select(NetworkEdge).where(
                    NetworkEdge.organization_id == organization_id,
                    NetworkEdge.parent_agent_id == old_parent_agent_id,
                    NetworkEdge.child_agent_id == agent_id,
                    NetworkEdge.effective_to.is_(None),
                )
            )
        ).scalar_one_or_none()
        if old_edge is not None:
            old_edge.effective_to = effective_at

    node.effective_to = effective_at
    new_node = NetworkNode(
        organization_id=organization_id,
        agent_id=agent_id,
        direct_parent_agent_id=new_parent_agent_id,
        status=node.status,
        effective_from=effective_at,
    )
    db.add(new_node)

    if new_parent_agent_id is not None:
        db.add(
            NetworkEdge(
                organization_id=organization_id,
                parent_agent_id=new_parent_agent_id,
                child_agent_id=agent_id,
                effective_from=effective_at,
            )
        )
        new_ancestors = await _get_active_ancestors(
            db, organization_id=organization_id, agent_id=new_parent_agent_id
        )
        # New paths: every (new ancestor) -> every (subtree member), depth composed.
        for ancestor_id, ancestor_depth in new_ancestors:
            for sub_ancestor, sub_descendant, sub_depth in internal_rows:
                if sub_ancestor != agent_id:
                    continue  # only need paths rooted at the moving agent itself
                db.add(
                    NetworkClosure(
                        organization_id=organization_id,
                        ancestor_agent_id=ancestor_id,
                        descendant_agent_id=sub_descendant,
                        depth=ancestor_depth + 1 + sub_depth,
                        effective_from=effective_at,
                    )
                )

    db.add(
        NetworkAssignmentHistory(
            organization_id=organization_id,
            agent_id=agent_id,
            old_parent_agent_id=old_parent_agent_id,
            new_parent_agent_id=new_parent_agent_id,
            requested_by=requested_by,
            approved_by=approved_by,
            reason=reason,
            effective_at=effective_at,
        )
    )

    await audit_service.record(
        db,
        organization_id=organization_id,
        actor_user_id=requested_by,
        action="network.agent_moved",
        entity_type="agent_profile",
        entity_id=str(agent_id),
        previous_value={"parent_agent_id": str(old_parent_agent_id) if old_parent_agent_id else None},
        new_value={"parent_agent_id": str(new_parent_agent_id) if new_parent_agent_id else None},
        reason=reason,
    )
    await db.commit()


async def is_ancestor(
    db: AsyncSession, *, organization_id: uuid.UUID, ancestor_agent_id: uuid.UUID, agent_id: uuid.UUID
) -> bool:
    """ABAC helper: is ancestor_agent_id an active ancestor of agent_id (or the same
    agent)? Used to authorize branch-scoped access (e.g. network.read_branch)."""
    stmt = select(NetworkClosure.depth).where(
        NetworkClosure.organization_id == organization_id,
        NetworkClosure.ancestor_agent_id == ancestor_agent_id,
        NetworkClosure.descendant_agent_id == agent_id,
        NetworkClosure.effective_to.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def get_branch(
    db: AsyncSession, *, organization_id: uuid.UUID, root_agent_id: uuid.UUID
) -> list[tuple[uuid.UUID, int]]:
    return await _get_active_descendants(db, organization_id=organization_id, agent_id=root_agent_id)


async def create_snapshot_for_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, producer_agent_id: uuid.UUID, reason: str = "contract_activation"
) -> NetworkSnapshot:
    """Freezes the producer's current ancestor chain (with each ancestor's rank at
    this moment) into an immutable snapshot. Called once, at contract activation."""
    from app.domains.network.models import (
        AgentProfile as _AgentProfile,  # local import, avoid cycle at module load
    )

    ancestors = await _get_active_ancestors(db, organization_id=organization_id, agent_id=producer_agent_id)

    snapshot = NetworkSnapshot(organization_id=organization_id, reason=reason)
    db.add(snapshot)
    await db.flush()

    agent_ids = [a for a, _ in ancestors]
    rank_rows = (
        await db.execute(
            select(_AgentProfile.id, _AgentProfile.current_rank_id).where(
                _AgentProfile.id.in_(agent_ids)
            )
        )
    ).all()
    rank_by_agent = {row[0]: row[1] for row in rank_rows}

    for ancestor_id, depth in ancestors:
        db.add(
            NetworkSnapshotNode(
                snapshot_id=snapshot.id,
                ancestor_agent_id=ancestor_id,
                depth=depth,
                rank_id_at_snapshot=rank_by_agent.get(ancestor_id),
            )
        )

    await db.flush()
    return snapshot
