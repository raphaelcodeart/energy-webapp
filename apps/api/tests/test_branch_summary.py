"""Covers the promoter "azienda" view aggregations: per-agent/per-level contract
and commission rollups, and flat contract-level detail linking customer/product/
status/commission."""

import uuid
from datetime import UTC, datetime

import pytest

from app.core.security import hash_password
from app.domains.catalog.models import Product, ProductVersion
from app.domains.commissions.models import Rank
from app.domains.commissions.tasks.dispatch import process_pending_outbox_events
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from app.domains.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_actor(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer_agent_id):
    product = Product(organization_id=organization_id, code=f"P-{uuid.uuid4().hex[:6]}", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Test product", base_price_cents=1000, valid_from=NOW,
    )
    db.add(product_version)
    await db.flush()

    customer = Customer(organization_id=organization_id, kind="PRIVATE", email=f"cust-{uuid.uuid4().hex[:6]}@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Test 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY", supply_address_id=address.id,
    )
    db.add(supply_point)
    await db.commit()

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=product_version.id, producer_agent_id=producer_agent_id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    return contract


async def _advance_to_active(db, organization_id, contract, actor_user_id):
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING", "PAID", "ACTIVATION_PENDING", "ACTIVE"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    return contract


async def _advance_to_documents_pending(db, organization_id, contract, actor_user_id):
    for step in ["SUBMITTED", "DOCUMENTS_PENDING"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    return contract


@pytest.mark.asyncio
async def test_branch_summary_counts_contracts_and_commissions_per_agent(db, organization_id):
    s1 = Rank(organization_id=organization_id, code="S1", name="Seller 1", level=1, personal_token_cents=4000, valid_from=NOW, rule_version="test")
    db.add(s1)
    await db.flush()

    sponsor = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Sponsor", promoter_code=f"SP-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    producer = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Producer", promoter_code=f"PR-{uuid.uuid4().hex[:8]}",
        parent_agent_id=sponsor.id, current_rank_id=s1.id,
    )

    actor_user_id = await _make_actor(db, organization_id)

    active_contract = await _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer.id)
    active_contract = await _advance_to_active(db, organization_id, active_contract, actor_user_id)
    await process_pending_outbox_events(db)

    problem_contract = await _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer.id)
    await _advance_to_documents_pending(db, organization_id, problem_contract, actor_user_id)

    summary = await network_service.get_branch_summary(db, organization_id=organization_id, root_agent_id=sponsor.id)

    by_id = {a["agent_id"]: a for a in summary["agents"]}
    producer_row = by_id[producer.id]
    assert producer_row["contracts_total"] == 2
    assert producer_row["contracts_processed"] == 1  # ACTIVE
    assert producer_row["contracts_problem"] == 1  # DOCUMENTS_PENDING
    assert producer_row["commission_cents"] == 4000  # PERSONAL_TOKEN for the active contract

    assert summary["totals"]["contracts"] == 2
    assert summary["totals"]["commission_cents"] == 4000


@pytest.mark.asyncio
async def test_branch_contracts_links_customer_product_status_and_commission(db, organization_id):
    s1 = Rank(organization_id=organization_id, code="S1", name="Seller 1", level=1, personal_token_cents=4000, valid_from=NOW, rule_version="test")
    db.add(s1)
    await db.flush()

    producer = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Solo Producer", promoter_code=f"SOLO-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    actor_user_id = await _make_actor(db, organization_id)

    contract = await _make_contract_ready_to_activate(db, organization_id, actor_user_id, producer.id)
    contract = await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    rows = await network_service.get_branch_contracts(db, organization_id=organization_id, root_agent_id=producer.id)
    assert len(rows) == 1
    row = rows[0]
    assert row["contract_id"] == contract.id
    assert row["status"] == "ACTIVE"
    assert row["commission_cents"] == 4000
    assert row["is_problem"] is False
    assert row["producer_agent_id"] == producer.id
    assert "@example.com" in row["customer_email"]
