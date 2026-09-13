"""Covers admin reassignment of a customer's attributed promoter: the
customer must always end up attributed to SOMEONE ("nessuno può stare senza
promoter che lo invita"), the AttributionCorrection audit trail records the
move, and reassigning to the same promoter (a no-op) is rejected rather than
silently accepted."""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.auth import service as auth_service
from app.domains.auth.schemas import RegisterRequest
from app.domains.customers.models import Customer
from app.domains.network import service as network_service
from app.domains.rbac.models import Role
from app.domains.referral import service as referral_service
from app.domains.referral.models import AttributionCorrection, CustomerAttribution
from app.domains.users.models import User


async def _make_customer_role(db, organization_id):
    role = Role(organization_id=organization_id, code="CUSTOMER", name="Customer")
    db.add(role)
    await db.commit()
    return role


async def _make_promoter_with_code(db, organization_id, *, name="Default Promoter"):
    first_name, last_name = name.split(" ", 1)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name=first_name, last_name=last_name,
        promoter_code=f"REF-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    promoter_code = await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=agent.id
    )
    return agent, promoter_code


async def _make_registered_customer(db, organization_id, promoter_code):
    payload = RegisterRequest(
        organization_id=str(organization_id), referral_code=promoter_code.code,
        email=f"cust-{uuid.uuid4().hex[:8]}@example.com", password="correct-horse-battery-staple",
        kind="PRIVATE", first_name="Test", last_name="Customer",
    )
    user = await auth_service.register_with_referral(db, organization_id=organization_id, payload=payload)
    customer = (await db.execute(select(Customer).where(Customer.user_id == user.id))).scalar_one()
    return customer


async def _make_actor(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


@pytest.mark.asyncio
async def test_reassign_customer_promoter_moves_attribution(db, organization_id):
    await _make_customer_role(db, organization_id)
    _old_agent, old_code = await _make_promoter_with_code(db, organization_id, name="Old Promoter")
    new_agent, _ = await _make_promoter_with_code(db, organization_id, name="New Promoter")
    customer = await _make_registered_customer(db, organization_id, old_code)
    actor_user_id = await _make_actor(db, organization_id)

    updated = await referral_service.reassign_customer_promoter(
        db, organization_id=organization_id, customer_id=customer.id, new_agent_id=new_agent.id,
        requested_by=actor_user_id, reason="Cliente ha chiesto di cambiare venditore",
    )

    new_code = (
        await db.execute(select(CustomerAttribution).where(CustomerAttribution.customer_id == customer.id))
    ).scalar_one()
    assert new_code.promoter_code_id == updated.promoter_code_id
    assert new_code.promoter_code_id != old_code.id

    correction = (
        await db.execute(select(AttributionCorrection).where(AttributionCorrection.customer_attribution_id == updated.id))
    ).scalar_one()
    assert correction.previous_promoter_code_id == old_code.id
    assert correction.requested_by == actor_user_id
    assert correction.reason == "Cliente ha chiesto di cambiare venditore"


@pytest.mark.asyncio
async def test_reassign_to_same_promoter_is_rejected(db, organization_id):
    await _make_customer_role(db, organization_id)
    agent, code = await _make_promoter_with_code(db, organization_id)
    customer = await _make_registered_customer(db, organization_id, code)
    actor_user_id = await _make_actor(db, organization_id)

    with pytest.raises(referral_service.ReassignmentError):
        await referral_service.reassign_customer_promoter(
            db, organization_id=organization_id, customer_id=customer.id, new_agent_id=agent.id,
            requested_by=actor_user_id, reason="no-op",
        )


@pytest.mark.asyncio
async def test_reassign_customer_with_no_attribution_is_rejected(db, organization_id):
    customer = Customer(organization_id=organization_id, kind="PRIVATE", email="noattr@example.com")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    new_agent, _ = await _make_promoter_with_code(db, organization_id)
    actor_user_id = await _make_actor(db, organization_id)

    with pytest.raises(referral_service.ReassignmentError):
        await referral_service.reassign_customer_promoter(
            db, organization_id=organization_id, customer_id=customer.id, new_agent_id=new_agent.id,
            requested_by=actor_user_id, reason="test",
        )


async def _promote_customer_to_agent(db, organization_id, customer, *, parent_agent_id, name="Dual Role"):
    """Makes an existing registered customer ALSO a promoter, placed under
    parent_agent_id -- the dual-role situation Session 37's tree-follow
    behaviour exists for."""
    first_name, last_name = name.split(" ", 1)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name=first_name, last_name=last_name,
        promoter_code=f"DUAL-{uuid.uuid4().hex[:8]}", parent_agent_id=parent_agent_id,
        user_id=customer.user_id, status="ACTIVE",
    )
    await db.commit()
    await db.refresh(agent)
    return agent


async def _active_parent_of(db, organization_id, agent_id):
    node = await network_service.get_active_node(db, organization_id=organization_id, agent_id=agent_id)
    return node.direct_parent_agent_id if node is not None else None


async def _attributed_agent_id(db, customer_id):
    from app.domains.referral.models import PromoterCode

    attribution = (
        await db.execute(select(CustomerAttribution).where(CustomerAttribution.customer_id == customer_id))
    ).scalar_one()
    code = (
        await db.execute(select(PromoterCode).where(PromoterCode.id == attribution.promoter_code_id))
    ).scalar_one()
    return code.agent_id


