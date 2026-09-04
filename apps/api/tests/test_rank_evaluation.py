"""Monthly rank evaluation: promotes/demotes every ACTIVE agent to match a
single calendar month's production (see commissions/services/rank_evaluation.py
and docs/business-rules.md#rank-promotion-progress-placeholder for why this is
a strict monthly window, not the cumulative one rank_progress.py uses)."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.catalog.models import Product, ProductVersion
from app.domains.commissions.models import AgentRankHistory, Rank
from app.domains.commissions.router import run_rank_evaluation
from app.domains.commissions.services.rank_evaluation import (
    previous_calendar_month,
    run_monthly_rank_evaluation,
)
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from app.domains.users.models import User

TARGET_MONTH_START = datetime(2026, 7, 1, tzinfo=UTC)
TARGET_MONTH_END = datetime(2026, 8, 1, tzinfo=UTC)


async def _make_actor(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"re-actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _make_ladder(db, organization_id, *, rule_version):
    s1 = Rank(
        organization_id=organization_id, code="S1", name="Seller 1", level=1,
        personal_token_cents=4000, personal_volume_threshold_cents=0, group_volume_threshold_cents=0,
        valid_from=TARGET_MONTH_START, rule_version=rule_version,
    )
    s2 = Rank(
        organization_id=organization_id, code="S2", name="Seller 2", level=2,
        personal_token_cents=4500, personal_volume_threshold_cents=1500, group_volume_threshold_cents=1500,
        valid_from=TARGET_MONTH_START, rule_version=rule_version,
    )
    db.add_all([s1, s2])
    await db.flush()
    return s1, s2


async def _make_active_contract(db, organization_id, *, producer_agent_id, actor_user_id, price_cents, activated_at):
    product = Product(organization_id=organization_id, code=f"RE-{uuid.uuid4().hex[:6]}", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Rank evaluation test product",
        base_price_cents=price_cents, valid_from=TARGET_MONTH_START,
    )
    db.add(product_version)
    await db.flush()

    customer = Customer(organization_id=organization_id, kind="PRIVATE", email=f"re-{uuid.uuid4().hex[:8]}@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Valutazione 1", city="Roma", province="RM", postal_code="00100",
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
        product_version_id=product_version.id, producer_agent_id=producer_agent_id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING", "PAID", "ACTIVATION_PENDING", "ACTIVE"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    # transition_contract() stamps activated_at with the real clock -- force it
    # into the month under test so the window filter has something to select on.
    contract.activated_at = activated_at
    await db.commit()
    await db.refresh(contract)
    return contract


@pytest.mark.asyncio
async def test_promotes_when_month_volume_crosses_threshold(db, organization_id):
    s1, s2 = await _make_ladder(db, organization_id, rule_version="promo")
    actor_user_id = await _make_actor(db, organization_id)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Rising", last_name="Star", promoter_code=f"RS-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    await _make_active_contract(
        db, organization_id, producer_agent_id=agent.id, actor_user_id=actor_user_id,
        price_cents=2000, activated_at=TARGET_MONTH_START,
    )

    changes = await run_monthly_rank_evaluation(
        db, organization_id=organization_id, window_start=TARGET_MONTH_START, window_end=TARGET_MONTH_END,
    )

    assert len(changes) == 1
    assert changes[0].direction == "PROMOTED"
    assert changes[0].previous_rank_code == "S1"
    assert changes[0].new_rank_code == "S2"

    await db.refresh(agent)
    assert agent.current_rank_id == s2.id

    history = (await db.execute(
        select(AgentRankHistory).where(AgentRankHistory.agent_id == agent.id)
    )).scalars().all()
    assert len(history) == 1
    assert history[0].calculation_source == "AUTOMATIC"


@pytest.mark.asyncio
async def test_demotes_when_month_has_no_production(db, organization_id):
    s1, s2 = await _make_ladder(db, organization_id, rule_version="demo")
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Quiet", last_name="Month", promoter_code=f"QM-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s2.id,
    )
    # No contracts at all this month -- personal/group volume is 0, below S2's threshold.

    changes = await run_monthly_rank_evaluation(
        db, organization_id=organization_id, window_start=TARGET_MONTH_START, window_end=TARGET_MONTH_END,
    )

    assert len(changes) == 1
    assert changes[0].direction == "DEMOTED"
    assert changes[0].previous_rank_code == "S2"
    assert changes[0].new_rank_code == "S1"

    await db.refresh(agent)
    assert agent.current_rank_id == s1.id


@pytest.mark.asyncio
async def test_agent_without_prior_rank_gets_floor_rank(db, organization_id):
    s1, _s2 = await _make_ladder(db, organization_id, rule_version="floor")
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Brand", last_name="New", promoter_code=f"BN-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None,  # no current_rank_id
    )

    changes = await run_monthly_rank_evaluation(
        db, organization_id=organization_id, window_start=TARGET_MONTH_START, window_end=TARGET_MONTH_END,
    )

    assert len(changes) == 1
    assert changes[0].previous_rank_code is None
    assert changes[0].new_rank_code == "S1"
    assert changes[0].direction == "PROMOTED"

    await db.refresh(agent)
    assert agent.current_rank_id == s1.id


@pytest.mark.asyncio
async def test_non_active_agents_are_never_touched(db, organization_id):
    await _make_ladder(db, organization_id, rule_version="skip")
    pending = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Pending", last_name="Tester", promoter_code=f"PE-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, status="PENDING_APPROVAL",
    )
    terminated = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Terminated", last_name="Tester", promoter_code=f"TE-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, status="TERMINATED",
    )

    changes = await run_monthly_rank_evaluation(
        db, organization_id=organization_id, window_start=TARGET_MONTH_START, window_end=TARGET_MONTH_END,
    )

    assert changes == []
    await db.refresh(pending)
    await db.refresh(terminated)
    assert pending.current_rank_id is None
    assert terminated.current_rank_id is None


@pytest.mark.asyncio
async def test_production_outside_window_is_excluded(db, organization_id):
    s1, _s2 = await _make_ladder(db, organization_id, rule_version="window")
    actor_user_id = await _make_actor(db, organization_id)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Last", last_name="Month", promoter_code=f"LM-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    # Big contract, but activated the month BEFORE the evaluated window.
    await _make_active_contract(
        db, organization_id, producer_agent_id=agent.id, actor_user_id=actor_user_id,
        price_cents=5000, activated_at=datetime(2026, 6, 15, tzinfo=UTC),
    )

    changes = await run_monthly_rank_evaluation(
        db, organization_id=organization_id, window_start=TARGET_MONTH_START, window_end=TARGET_MONTH_END,
    )

    assert changes == []  # stays at S1 -- the June contract doesn't count toward July


def test_previous_calendar_month_handles_year_boundary():
    start, end = previous_calendar_month(datetime(2026, 1, 15, tzinfo=UTC))
    assert start == datetime(2025, 12, 1, tzinfo=UTC)
    assert end == datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_manual_endpoint_accepts_explicit_month_and_scopes_to_caller_org(db, organization_id):
    from app.core.deps import CurrentUser

    s1, s2 = await _make_ladder(db, organization_id, rule_version="manual")
    actor_user_id = await _make_actor(db, organization_id)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Manual", last_name="Trigger", promoter_code=f"MT-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    window_start, window_end = previous_calendar_month(TARGET_MONTH_END)
    await _make_active_contract(
        db, organization_id, producer_agent_id=agent.id, actor_user_id=actor_user_id,
        price_cents=2000, activated_at=window_start,
    )

    changes = await run_rank_evaluation(
        month=f"{window_start:%Y-%m}",
        current_user=CurrentUser(user_id=actor_user_id, organization_id=organization_id, roles=["SUPER_ADMIN"]),
        db=db,
    )

    assert len(changes) == 1
    assert changes[0].new_rank_code == "S2"
