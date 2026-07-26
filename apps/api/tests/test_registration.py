"""Covers the invite-only public registration flow: a referral code from a
promoter's shared link is required, no exceptions ("nessuno può stare senza
promoter che lo invita" -- closed circuit)."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.domains.auth import service as auth_service
from app.domains.auth.schemas import RegisterRequest
from app.domains.customers.models import Customer, CustomerProfile
from app.domains.network import service as network_service
from app.domains.rbac.models import Role
from app.domains.referral.models import CustomerAttribution, PromoterCode
from app.domains.referral import service as referral_service
from app.domains.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_customer_role(db, organization_id):
    role = Role(organization_id=organization_id, code="CUSTOMER", name="Customer")
    db.add(role)
    await db.commit()
    return role


async def _make_promoter_with_code(db, organization_id):
    agent = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Referring Promoter",
        promoter_code=f"REF-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    promoter_code = await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=agent.id
    )
    return agent, promoter_code


@pytest.mark.asyncio
async def test_registration_with_valid_referral_code_creates_attributed_customer(db, organization_id):
    await _make_customer_role(db, organization_id)
    agent, promoter_code = await _make_promoter_with_code(db, organization_id)

    payload = RegisterRequest(
        organization_id=str(organization_id),
        referral_code=promoter_code.code,
        email="new.customer@example.com",
        password="correct-horse-battery-staple",
        kind="PRIVATE",
        first_name="Nuovo",
        last_name="Cliente",
    )
    user = await auth_service.register_with_referral(db, organization_id=organization_id, payload=payload)

    assert user.email == "new.customer@example.com"

    customer = (await db.execute(select(Customer).where(Customer.user_id == user.id))).scalar_one()
    assert customer.email == "new.customer@example.com"

    profile = (await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id == customer.id))).scalar_one()
    assert profile.first_name == "Nuovo"

    attribution = (
        await db.execute(select(CustomerAttribution).where(CustomerAttribution.customer_id == customer.id))
    ).scalar_one()
    assert attribution.promoter_code_id == promoter_code.id


@pytest.mark.asyncio
async def test_registration_rejects_invalid_referral_code(db, organization_id):
    await _make_customer_role(db, organization_id)

    payload = RegisterRequest(
        organization_id=str(organization_id),
        referral_code="DOES-NOT-EXIST",
        email="orphan@example.com",
        password="correct-horse-battery-staple",
        kind="PRIVATE",
        first_name="Orfano",
        last_name="Cliente",
    )
    with pytest.raises(auth_service.RegistrationError):
        await auth_service.register_with_referral(db, organization_id=organization_id, payload=payload)

    # No half-created account left behind.
    leftover = (await db.execute(select(User).where(User.email == "orphan@example.com"))).scalar_one_or_none()
    assert leftover is None


@pytest.mark.asyncio
async def test_registration_rejects_duplicate_email(db, organization_id):
    await _make_customer_role(db, organization_id)
    _, promoter_code = await _make_promoter_with_code(db, organization_id)

    payload = RegisterRequest(
        organization_id=str(organization_id),
        referral_code=promoter_code.code,
        email="duplicate@example.com",
        password="correct-horse-battery-staple",
        kind="PRIVATE",
        first_name="Primo",
        last_name="Cliente",
    )
    await auth_service.register_with_referral(db, organization_id=organization_id, payload=payload)

    with pytest.raises(auth_service.RegistrationError):
        await auth_service.register_with_referral(db, organization_id=organization_id, payload=payload)


@pytest.mark.asyncio
async def test_registration_rejects_expired_referral_code(db, organization_id):
    await _make_customer_role(db, organization_id)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Expired Promoter",
        promoter_code=f"EXP-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    expired_code = PromoterCode(
        organization_id=organization_id, agent_id=agent.id, code=f"EXPCODE-{uuid.uuid4().hex[:6]}",
        personal_link="/r/expired", status="ACTIVE",
        valid_from=NOW, valid_to=datetime(2026, 1, 2, tzinfo=UTC),
    )
    db.add(expired_code)
    await db.commit()

    payload = RegisterRequest(
        organization_id=str(organization_id),
        referral_code=expired_code.code,
        email="toolate@example.com",
        password="correct-horse-battery-staple",
        kind="PRIVATE",
        first_name="Troppo",
        last_name="Tardi",
    )
    with pytest.raises(auth_service.RegistrationError):
        await auth_service.register_with_referral(db, organization_id=organization_id, payload=payload)


@pytest.mark.asyncio
async def test_get_or_create_promoter_code_is_idempotent(db, organization_id):
    agent = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Idempotent Promoter",
        promoter_code=f"IDM-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    first = await referral_service.get_or_create_promoter_code(db, organization_id=organization_id, agent_id=agent.id)
    second = await referral_service.get_or_create_promoter_code(db, organization_id=organization_id, agent_id=agent.id)
    assert first.id == second.id
    assert first.code == agent.promoter_code
