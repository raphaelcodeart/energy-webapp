"""Covers docs/paid-contract-commission-audit.md, Problem #1: a contract created
with a producer_agent_id that does not resolve to a real, active agent in the
right organization must be rejected at creation time, not silently accepted and
left to fail commission calculation later with zero visibility."""

import uuid

import pytest

from app.domains.contracts import service as contract_service
from app.domains.contracts.service import InvalidProducerAgentError
from app.domains.network import service as network_service
from app.domains.organizations.models import Organization
from app.domains.catalog.models import Product, ProductVersion
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.core.db import utcnow

from tests.test_commission_engine_integration import _make_actor


async def _make_customer_and_supply_point(db, organization_id):
    customer = Customer(organization_id=organization_id, kind="PRIVATE", email="test@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Test 1", city="Roma", province="RM", postal_code="00100",
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


async def _make_product_version(db, organization_id):
    product = Product(organization_id=organization_id, code="TEST-PROD", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Test product", base_price_cents=1000,
        valid_from=utcnow(),
    )
    db.add(product_version)
    await db.commit()
    return product_version


@pytest.mark.asyncio
async def test_create_contract_rejects_unknown_producer_agent(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    customer, supply_point = await _make_customer_and_supply_point(db, organization_id)
    product_version = await _make_product_version(db, organization_id)

    with pytest.raises(InvalidProducerAgentError):
        await contract_service.create_contract(
            db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
            product_version_id=product_version.id, producer_agent_id=uuid.uuid4(),
            actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
        )


@pytest.mark.asyncio
async def test_create_contract_rejects_producer_from_another_organization(db, organization_id):
    other_org = Organization(name=f"Other Org {uuid.uuid4()}", status="ACTIVE")
    db.add(other_org)
    await db.commit()
    await db.refresh(other_org)

    foreign_agent = await network_service.create_agent(
        db, organization_id=other_org.id, display_name="Foreign Agent",
        promoter_code=f"FA-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )

    actor_user_id = await _make_actor(db, organization_id)
    customer, supply_point = await _make_customer_and_supply_point(db, organization_id)
    product_version = await _make_product_version(db, organization_id)

    with pytest.raises(InvalidProducerAgentError):
        await contract_service.create_contract(
            db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
            product_version_id=product_version.id, producer_agent_id=foreign_agent.id,
            actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
        )


@pytest.mark.asyncio
async def test_create_contract_rejects_non_active_producer(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    customer, supply_point = await _make_customer_and_supply_point(db, organization_id)
    product_version = await _make_product_version(db, organization_id)

    agent = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Suspended Agent",
        promoter_code=f"SA-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    agent.status = "SUSPENDED"
    await db.commit()

    with pytest.raises(InvalidProducerAgentError):
        await contract_service.create_contract(
            db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
            product_version_id=product_version.id, producer_agent_id=agent.id,
            actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
        )


@pytest.mark.asyncio
async def test_create_contract_accepts_valid_active_producer(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    customer, supply_point = await _make_customer_and_supply_point(db, organization_id)
    product_version = await _make_product_version(db, organization_id)

    agent = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Valid Agent",
        promoter_code=f"VA-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=product_version.id, producer_agent_id=agent.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    assert contract.status == "DRAFT"
