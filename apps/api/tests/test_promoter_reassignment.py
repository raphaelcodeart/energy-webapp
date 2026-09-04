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
    old_agent, old_code = await _make_promoter_with_code(db, organization_id, name="Old Promoter")
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
