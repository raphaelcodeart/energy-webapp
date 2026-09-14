"""Bonus al PRIMO promoter che ha portato il cliente.

The rule, stated by the business: on top of the commission the plan already
pays, a product can carry an extra one-off bonus -- 25 EUR on the "BAR /
Energia Circolare" contract -- and that bonus goes **exclusively** to the
promoter who originally brought the customer into Lial Energy.

That makes two concepts that look identical in the ordinary case and come
apart in exactly the situation this bonus exists for:

  - the REFERRER / INVITER: whoever's link (or CRM registration) the customer
    arrived through. A property of the CUSTOMER. Frozen onto the contract at
    creation as `contracts.first_referrer_agent_id`.
  - the PRODUCER: whoever actually filled this contract in, and therefore
    earns the recursive commission. A property of the CONTRACT
    (`contract_attributions.producer_agent_id`).

The tests below pin down that the bonus follows the first of those, never the
second, that it is additive rather than a replacement, and that it can only
ever be paid once per contract -- not once per activation, and not once per
webhook delivery.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.catalog.models import Product, ProductVersion
from app.domains.commissions.models import CommissionMovement, Rank
from app.domains.commissions.services.run_calculation import (
    FIRST_REFERRER_BONUS_MOVEMENT_TYPE,
    run_calculation_for_contract,
)
from app.domains.commissions.tasks.dispatch import process_pending_outbox_events
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from app.domains.referral import service as referral_service
from app.domains.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)
BONUS_CENTS = 25_00


async def _make_actor(db, organization_id) -> uuid.UUID:
    user = User(
        organization_id=organization_id, email=f"actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _make_agent(db, organization_id, *, name: str, parent_agent_id=None, rank_id=None):
    return await network_service.create_agent(
        db, organization_id=organization_id, first_name=name, last_name="Tester",
        promoter_code=f"{name[:2].upper()}-{uuid.uuid4().hex[:8]}",
        parent_agent_id=parent_agent_id, current_rank_id=rank_id,
    )


async def _make_product(db, organization_id, *, bonus_enabled: bool, bonus_cents: int = BONUS_CENTS):
    product = Product(
        organization_id=organization_id, code=f"BAR-{uuid.uuid4().hex[:6]}",
        energy_type="ELECTRICITY", customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="BAR Energia Circolare",
        base_price_cents=249_00, valid_from=NOW,
        # The recursive commission the plan already pays, untouched by the bonus.
        commission_tokens={"S1": 80_00},
        first_referrer_bonus_enabled=bonus_enabled,
        first_referrer_bonus_cents=bonus_cents,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


async def _make_customer_referred_by(db, organization_id, referrer_agent_id):
    """A customer attributed to `referrer_agent_id` -- i.e. one who arrived
    through that promoter's link, the same CustomerAttribution row that
    registration and the promoter CRM both write."""
    customer = Customer(
        organization_id=organization_id, kind="PRIVATE", email=f"c-{uuid.uuid4().hex[:8]}@example.com"
    )
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
    await db.flush()

    code = await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=referrer_agent_id
    )
    await referral_service.attribute_customer(
        db, organization_id=organization_id, customer_id=customer.id,
        promoter_code_id=code.id, referral_session_id=None,
    )
    await db.commit()
    return customer, supply_point


async def _activate(db, organization_id, contract, actor_user_id):
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAID"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    await process_pending_outbox_events(db)
    return contract


async def _movements(db, contract_id):
    return list(
        (
            await db.execute(select(CommissionMovement).where(CommissionMovement.contract_id == contract_id))
        ).scalars()
    )


@pytest.mark.asyncio
async def test_bonus_goes_to_the_first_referrer_not_the_promoter_who_filled_it_in(db, organization_id):
    """The case the whole feature exists for: Anna brought the customer in,
    Bruno sat down with them and completed the contract. Bruno earns the
    ordinary commission for producing it; the 25 EUR bonus is Anna's."""
    actor_user_id = await _make_actor(db, organization_id)
    rank = Rank(
        organization_id=organization_id, code="S1", name="Seller 1", level=1,
        personal_token_cents=80_00, valid_from=NOW, rule_version="test",
    )
    db.add(rank)
    await db.flush()

    anna = await _make_agent(db, organization_id, name="Anna", rank_id=rank.id)
    bruno = await _make_agent(db, organization_id, name="Bruno", rank_id=rank.id)
    version = await _make_product(db, organization_id, bonus_enabled=True)
    customer, supply_point = await _make_customer_referred_by(db, organization_id, anna.id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id,
        # Bruno is the producer -- he filled it in.
        producer_agent_id=bruno.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    assert contract.first_referrer_agent_id == anna.id

    await _activate(db, organization_id, contract, actor_user_id)
    movements = await _movements(db, contract.id)

    bonuses = [m for m in movements if m.movement_type == FIRST_REFERRER_BONUS_MOVEMENT_TYPE]
    assert len(bonuses) == 1
    assert bonuses[0].agent_id == anna.id
    assert bonuses[0].amount_cents == BONUS_CENTS

    # Additive, never a replacement: Bruno still gets the full 80 EUR the
    # plan already paid before this feature existed.
    bruno_ordinary = [
        m for m in movements
        if m.agent_id == bruno.id and m.movement_type != FIRST_REFERRER_BONUS_MOVEMENT_TYPE
    ]
    assert sum(m.amount_cents for m in bruno_ordinary) == 80_00
    # ...and Bruno gets no bonus, because he is not the first referrer.
    assert not [m for m in bonuses if m.agent_id == bruno.id]


@pytest.mark.asyncio
async def test_bonus_is_paid_once_even_if_the_calculation_runs_again(db, organization_id):
    """Not once per activation, not once per replayed event: once per
    contract. The idempotency key deliberately leaves the trigger event out,
    so the UNIQUE constraint is the guarantee even if the readable check is
    bypassed."""
    actor_user_id = await _make_actor(db, organization_id)
    rank = Rank(
        organization_id=organization_id, code="S1", name="Seller 1", level=1,
        personal_token_cents=80_00, valid_from=NOW, rule_version="test",
    )
    db.add(rank)
    await db.flush()

    anna = await _make_agent(db, organization_id, name="Anna", rank_id=rank.id)
    version = await _make_product(db, organization_id, bonus_enabled=True)
    customer, supply_point = await _make_customer_referred_by(db, organization_id, anna.id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=anna.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    contract = await _activate(db, organization_id, contract, actor_user_id)

    # A second, independent calculation for the same contract -- what a
    # renewal or a re-dispatched event looks like to this code.
    await run_calculation_for_contract(
        db, organization_id=organization_id, contract_id=contract.id, trigger_event_id=uuid.uuid4()
    )

    movements = await _movements(db, contract.id)
    bonuses = [m for m in movements if m.movement_type == FIRST_REFERRER_BONUS_MOVEMENT_TYPE]
    assert len(bonuses) == 1
    assert sum(m.amount_cents for m in bonuses) == BONUS_CENTS


@pytest.mark.asyncio
async def test_no_bonus_when_the_product_does_not_configure_one(db, organization_id):
    """The default for every product that exists today. The bonus must be a
    value an admin sets, never something inferred from a price."""
    actor_user_id = await _make_actor(db, organization_id)
    rank = Rank(
        organization_id=organization_id, code="S1", name="Seller 1", level=1,
        personal_token_cents=80_00, valid_from=NOW, rule_version="test",
    )
    db.add(rank)
    await db.flush()

    anna = await _make_agent(db, organization_id, name="Anna", rank_id=rank.id)
    version = await _make_product(db, organization_id, bonus_enabled=False)
    customer, supply_point = await _make_customer_referred_by(db, organization_id, anna.id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=anna.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    await _activate(db, organization_id, contract, actor_user_id)

    movements = await _movements(db, contract.id)
    assert not [m for m in movements if m.movement_type == FIRST_REFERRER_BONUS_MOVEMENT_TYPE]
    # The ordinary commission is completely unaffected by the bonus being off.
    assert sum(m.amount_cents for m in movements) == 80_00


@pytest.mark.asyncio
async def test_reassigning_the_customer_later_does_not_move_an_already_opened_contracts_bonus(
    db, organization_id
):
    """`first_referrer_agent_id` is frozen at contract creation on purpose. An
    admin reassigning the customer changes who earns FUTURE business, not who
    is owed the bonus on a contract that was already opened."""
    actor_user_id = await _make_actor(db, organization_id)
    rank = Rank(
        organization_id=organization_id, code="S1", name="Seller 1", level=1,
        personal_token_cents=80_00, valid_from=NOW, rule_version="test",
    )
    db.add(rank)
    await db.flush()

    anna = await _make_agent(db, organization_id, name="Anna", rank_id=rank.id)
    carla = await _make_agent(db, organization_id, name="Carla", rank_id=rank.id)
    version = await _make_product(db, organization_id, bonus_enabled=True)
    customer, supply_point = await _make_customer_referred_by(db, organization_id, anna.id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=anna.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )

    await referral_service.reassign_customer_promoter(
        db, organization_id=organization_id, customer_id=customer.id, new_agent_id=carla.id,
        requested_by=actor_user_id, reason="test",
    )

    await _activate(db, organization_id, contract, actor_user_id)
    bonuses = [
        m for m in await _movements(db, contract.id)
        if m.movement_type == FIRST_REFERRER_BONUS_MOVEMENT_TYPE
    ]
    assert len(bonuses) == 1
    assert bonuses[0].agent_id == anna.id
