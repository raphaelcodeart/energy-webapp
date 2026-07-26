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
async def test_get_branch_returns_parent_agent_id_for_tree_reconstruction(db, organization_id):
    """The frontend tree (branch-visualizer.tsx) builds its hierarchy from
    parent_agent_id, not from row order -- get_branch()'s query has no
    ORDER BY, so relying on pre-order row sequence silently broke the tree
    whenever Postgres didn't happen to return rows in traversal order. This
    covers the fix: every non-root row must carry its real parent, and the
    root itself must have none (its own parent, if any, is outside the
    branch that was fetched)."""
    a = await network_service.create_agent(
        db, organization_id=organization_id, display_name="A", promoter_code=f"PA-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None,
    )
    b = await network_service.create_agent(
        db, organization_id=organization_id, display_name="B", promoter_code=f"PB-{uuid.uuid4().hex[:8]}",
        parent_agent_id=a.id,
    )
    c = await network_service.create_agent(
        db, organization_id=organization_id, display_name="C", promoter_code=f"PC-{uuid.uuid4().hex[:8]}",
        parent_agent_id=b.id,
    )
    d = await network_service.create_agent(
        db, organization_id=organization_id, display_name="D", promoter_code=f"PD-{uuid.uuid4().hex[:8]}",
        parent_agent_id=b.id,
    )

    branch = await network_service.get_branch(db, organization_id=organization_id, root_agent_id=a.id)
    parent_by_agent = {row["agent_id"]: row["parent_agent_id"] for row in branch}

    assert parent_by_agent[a.id] is None
    assert parent_by_agent[b.id] == a.id
    assert parent_by_agent[c.id] == b.id
    assert parent_by_agent[d.id] == b.id


@pytest.mark.asyncio
async def test_get_branch_from_a_non_root_agent_hides_its_own_parent(db, organization_id):
    """Fetching the branch rooted at B (not the whole org's root A) must not
    include A -- and B's own parent_agent_id in that fetch must be None, since
    A was never fetched and the frontend must not try to attach B to a node
    it doesn't have."""
    a = await network_service.create_agent(
        db, organization_id=organization_id, display_name="A", promoter_code=f"QA-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None,
    )
    b = await network_service.create_agent(
        db, organization_id=organization_id, display_name="B", promoter_code=f"QB-{uuid.uuid4().hex[:8]}",
        parent_agent_id=a.id,
    )
    c = await network_service.create_agent(
        db, organization_id=organization_id, display_name="C", promoter_code=f"QC-{uuid.uuid4().hex[:8]}",
        parent_agent_id=b.id,
    )

    branch = await network_service.get_branch(db, organization_id=organization_id, root_agent_id=b.id)
    agent_ids = {row["agent_id"] for row in branch}
    parent_by_agent = {row["agent_id"]: row["parent_agent_id"] for row in branch}

    assert a.id not in agent_ids
    assert parent_by_agent[b.id] is None
    assert parent_by_agent[c.id] == b.id


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
