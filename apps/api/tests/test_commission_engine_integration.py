import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.catalog.models import Product, ProductVersion
from app.domains.commissions.models import CommissionMovement, Rank
from app.domains.commissions.tasks.dispatch import process_pending_outbox_events
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from app.domains.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_actor(db, organization_id):
    """contract_status_history/audit_log FK to a real users.id -- a random UUID
    is not a valid actor."""
    user = User(
        organization_id=organization_id, email=f"actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _setup_contract_ready_to_activate(db, organization_id, actor_user_id):
    """Builds: producer (S1) -> sponsor (S2), a product, a customer + supply point,
    and a DRAFT contract. Returns the contract."""
    s1 = Rank(
        organization_id=organization_id, code="S1", name="Seller 1", level=1,
        personal_token_cents=4000, valid_from=NOW, rule_version="test",
    )
    s2 = Rank(
        organization_id=organization_id, code="S2", name="Seller 2", level=2,
        personal_token_cents=4500, valid_from=NOW, rule_version="test",
    )
    db.add_all([s1, s2])
    await db.flush()

    sponsor = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Sponsor", promoter_code=f"SP-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s2.id,
    )
    producer = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Producer", promoter_code=f"PR-{uuid.uuid4().hex[:8]}",
        parent_agent_id=sponsor.id, current_rank_id=s1.id,
    )

    product = Product(organization_id=organization_id, code="TEST-PROD", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Test product", base_price_cents=1000,
        valid_from=NOW,
    )
    db.add(product_version)
    await db.flush()

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

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=product_version.id, producer_agent_id=producer.id,
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


@pytest.mark.asyncio
async def test_activation_generates_expected_commission_movements(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)

    processed = await process_pending_outbox_events(db)
    assert processed >= 1

    stmt = select(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    movements = (await db.execute(stmt)).scalars().all()

    # producer (S1, 4000) + sponsor entrepreneurial difference (4500-4000=500)
    assert len(movements) == 2
    amounts = sorted(m.amount_cents for m in movements)
    assert amounts == [500, 4000]


@pytest.mark.asyncio
async def test_reprocessing_outbox_does_not_duplicate_movements(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)

    first_count = await process_pending_outbox_events(db)
    second_count = await process_pending_outbox_events(db)  # nothing left unprocessed
    assert first_count >= 1
    assert second_count == 0  # no unprocessed events remain -- not a re-run of the same ones

    stmt = select(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    movements = (await db.execute(stmt)).scalars().all()
    assert len(movements) == 2  # still exactly 2, no duplicates


@pytest.mark.asyncio
async def test_commission_calculation_is_scoped_to_its_organization(db):
    from app.domains.organizations.models import Organization

    org_a = Organization(name="Org A", status="ACTIVE")
    org_b = Organization(name="Org B", status="ACTIVE")
    db.add_all([org_a, org_b])
    await db.commit()
    await db.refresh(org_a)
    await db.refresh(org_b)

    actor_user_id = await _make_actor(db, org_a.id)
    contract_a = await _setup_contract_ready_to_activate(db, org_a.id, actor_user_id)
    await _advance_to_active(db, org_a.id, contract_a, actor_user_id)
    await process_pending_outbox_events(db)

    stmt = select(CommissionMovement).where(CommissionMovement.organization_id == org_b.id)
    org_b_movements = (await db.execute(stmt)).scalars().all()
    assert org_b_movements == []  # org B must see zero movements from org A's activity
