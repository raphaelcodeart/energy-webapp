import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.security import hash_password
from app.domains.audit.models import AuditLog
from app.domains.catalog.models import Product, ProductVersion
from app.domains.commissions.models import CommissionCalculation, CommissionMovement, Rank
from app.domains.commissions.services.run_calculation import run_calculation_for_contract
from app.domains.commissions.tasks.dispatch import process_pending_outbox_events
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import Contract
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from app.domains.network.models import NetworkSnapshot
from app.domains.organizations.models import Organization
from app.domains.outbox import service as outbox_service
from app.domains.outbox.models import DomainOutbox
from app.domains.users.models import User
from tests.conftest import TEST_DATABASE_URL

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


@pytest.mark.asyncio
async def test_empty_ancestor_chain_records_failed_calculation_not_silent_skip(db, organization_id):
    """docs/paid-contract-commission-audit.md, Problem #1 (defense in depth): even
    though create_contract() now validates producer_agent_id, an empty ancestor
    chain at calculation time must never be silently skipped. Previously:
    run_calculation_for_contract returned None, wrote nothing, and the dispatcher
    still marked the event processed -- a contract could activate and pay nobody
    with zero record of why."""
    customer = Customer(organization_id=organization_id, kind="PRIVATE", email="empty-chain@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Test 2", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id,
    )
    db.add(supply_point)

    product = Product(organization_id=organization_id, code="EMPTY-PROD", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Empty chain product", base_price_cents=1000,
        valid_from=NOW,
    )
    db.add(product_version)

    # A snapshot with zero nodes -- simulates a producer whose ancestor chain
    # could not be resolved.
    snapshot = NetworkSnapshot(organization_id=organization_id, reason="test_empty_chain")
    db.add(snapshot)
    await db.flush()

    contract = Contract(
        organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=product_version.id, contract_attribution_id=None,
        network_snapshot_id=snapshot.id, status="ACTIVE",
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)

    trigger_event_id = uuid.uuid4()
    calculation = await run_calculation_for_contract(
        db, organization_id=organization_id, contract_id=contract.id, trigger_event_id=trigger_event_id,
    )

    assert calculation is not None
    assert calculation.status == "FAILED"

    movements = (await db.execute(
        select(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    )).scalars().all()
    assert movements == []  # no money moved for an unresolved producer

    audit_rows = (await db.execute(
        select(AuditLog).where(
            AuditLog.organization_id == organization_id,
            AuditLog.action == "commission.calculation_failed",
            AuditLog.entity_id == str(contract.id),
        )
    )).scalars().all()
    assert len(audit_rows) == 1  # the failure is now visible, not silent


@pytest.mark.asyncio
async def test_dispatch_isolates_failing_event_from_others(db, organization_id):
    """docs/paid-contract-commission-audit.md, Problem #2: a poisoned event
    (pointing at a contract_id that does not exist) must not block dispatch of
    other, unrelated events in the same batch. Enqueued first, so it is
    processed before the healthy event -- proving the failure doesn't abort the
    rest of the loop."""
    actor_user_id = await _make_actor(db, organization_id)

    poisoned_contract_id = uuid.uuid4()
    db.add(outbox_service.enqueue(
        organization_id=organization_id, event_type="ContractActivated",
        payload={"contract_id": str(poisoned_contract_id), "correlation_id": str(uuid.uuid4())},
    ))
    await db.commit()

    contract = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    contract = await _advance_to_active(db, organization_id, contract, actor_user_id)

    processed = await process_pending_outbox_events(db)
    assert processed >= 1  # the healthy event, at minimum

    movements = (await db.execute(
        select(CommissionMovement).where(CommissionMovement.contract_id == contract.id)
    )).scalars().all()
    assert len(movements) == 2  # healthy contract still got its commissions

    events = (await db.execute(
        select(DomainOutbox).where(
            DomainOutbox.organization_id == organization_id,
            DomainOutbox.event_type == "ContractActivated",
        )
    )).scalars().all()
    poisoned_event = next(e for e in events if e.payload["contract_id"] == str(poisoned_contract_id))
    assert poisoned_event.processed_at is None  # left for retry, not silently dropped

    audit_rows = (await db.execute(
        select(AuditLog).where(
            AuditLog.organization_id == organization_id,
            AuditLog.action == "commission.calculation_error",
            AuditLog.entity_id == str(poisoned_contract_id),
        )
    )).scalars().all()
    assert len(audit_rows) == 1  # the failure was recorded, not swallowed


@pytest.mark.asyncio
async def test_concurrent_calculation_race_is_handled_by_db_constraint():
    """docs/paid-contract-commission-audit.md, Problem #3. Uses two independent,
    truly concurrent DB connections (NOT the shared savepoint-rollback `db`
    fixture, which cannot exercise real concurrency) racing to process the same
    trigger event. Whichever loses the race must be handled gracefully by the
    uq_commission_calculations_contract_trigger constraint, not raise an
    unhandled error -- and exactly one calculation/movement set must exist
    afterwards regardless of how the race actually interleaved."""
    engine = create_async_engine(TEST_DATABASE_URL)
    setup_session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        org = Organization(name=f"Race Org {uuid.uuid4()}", status="ACTIVE")
        setup_session.add(org)
        await setup_session.commit()
        await setup_session.refresh(org)

        actor_user_id = await _make_actor(setup_session, org.id)
        contract = await _setup_contract_ready_to_activate(setup_session, org.id, actor_user_id)
        contract = await _advance_to_active(setup_session, org.id, contract, actor_user_id)

        event = (await setup_session.execute(
            select(DomainOutbox).where(
                DomainOutbox.organization_id == org.id, DomainOutbox.event_type == "ContractActivated"
            )
        )).scalar_one()
        org_id, contract_id, event_id = org.id, contract.id, event.id
    finally:
        await setup_session.close()

    session_a = AsyncSession(bind=engine, expire_on_commit=False)
    session_b = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        results = await asyncio.gather(
            run_calculation_for_contract(session_a, organization_id=org_id, contract_id=contract_id, trigger_event_id=event_id),
            run_calculation_for_contract(session_b, organization_id=org_id, contract_id=contract_id, trigger_event_id=event_id),
            return_exceptions=True,
        )
    finally:
        await session_a.close()
        await session_b.close()

    for result in results:
        assert not isinstance(result, Exception), f"run_calculation_for_contract raised: {result!r}"

    verify_session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        calcs = (await verify_session.execute(
            select(CommissionCalculation).where(
                CommissionCalculation.contract_id == contract_id,
                CommissionCalculation.trigger_event_id == event_id,
            )
        )).scalars().all()
        assert len(calcs) == 1  # exactly one calculation row despite the race

        movements = (await verify_session.execute(
            select(CommissionMovement).where(CommissionMovement.contract_id == contract_id)
        )).scalars().all()
        assert len(movements) == 2  # producer + sponsor, never duplicated
    finally:
        await verify_session.close()

    await engine.dispose()
