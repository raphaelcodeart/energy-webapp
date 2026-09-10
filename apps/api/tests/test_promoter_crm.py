"""Session 36's "Miei Clienti" promoter CRM: a promoter registers a brand-
new customer themselves (no self-registration/referral-link click needed)
and activates a contract for them, even though the customer has never
logged in. Covers the network-attribution parity with a normal referral
registration, the ownership check that stops a promoter from touching
someone else's customer, and reset_password()'s new email_verified_at
side effect."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.auth import service as auth_service
from app.domains.auth.models import PasswordResetToken
from app.domains.catalog import service as catalog_service
from app.domains.catalog.schemas import ProductCreate
from app.domains.contracts import service as contracts_service
from app.domains.customers.models import Customer
from app.domains.customers.schemas import CustomerCreate
from app.domains.network import service as network_service
from app.domains.rbac.models import Role
from app.domains.referral import service as referral_service
from app.domains.referral.models import CustomerAttribution
from app.domains.users.models import User


async def _make_customer_role(db, organization_id):
    role = Role(organization_id=organization_id, code="CUSTOMER", name="Customer")
    db.add(role)
    await db.commit()
    return role


async def _make_promoter_with_login(db, organization_id, *, name="Test Promoter", status="ACTIVE"):
    first_name, last_name = name.split(" ", 1)
    user = User(
        organization_id=organization_id, email=f"promoter-{uuid.uuid4().hex[:8]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.flush()
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name=first_name, last_name=last_name,
        promoter_code=f"REF-{uuid.uuid4().hex[:8]}", parent_agent_id=None, user_id=user.id, status=status,
    )
    await db.commit()
    await db.refresh(user)
    await db.refresh(agent)
    return agent, user


def _customer_payload(**overrides):
    defaults = dict(
        kind="PRIVATE", email=f"cust-{uuid.uuid4().hex[:8]}@example.demo", phone=None, pec=None,
        fiscal_code=None, vat_number=None, first_name="Mario", last_name="Rossi", company_name=None,
    )
    defaults.update(overrides)
    return CustomerCreate(**defaults)


async def _make_internal_product_version(db, organization_id, actor_user_id, *, energy_type="ELECTRICITY"):
    product = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        payload=ProductCreate(
            code=f"CRM-{uuid.uuid4().hex[:6]}", customer_type="PRIVATE", category="INTERNAL",
            energy_type=energy_type, name="Luce Standard", base_price_cents=5000,
        ),
    )
    _, versions = await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=product.id)
    return versions[0]


def _supply_point_payload(energy_type="ELECTRICITY"):
    from app.domains.customers.schemas import SupplyPointCreate

    return SupplyPointCreate(
        energy_type=energy_type,
        pod_code="IT001E12345678" if energy_type != "GAS" else None,
        pdr_code="00000000000000" if energy_type == "GAS" else None,
        meter_number=None, street="Via Roma 1", city="Milano", province="MI", postal_code="20100", country="IT",
    )


@pytest.mark.asyncio
async def test_promoter_recruits_a_customer_with_login_and_network_attribution(db, organization_id):
    await _make_customer_role(db, organization_id)
    promoter_agent, promoter_user = await _make_promoter_with_login(db, organization_id)

    customer = await network_service.create_recruited_customer(
        db, organization_id=organization_id, promoter_user_id=promoter_user.id,
        payload=_customer_payload(), actor_user_id=promoter_user.id,
    )

    assert customer.user_id is not None
    user = await db.get(User, customer.user_id)
    assert user is not None
    assert user.status == "ACTIVE"
    assert user.email_verified_at is None  # not yet -- "primo accesso" still pending

    attribution = (
        await db.execute(select(CustomerAttribution).where(CustomerAttribution.customer_id == customer.id))
    ).scalar_one()
    promoter_code = await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=promoter_agent.id
    )
    assert attribution.promoter_code_id == promoter_code.id


@pytest.mark.asyncio
async def test_recruiting_a_duplicate_email_is_rejected(db, organization_id):
    await _make_customer_role(db, organization_id)
    _agent, promoter_user = await _make_promoter_with_login(db, organization_id)
    payload = _customer_payload()
    await network_service.create_recruited_customer(
        db, organization_id=organization_id, promoter_user_id=promoter_user.id,
        payload=payload, actor_user_id=promoter_user.id,
    )

    with pytest.raises(network_service.RecruitedCustomerError):
        await network_service.create_recruited_customer(
            db, organization_id=organization_id, promoter_user_id=promoter_user.id,
            payload=payload, actor_user_id=promoter_user.id,
        )


@pytest.mark.asyncio
async def test_non_active_promoter_cannot_recruit_customers(db, organization_id):
    await _make_customer_role(db, organization_id)
    _agent, promoter_user = await _make_promoter_with_login(db, organization_id, status="SUSPENDED")

    with pytest.raises(network_service.RecruitedCustomerError):
        await network_service.create_recruited_customer(
            db, organization_id=organization_id, promoter_user_id=promoter_user.id,
            payload=_customer_payload(), actor_user_id=promoter_user.id,
        )


@pytest.mark.asyncio
async def test_list_recruited_customers_scoped_to_the_calling_promoter(db, organization_id):
    await _make_customer_role(db, organization_id)
    agent_a, user_a = await _make_promoter_with_login(db, organization_id, name="Promoter A")
    agent_b, user_b = await _make_promoter_with_login(db, organization_id, name="Promoter B")

    customer_a = await network_service.create_recruited_customer(
        db, organization_id=organization_id, promoter_user_id=user_a.id,
        payload=_customer_payload(), actor_user_id=user_a.id,
    )
    await network_service.create_recruited_customer(
        db, organization_id=organization_id, promoter_user_id=user_b.id,
        payload=_customer_payload(), actor_user_id=user_b.id,
    )

    rows_a = await network_service.list_recruited_customers(db, organization_id=organization_id, promoter_user_id=user_a.id)
    assert {r["id"] for r in rows_a} == {customer_a.id}


@pytest.mark.asyncio
async def test_promoter_activates_a_contract_for_their_own_recruited_customer(db, organization_id):
    await _make_customer_role(db, organization_id)
    promoter_agent, promoter_user = await _make_promoter_with_login(db, organization_id)
    customer = await network_service.create_recruited_customer(
        db, organization_id=organization_id, promoter_user_id=promoter_user.id,
        payload=_customer_payload(), actor_user_id=promoter_user.id,
    )
    version = await _make_internal_product_version(db, organization_id, promoter_user.id)

    contract = await contracts_service.create_contract_for_recruited_customer(
        db, organization_id=organization_id, promoter_user_id=promoter_user.id, customer_id=customer.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(), email=customer.email,
    )

    assert contract.status == "DOCUMENTS_PENDING"
    from app.domains.contracts.models import ContractAttribution

    attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
    assert attribution.producer_agent_id == promoter_agent.id


@pytest.mark.asyncio
async def test_promoter_cannot_activate_a_contract_for_someone_elses_customer(db, organization_id):
    await _make_customer_role(db, organization_id)
    _agent_a, user_a = await _make_promoter_with_login(db, organization_id, name="Promoter A")
    _agent_b, user_b = await _make_promoter_with_login(db, organization_id, name="Promoter B")
    customer_a = await network_service.create_recruited_customer(
        db, organization_id=organization_id, promoter_user_id=user_a.id,
        payload=_customer_payload(), actor_user_id=user_a.id,
    )
    version = await _make_internal_product_version(db, organization_id, user_a.id)

    with pytest.raises(contracts_service.SelfServiceContractError):
        await contracts_service.create_contract_for_recruited_customer(
            db, organization_id=organization_id, promoter_user_id=user_b.id, customer_id=customer_a.id,
            product_version_id=version.id, supply_point_payload=_supply_point_payload(), email=customer_a.email,
        )


@pytest.mark.asyncio
async def test_reset_password_marks_the_account_email_verified_if_not_already(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"reset-{uuid.uuid4().hex[:8]}@example.demo",
        password_hash=hash_password("old-password"),
    )
    db.add(user)
    await db.flush()
    assert user.email_verified_at is None

    token = "plain-test-token"
    from app.core.security import hash_password_reset_token

    db.add(
        PasswordResetToken(
            user_id=user.id, token_hash=hash_password_reset_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=60),
        )
    )
    await db.commit()

    await auth_service.reset_password(db, token=token, new_password="brand-new-password-123")

    await db.refresh(user)
    assert user.email_verified_at is not None
