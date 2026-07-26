import uuid

import pytest

from app.core.security import hash_password
from app.domains.network import service as network_service
from app.domains.organizations.models import Organization
from app.domains.users.models import User


async def _make_actor(db, organization_id):
    """network_assignment_history/audit_log FK to a real users.id."""
    user = User(
        organization_id=organization_id, email=f"actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


@pytest.mark.asyncio
async def test_branch_isolation_parallel_branches_are_not_ancestors_of_each_other(db, organization_id):
    root_a = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Root A", promoter_code="ROOT-A", parent_agent_id=None,
    )
    child_a = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Child A", promoter_code="CHILD-A",
        parent_agent_id=root_a.id,
    )
    root_b = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Root B", promoter_code="ROOT-B", parent_agent_id=None,
    )

    # root_a IS an ancestor of child_a...
    assert await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root_a.id, agent_id=child_a.id
    )
    # ...but root_b is NOT -- a parallel branch must never be treated as an ancestor.
    assert not await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root_b.id, agent_id=child_a.id
    )


@pytest.mark.asyncio
async def test_closure_table_reflects_full_chain_depth(db, organization_id):
    a = await network_service.create_agent(
        db, organization_id=organization_id, display_name="A", promoter_code="A1", parent_agent_id=None
    )
    b = await network_service.create_agent(
        db, organization_id=organization_id, display_name="B", promoter_code="B1", parent_agent_id=a.id
    )
    c = await network_service.create_agent(
        db, organization_id=organization_id, display_name="C", promoter_code="C1", parent_agent_id=b.id
    )

    branch = await network_service.get_branch(db, organization_id=organization_id, root_agent_id=a.id)
    depths = {row["agent_id"]: row["depth"] for row in branch}
    assert depths[a.id] == 0
    assert depths[b.id] == 1
    assert depths[c.id] == 2


@pytest.mark.asyncio
async def test_move_agent_prevents_cycle(db, organization_id):
    a = await network_service.create_agent(
        db, organization_id=organization_id, display_name="A", promoter_code="A2", parent_agent_id=None
    )
    b = await network_service.create_agent(
        db, organization_id=organization_id, display_name="B", promoter_code="B2", parent_agent_id=a.id
    )

    actor_user_id = await _make_actor(db, organization_id)
    with pytest.raises(network_service.CycleError):
        # a is b's ancestor; making a a child of b would create a cycle.
        await network_service.move_agent(
            db, organization_id=organization_id, agent_id=a.id, new_parent_agent_id=b.id,
            requested_by=actor_user_id, approved_by=None, reason="test",
        )


@pytest.mark.asyncio
async def test_move_agent_relocates_whole_subtree_and_updates_closure(db, organization_id):
    root1 = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Root1", promoter_code="R1", parent_agent_id=None
    )
    root2 = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Root2", promoter_code="R2", parent_agent_id=None
    )
    mover = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Mover", promoter_code="MV", parent_agent_id=root1.id
    )
    movers_child = await network_service.create_agent(
        db, organization_id=organization_id, display_name="MoversChild", promoter_code="MC",
        parent_agent_id=mover.id,
    )

    actor_user_id = await _make_actor(db, organization_id)
    await network_service.move_agent(
        db, organization_id=organization_id, agent_id=mover.id, new_parent_agent_id=root2.id,
        requested_by=actor_user_id, approved_by=actor_user_id, reason="reorg test",
    )

    # mover and its child are no longer under root1...
    assert not await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root1.id, agent_id=mover.id
    )
    assert not await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root1.id, agent_id=movers_child.id
    )
    # ...they are now under root2, and the internal mover->child relationship survives the move.
    assert await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root2.id, agent_id=mover.id
    )
    assert await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root2.id, agent_id=movers_child.id
    )
    assert await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=mover.id, agent_id=movers_child.id
    )


@pytest.mark.asyncio
async def test_multi_tenant_isolation_agents_are_scoped_to_their_organization(db):
    org_a = Organization(name="Org A", status="ACTIVE")
    org_b = Organization(name="Org B", status="ACTIVE")
    db.add_all([org_a, org_b])
    await db.commit()
    await db.refresh(org_a)
    await db.refresh(org_b)

    agent_a = await network_service.create_agent(
        db, organization_id=org_a.id, display_name="Agent A", promoter_code="OA-1", parent_agent_id=None
    )

    # A query scoped to org_b must never find an agent that belongs to org_a, even
    # when given org_a's real agent id -- this is the ABAC/tenancy backstop.
    assert not await network_service.is_ancestor(
        db, organization_id=org_b.id, ancestor_agent_id=agent_a.id, agent_id=agent_a.id
    )