@pytest.mark.asyncio
async def test_reassigning_a_dual_role_person_also_moves_them_in_the_network_tree(db, organization_id):
    """The bug this fixes: reassigning someone who is both customer and
    promoter moved only their customer attribution, leaving them hanging
    under the OLD promoter in the commission tree."""
    await _make_customer_role(db, organization_id)
    old_agent, old_code = await _make_promoter_with_code(db, organization_id, name="Old Promoter")
    new_agent, _ = await _make_promoter_with_code(db, organization_id, name="New Promoter")
    customer = await _make_registered_customer(db, organization_id, old_code)
    dual_agent = await _promote_customer_to_agent(db, organization_id, customer, parent_agent_id=old_agent.id)
    actor_user_id = await _make_actor(db, organization_id)

    assert await _active_parent_of(db, organization_id, dual_agent.id) == old_agent.id

    await referral_service.reassign_customer_promoter(
        db, organization_id=organization_id, customer_id=customer.id, new_agent_id=new_agent.id,
        requested_by=actor_user_id, reason="Passa a un altro promoter",
    )

    # Both halves moved: the customer attribution AND the tree position.
    assert await _attributed_agent_id(db, customer.id) == new_agent.id
    assert await _active_parent_of(db, organization_id, dual_agent.id) == new_agent.id


@pytest.mark.asyncio
async def test_reassigning_a_dual_role_person_brings_their_downline_along(db, organization_id):
    """"tutto e' sotto il nuovo, come se lo avesse iscritto lui" -- the whole
    subtree follows, not just the person."""
    await _make_customer_role(db, organization_id)
    old_agent, old_code = await _make_promoter_with_code(db, organization_id, name="Old Promoter")
    new_agent, _ = await _make_promoter_with_code(db, organization_id, name="New Promoter")
    customer = await _make_registered_customer(db, organization_id, old_code)
    dual_agent = await _promote_customer_to_agent(db, organization_id, customer, parent_agent_id=old_agent.id)
    downline = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Sub", last_name="Ordinate",
        promoter_code=f"SUB-{uuid.uuid4().hex[:8]}", parent_agent_id=dual_agent.id, status="ACTIVE",
    )
    await db.commit()
    actor_user_id = await _make_actor(db, organization_id)

    await referral_service.reassign_customer_promoter(
        db, organization_id=organization_id, customer_id=customer.id, new_agent_id=new_agent.id,
        requested_by=actor_user_id, reason="Passa a un altro promoter",
    )

    # The downline stays under the moved person, who is now under the new promoter.
    assert await _active_parent_of(db, organization_id, dual_agent.id) == new_agent.id
    assert await _active_parent_of(db, organization_id, downline.id) == dual_agent.id


@pytest.mark.asyncio
async def test_reassigning_a_plain_customer_touches_no_network_tree(db, organization_id):
    """A customer who is NOT a promoter must behave exactly as before --
    attribution moves, nothing else happens."""
    from app.domains.network.models import NetworkAssignmentHistory

    await _make_customer_role(db, organization_id)
    _old_agent, old_code = await _make_promoter_with_code(db, organization_id, name="Old Promoter")
    new_agent, _ = await _make_promoter_with_code(db, organization_id, name="New Promoter")
    customer = await _make_registered_customer(db, organization_id, old_code)
    actor_user_id = await _make_actor(db, organization_id)

    before = len((await db.execute(select(NetworkAssignmentHistory))).scalars().all())

    await referral_service.reassign_customer_promoter(
        db, organization_id=organization_id, customer_id=customer.id, new_agent_id=new_agent.id,
        requested_by=actor_user_id, reason="Solo cliente",
    )

    assert await _attributed_agent_id(db, customer.id) == new_agent.id
    after = len((await db.execute(select(NetworkAssignmentHistory))).scalars().all())
    assert after == before  # no tree move was recorded


@pytest.mark.asyncio
async def test_reassigning_under_your_own_downline_is_rejected_and_changes_nothing(db, organization_id):
    """Moving someone under their own descendant would create a cycle. The
    whole reassignment must fail atomically -- never leave the customer
    reassigned but stranded in the old tree position."""
    await _make_customer_role(db, organization_id)
    old_agent, old_code = await _make_promoter_with_code(db, organization_id, name="Old Promoter")
    customer = await _make_registered_customer(db, organization_id, old_code)
    dual_agent = await _promote_customer_to_agent(db, organization_id, customer, parent_agent_id=old_agent.id)
    # This agent sits UNDER the dual-role person -- reassigning the person to
    # them would make the person their own descendant's child.
    descendant = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Giu", last_name="Sotto",
        promoter_code=f"DESC-{uuid.uuid4().hex[:8]}", parent_agent_id=dual_agent.id, status="ACTIVE",
    )
    await db.commit()
    actor_user_id = await _make_actor(db, organization_id)

    with pytest.raises(referral_service.ReassignmentError):
        await referral_service.reassign_customer_promoter(
            db, organization_id=organization_id, customer_id=customer.id, new_agent_id=descendant.id,
            requested_by=actor_user_id, reason="Ciclo",
        )

    # Tree untouched.
    assert await _active_parent_of(db, organization_id, dual_agent.id) == old_agent.id
