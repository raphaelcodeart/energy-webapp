"""Session 37: a FROZEN account disappears from the network branch as far
as their upline is concerned -- them AND everyone under them -- while the
admin tier keeps seeing them, flagged is_frozen. Freezing sets
users.status, which until now had no effect at all on the network tree.

Note the two independent "status" concepts these tests keep apart:
AgentProfile.status (the agent lifecycle: ACTIVE/SUSPENDED/...) versus
User.status (the login: ACTIVE/FROZEN). Only the latter drives this.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.domains.network import service as network_service
from app.domains.users import service as users_service
from app.domains.users.models import User


async def _make_agent(db, organization_id, *, name, parent_agent_id=None, with_login=True):
    user_id = None
    if with_login:
        user = User(
            organization_id=organization_id, email=f"{uuid.uuid4().hex[:8]}@example.demo",
            password_hash=hash_password("irrelevant"),
        )
        db.add(user)
        await db.flush()
        user_id = user.id
    first_name, last_name = name.split(" ", 1)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name=first_name, last_name=last_name,
        promoter_code=f"{first_name[:4].upper()}-{uuid.uuid4().hex[:6]}",
        parent_agent_id=parent_agent_id, user_id=user_id, status="ACTIVE",
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def _freeze(db, organization_id, agent, *, actor_user_id):
    await users_service.freeze_user(
        db, organization_id=organization_id, user_id=agent.user_id, actor_user_id=actor_user_id
    )


def _names(branch):
    return {row["display_name"] for row in branch}


@pytest.fixture
async def _actor_id(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"admin-{uuid.uuid4().hex[:8]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


@pytest.mark.asyncio
async def test_frozen_member_is_hidden_from_the_upline_but_visible_to_admin(db, organization_id, _actor_id):
    root = await _make_agent(db, organization_id, name="Root Boss")
    await _make_agent(db, organization_id, name="Normale Attivo", parent_agent_id=root.id)
    congelato = await _make_agent(db, organization_id, name="Congelato Tizio", parent_agent_id=root.id)
    await _freeze(db, organization_id, congelato, actor_user_id=_actor_id)

    for_promoter = await network_service.get_branch(
        db, organization_id=organization_id, root_agent_id=root.id, include_frozen=False
    )
    assert _names(for_promoter) == {"Root Boss", "Normale Attivo"}

    for_admin = await network_service.get_branch(
        db, organization_id=organization_id, root_agent_id=root.id, include_frozen=True
    )
    assert _names(for_admin) == {"Root Boss", "Normale Attivo", "Congelato Tizio"}
    frozen_row = next(r for r in for_admin if r["display_name"] == "Congelato Tizio")
    assert frozen_row["is_frozen"] is True
    assert all(not r["is_frozen"] for r in for_admin if r["display_name"] != "Congelato Tizio")


@pytest.mark.asyncio
async def test_freezing_takes_the_whole_subtree_with_it(db, organization_id, _actor_id):
    """"Nascondi lui e tutto il suo ramo" -- the explicit business choice."""
    root = await _make_agent(db, organization_id, name="Root Boss")
    congelato = await _make_agent(db, organization_id, name="Congelato Tizio", parent_agent_id=root.id)
    figlio = await _make_agent(db, organization_id, name="Figlio Attivo", parent_agent_id=congelato.id)
    await _make_agent(db, organization_id, name="Nipote Attivo", parent_agent_id=figlio.id)
    await _freeze(db, organization_id, congelato, actor_user_id=_actor_id)

    for_promoter = await network_service.get_branch(
        db, organization_id=organization_id, root_agent_id=root.id, include_frozen=False
    )
    # The frozen person AND both generations under them are gone.
    assert _names(for_promoter) == {"Root Boss"}

    for_admin = await network_service.get_branch(
        db, organization_id=organization_id, root_agent_id=root.id, include_frozen=True
    )
    assert _names(for_admin) == {"Root Boss", "Congelato Tizio", "Figlio Attivo", "Nipote Attivo"}


@pytest.mark.asyncio
async def test_unfreezing_brings_them_back(db, organization_id, _actor_id):
    root = await _make_agent(db, organization_id, name="Root Boss")
    congelato = await _make_agent(db, organization_id, name="Congelato Tizio", parent_agent_id=root.id)
    await _make_agent(db, organization_id, name="Figlio Attivo", parent_agent_id=congelato.id)
    await _freeze(db, organization_id, congelato, actor_user_id=_actor_id)

    assert _names(await network_service.get_branch(
        db, organization_id=organization_id, root_agent_id=root.id, include_frozen=False
    )) == {"Root Boss"}

    await users_service.unfreeze_user(
        db, organization_id=organization_id, user_id=congelato.user_id, actor_user_id=_actor_id
    )

    assert _names(await network_service.get_branch(
        db, organization_id=organization_id, root_agent_id=root.id, include_frozen=False
    )) == {"Root Boss", "Congelato Tizio", "Figlio Attivo"}


@pytest.mark.asyncio
async def test_a_frozen_root_hides_the_entire_branch_from_a_promoter(db, organization_id, _actor_id):
    """Degenerate case: the branch root itself is frozen. Nothing is left to
    show -- and critically, no orphan rows leak out referencing a parent
    that was filtered away."""
    root = await _make_agent(db, organization_id, name="Root Boss")
    await _make_agent(db, organization_id, name="Figlio Attivo", parent_agent_id=root.id)
    await _freeze(db, organization_id, root, actor_user_id=_actor_id)

    assert await network_service.get_branch(
        db, organization_id=organization_id, root_agent_id=root.id, include_frozen=False
    ) == []


@pytest.mark.asyncio
async def test_agent_without_a_login_is_never_treated_as_frozen(db, organization_id):
    """An admin-suggested agent can have no User at all (user_id NULL). The
    LEFT JOIN must read that as "not frozen", not hide them."""
    root = await _make_agent(db, organization_id, name="Root Boss")
    await _make_agent(db, organization_id, name="Senza Login", parent_agent_id=root.id, with_login=False)

    branch = await network_service.get_branch(
        db, organization_id=organization_id, root_agent_id=root.id, include_frozen=False
    )
    assert _names(branch) == {"Root Boss", "Senza Login"}
    assert all(not r["is_frozen"] for r in branch)


@pytest.mark.asyncio
async def test_branch_summary_totals_exclude_hidden_members(db, organization_id, _actor_id):
    """A member the caller can't see must not silently inflate their counts."""
    root = await _make_agent(db, organization_id, name="Root Boss")
    congelato = await _make_agent(db, organization_id, name="Congelato Tizio", parent_agent_id=root.id)
    await _make_agent(db, organization_id, name="Figlio Attivo", parent_agent_id=congelato.id)
    await _freeze(db, organization_id, congelato, actor_user_id=_actor_id)

    for_promoter = await network_service.get_branch_summary(
        db, organization_id=organization_id, root_agent_id=root.id, include_frozen=False
    )
    assert {a["display_name"] for a in for_promoter["agents"]} == {"Root Boss"}
    # people_total counts the downline only, excluding the root itself -- so
    # with both members below hidden, the promoter's own headcount is 0.
    assert for_promoter["totals"]["people_total"] == 0

    for_admin = await network_service.get_branch_summary(
        db, organization_id=organization_id, root_agent_id=root.id, include_frozen=True
    )
    assert for_admin["totals"]["people_total"] == 2
