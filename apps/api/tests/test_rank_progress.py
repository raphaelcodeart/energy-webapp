"""Rank promotion progress: personal/group cumulative contract value vs. the
NEXT rank's placeholder thresholds (see commissions/services/rank_progress.py
and docs/open-questions.md #1 for why these figures are a placeholder)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.core.security import hash_password
from app.domains.catalog.models import Product, ProductVersion
from app.domains.commissions.models import Rank
from app.domains.commissions.services.rank_progress import get_rank_progress
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from app.domains.users.models import User

NOW = datetime(2026, 7, 27, tzinfo=UTC)


async def _make_actor(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"rp-actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _make_active_contract(db, organization_id, *, producer_agent_id, actor_user_id, price_cents=1000):
    product = Product(organization_id=organization_id, code=f"RP-{uuid.uuid4().hex[:6]}", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Rank progress test product",
        base_price_cents=price_cents, valid_from=NOW,
    )
    db.add(product_version)
    await db.flush()

    customer = Customer(organization_id=organization_id, kind="PRIVATE", email=f"rp-{uuid.uuid4().hex[:8]}@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Rank 1", city="Roma", province="RM", postal_code="00100",
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
    return contract


@pytest.mark.asyncio
async def test_rank_progress_reports_personal_volume_and_next_rank_thresholds(db, organization_id):
    s1 = Rank(
        organization_id=organization_id, code="S1", name="Seller 1", level=1,
        personal_token_cents=4000, personal_volume_threshold_cents=0, group_volume_threshold_cents=0,
        valid_from=NOW, rule_version="test",
    )
    s2 = Rank(
        organization_id=organization_id, code="S2", name="Seller 2", level=2,
        personal_token_cents=4500, personal_volume_threshold_cents=1500, group_volume_threshold_cents=1500,
        valid_from=NOW, rule_version="test",
    )
    db.add_all([s1, s2])
    await db.flush()

    actor_user_id = await _make_actor(db, organization_id)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Producer", last_name="Tester", promoter_code=f"PR-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    await _make_active_contract(db, organization_id, producer_agent_id=agent.id, actor_user_id=actor_user_id, price_cents=1000)

    progress = await get_rank_progress(db, organization_id=organization_id, agent_id=agent.id)

    assert progress.current_rank_code == "S1"
    assert progress.next_rank_code == "S2"
    assert progress.is_max_rank is False
    assert progress.personal_volume_cents == 1000
    assert progress.personal_volume_threshold_cents == 1500
    assert progress.group_volume_cents == 1000
    assert progress.group_volume_threshold_cents == 1500


@pytest.mark.asyncio
async def test_rank_progress_group_volume_includes_downline_but_personal_does_not(db, organization_id):
    s1 = Rank(
        organization_id=organization_id, code="S1", name="Seller 1", level=1,
        personal_token_cents=4000, personal_volume_threshold_cents=0, group_volume_threshold_cents=0,
        valid_from=NOW, rule_version="test2",
    )
    s2 = Rank(
        organization_id=organization_id, code="S2", name="Seller 2", level=2,
        personal_token_cents=4500, personal_volume_threshold_cents=2000, group_volume_threshold_cents=500,
        valid_from=NOW, rule_version="test2",
    )
    db.add_all([s1, s2])
    await db.flush()

    actor_user_id = await _make_actor(db, organization_id)
    sponsor = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Sponsor", last_name="Tester", promoter_code=f"SP-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=s1.id,
    )
    producer = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Producer", last_name="Tester", promoter_code=f"PR-{uuid.uuid4().hex[:8]}",
        parent_agent_id=sponsor.id, current_rank_id=s1.id,
    )
    await _make_active_contract(db, organization_id, producer_agent_id=producer.id, actor_user_id=actor_user_id, price_cents=1000)

    sponsor_progress = await get_rank_progress(db, organization_id=organization_id, agent_id=sponsor.id)
    assert sponsor_progress.personal_volume_cents == 0  # sponsor produced nothing personally
    assert sponsor_progress.group_volume_cents == 1000  # but the downline's contract counts toward the group

    producer_progress = await get_rank_progress(db, organization_id=organization_id, agent_id=producer.id)
    assert producer_progress.personal_volume_cents == 1000
    assert producer_progress.group_volume_cents == 1000  # producer has no downline of their own


@pytest.mark.asyncio
async def test_rank_progress_is_max_rank_when_no_higher_rank_exists(db, organization_id):
    top = Rank(
        organization_id=organization_id, code="MD5", name="Manager Director 5", level=12,
        personal_token_cents=9500, personal_volume_threshold_cents=3000, group_volume_threshold_cents=45000,
        valid_from=NOW, rule_version="test3",
    )
    db.add(top)
    await db.flush()

    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Top", last_name="Agent", promoter_code=f"TOP-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None, current_rank_id=top.id,
    )

    progress = await get_rank_progress(db, organization_id=organization_id, agent_id=agent.id)
    assert progress.is_max_rank is True
    assert progress.next_rank_code is None
    assert progress.personal_volume_threshold_cents == 0
    assert progress.group_volume_threshold_cents == 0


@pytest.mark.asyncio
async def test_rank_progress_with_no_rank_assigned(db, organization_id):
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="No", last_name="Rank Agent", promoter_code=f"NR-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None,
    )
    progress = await get_rank_progress(db, organization_id=organization_id, agent_id=agent.id)
    assert progress.current_rank_code is None
    assert progress.next_rank_code is None
    assert progress.is_max_rank is False
