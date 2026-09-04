"""Covers the contract renewal/expiry engineering fix: energy contracts have a
12/24-month term and must be renewable every year, not just once. Before this
fix RENEWED was a dead end in the state machine (see state_machine.py) -- a
contract renewed once could never be renewed again, suspended, cancelled, or
left to expire. Also covers expires_at computation from the product version's
contract_duration_months."""

import uuid

import pytest

from app.core.db import utcnow
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from tests.test_commission_engine_integration import _make_actor


async def _make_customer_and_supply_point(db, organization_id):
    customer = Customer(organization_id=organization_id, kind="PRIVATE", email="renew@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Rinnovo 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id,
    )
    db.add(supply_point)
    await db.commit()
    return customer, supply_point


async def _make_product_version(db, organization_id, *, duration_months=12):
    product = Product(organization_id=organization_id, code="TEST-RENEW", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Test renewable product", base_price_cents=1000,
        contract_duration_months=duration_months, valid_from=utcnow(),
    )
    db.add(product_version)
    await db.commit()
    return product_version


async def _make_contract_to_active(db, organization_id, *, duration_months=12):
    actor_user_id = await _make_actor(db, organization_id)
    customer, supply_point = await _make_customer_and_supply_point(db, organization_id)
    product_version = await _make_product_version(db, organization_id, duration_months=duration_months)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Renewal", last_name="Agent",
        promoter_code=f"RA-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=product_version.id, producer_agent_id=agent.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    for to_status in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING", "PAID", "ACTIVATION_PENDING", "ACTIVE"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=to_status,
            actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
        )
    return contract, actor_user_id


@pytest.mark.asyncio
async def test_active_transition_sets_activated_and_expires_at(db, organization_id):
    contract, _ = await _make_contract_to_active(db, organization_id, duration_months=12)
    assert contract.activated_at is not None
    assert contract.expires_at is not None
    delta_days = (contract.expires_at - contract.activated_at).days
    assert 359 <= delta_days <= 366  # ~12 months, accounting for month-length variance


@pytest.mark.asyncio
async def test_product_with_no_duration_leaves_expires_at_null(db, organization_id):
    contract, _ = await _make_contract_to_active(db, organization_id, duration_months=None)
    assert contract.activated_at is not None
    assert contract.expires_at is None


@pytest.mark.asyncio
async def test_contract_can_be_renewed_more_than_once(db, organization_id):
    """The core bug fix: ACTIVE -> RENEWED -> RENEWED must both be legal --
    a contract renews every year of its life, not just once."""
    contract, actor_user_id = await _make_contract_to_active(db, organization_id)
    first_expiry = contract.expires_at

    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="RENEWED",
        actor_user_id=actor_user_id, reason="Year 1 renewal", notes=None, correlation_id=str(uuid.uuid4()),
    )
    assert contract.status == "RENEWED"
    assert contract.expires_at > first_expiry

    second_expiry = contract.expires_at
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="RENEWED",
        actor_user_id=actor_user_id, reason="Year 2 renewal", notes=None, correlation_id=str(uuid.uuid4()),
    )
    assert contract.status == "RENEWED"
    assert contract.expires_at > second_expiry


@pytest.mark.asyncio
async def test_renewed_contract_can_still_be_cancelled(db, organization_id):
    contract, actor_user_id = await _make_contract_to_active(db, organization_id)
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="RENEWED",
        actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
    )
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="CANCELLED",
        actor_user_id=actor_user_id, reason="Customer switched provider", notes=None,
        correlation_id=str(uuid.uuid4()),
    )
    assert contract.status == "CANCELLED"


@pytest.mark.asyncio
async def test_lapsed_expired_contract_can_be_revived_via_renewal(db, organization_id):
    contract, actor_user_id = await _make_contract_to_active(db, organization_id)
    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="EXPIRED",
        actor_user_id=actor_user_id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
    )
    assert contract.status == "EXPIRED"

    contract = await contract_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="RENEWED",
        actor_user_id=actor_user_id, reason="Customer came back", notes=None, correlation_id=str(uuid.uuid4()),
    )
    assert contract.status == "RENEWED"
    assert contract.expires_at is not None
