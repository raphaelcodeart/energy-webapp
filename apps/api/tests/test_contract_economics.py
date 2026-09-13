"""IVA, tipo cliente e cashback automatico sui contratti Lial Energy.

Three rules stated by the business, each of which used to have no server-side
implementation at all:

1. A contract for a private customer carries no VAT; a contract for a
   business/VAT-registered customer is priced net + VAT. Before this, VAT was
   a number two React components multiplied the displayed price by -- the
   backend never computed it, so the figure on screen and the figure that
   would have been charged were two independent implementations.
2. A product can be sold to privati, to aziende, or to both, and the rule is
   enforced server-side, not just by which cards the catalog renders.
3. Paying a Lial Energy contract credits LialCash automatically, with NO 5%
   surcharge -- explicitly unlike the partner-invoice redemption and the
   DROPSHIPPING order cashback, both of which stay exactly as they were.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.catalog import pricing
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from app.domains.users.models import User
from app.domains.wallets.models import Wallet, WalletTransaction

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_actor(db, organization_id) -> uuid.UUID:
    user = User(
        organization_id=organization_id, email=f"actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _make_product(
    db,
    organization_id,
    *,
    price_cents: int = 249_00,
    vat_percentage: float | None = 22.0,
    customer_type: str = "BOTH",
    contract_cashback_percentage: int = 0,
):
    product = Product(
        organization_id=organization_id, code=f"EC-{uuid.uuid4().hex[:6]}",
        energy_type="ELECTRICITY", customer_type=customer_type, category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Energia Circolare BAR",
        base_price_cents=price_cents, valid_from=NOW,
        tax_configuration={"vat_percentage": vat_percentage} if vat_percentage is not None else {},
        contract_cashback_percentage=contract_cashback_percentage,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return product, version


async def _make_customer(db, organization_id, *, kind: str, with_login: bool = False):
    user_id = None
    if with_login:
        user = User(
            organization_id=organization_id, email=f"cust-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("irrelevant"),
        )
        db.add(user)
        await db.flush()
        user_id = user.id

    customer = Customer(
        organization_id=organization_id, kind=kind, user_id=user_id,
        email=f"c-{uuid.uuid4().hex[:8]}@example.com",
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
    await db.commit()
    await db.refresh(customer)
    return customer, supply_point


async def _make_producer(db, organization_id):
    return await network_service.create_agent(
        db, organization_id=organization_id, first_name="Prod", last_name="Uttore",
        promoter_code=f"PR-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )


# --- 1. IVA ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_private_contract_carries_no_vat(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    _product, version = await _make_product(db, organization_id, price_cents=249_00, vat_percentage=22.0)
    customer, supply_point = await _make_customer(db, organization_id, kind="PRIVATE")
    producer = await _make_producer(db, organization_id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=producer.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )

    assert contract.net_amount_cents == 249_00
    assert contract.vat_rate == Decimal("0.00")
    assert contract.vat_amount_cents == 0
    # The private customer pays exactly the listed price -- not price + 22%.
    assert contract.gross_amount_cents == 249_00
    assert contract.customer_kind == "PRIVATE"


@pytest.mark.asyncio
async def test_business_contract_adds_vat_on_top(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    _product, version = await _make_product(db, organization_id, price_cents=249_00, vat_percentage=22.0)
    customer, supply_point = await _make_customer(db, organization_id, kind="COMPANY")
    producer = await _make_producer(db, organization_id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=producer.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )

    assert contract.net_amount_cents == 249_00
    assert contract.vat_rate == Decimal("22.00")
    # 24900 * 22 / 100 = 5478 exactly. Decimal, not float -- in binary
    # floating point this expression is 5477.999999999999.
    assert contract.vat_amount_cents == 5478
    assert contract.gross_amount_cents == 249_00 + 5478


@pytest.mark.asyncio
async def test_a_sole_proprietor_is_a_business_for_vat(db, organization_id):
    """SOLE_PROPRIETOR groups with PRIVATE elsewhere in the codebase (it has a
    person's name, not a company name) but has a P.IVA, so it is a business
    here. Two different questions, two different groupings -- this test exists
    to keep the two from being "helpfully" merged later."""
    actor_user_id = await _make_actor(db, organization_id)
    _product, version = await _make_product(db, organization_id, price_cents=100_00, vat_percentage=22.0)
    customer, supply_point = await _make_customer(db, organization_id, kind="SOLE_PROPRIETOR")
    producer = await _make_producer(db, organization_id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=producer.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    assert contract.vat_amount_cents == 22_00


@pytest.mark.asyncio
async def test_vat_snapshot_survives_a_later_product_price_change(db, organization_id):
    """The whole point of snapshotting: an admin editing the product must never
    restate a contract somebody already signed."""
    actor_user_id = await _make_actor(db, organization_id)
    _product, version = await _make_product(db, organization_id, price_cents=100_00, vat_percentage=22.0)
    customer, supply_point = await _make_customer(db, organization_id, kind="COMPANY")
    producer = await _make_producer(db, organization_id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=producer.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    original_gross = contract.gross_amount_cents

    version.base_price_cents = 999_00
    version.tax_configuration = {"vat_percentage": 4.0}
    await db.commit()
    await db.refresh(contract)

    assert contract.net_amount_cents == 100_00
    assert contract.gross_amount_cents == original_gross


# --- 2. Tipo cliente ammesso -------------------------------------------------


def test_product_audience_matching_covers_the_legacy_vocabulary():
    """`products.customer_type` used to hold PMI / ENERGY_INTENSIVE /
    SOLE_PROPRIETOR, a vocabulary that never lined up with `customers.kind`.
    Old values must keep parsing rather than blowing up or, worse, silently
    excluding everyone."""
    assert pricing.normalize_product_customer_type("PMI") == "BUSINESS"
    assert pricing.normalize_product_customer_type("ENERGY_INTENSIVE") == "BUSINESS"
    assert pricing.normalize_product_customer_type("SOLE_PROPRIETOR") == "BUSINESS"
    assert pricing.normalize_product_customer_type(None) == "BOTH"
    # An unrecognized value fails OPEN, showing the product to everyone --
    # a display filter quietly hiding a product from the whole catalog is far
    # more damaging than showing one product too many.
    assert pricing.normalize_product_customer_type("SOMETHING_NEW") == "BOTH"

    assert pricing.product_allows_customer_kind("PRIVATE", "PRIVATE") is True
    assert pricing.product_allows_customer_kind("PRIVATE", "COMPANY") is False
    assert pricing.product_allows_customer_kind("BUSINESS", "COMPANY") is True
    assert pricing.product_allows_customer_kind("BUSINESS", "PRIVATE") is False
    assert pricing.product_allows_customer_kind("BOTH", "PRIVATE") is True
    assert pricing.product_allows_customer_kind("BOTH", "COMPANY") is True


@pytest.mark.asyncio
async def test_a_promoter_cannot_activate_a_business_only_contract_for_a_private(db, organization_id):
    """Server-side enforcement, not just a filtered catalog: this goes through
    the CRM path a promoter actually uses."""
    from app.domains.customers.schemas import SupplyPointCreate
    from app.domains.referral import service as referral_service

    promoter_user = User(
        organization_id=organization_id, email=f"promo-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(promoter_user)
    await db.flush()
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Promo", last_name="Ter",
        promoter_code=f"PM-{uuid.uuid4().hex[:8]}", parent_agent_id=None, user_id=promoter_user.id,
    )
    code = await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=agent.id
    )

    customer, _sp = await _make_customer(db, organization_id, kind="PRIVATE")
    await referral_service.attribute_customer(
        db, organization_id=organization_id, customer_id=customer.id, promoter_code_id=code.id,
        referral_session_id=None,
    )

    _product, version = await _make_product(db, organization_id, customer_type="BUSINESS")

    with pytest.raises(contract_service.SelfServiceContractError, match="tipologia"):
        await contract_service.create_contract_for_recruited_customer(
            db, organization_id=organization_id, promoter_user_id=promoter_user.id,
            customer_id=customer.id, product_version_id=version.id,
            supply_point_payload=SupplyPointCreate(
                energy_type="ELECTRICITY", pod_code="IT001E12345678",
                street="Via Test 1", city="Roma", province="RM", postal_code="00100",
            ),
            email="cliente@example.com",
        )


# --- 3. Cashback automatico, senza il +5% ------------------------------------


@pytest.mark.asyncio
async def test_paying_a_contract_credits_lialcash_with_no_surcharge(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    _product, version = await _make_product(
        db, organization_id, price_cents=249_00, vat_percentage=22.0, contract_cashback_percentage=100
    )
    customer, supply_point = await _make_customer(db, organization_id, kind="PRIVATE", with_login=True)
    producer = await _make_producer(db, organization_id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=producer.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAID"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )

    wallet = (
        await db.execute(select(Wallet).where(Wallet.user_id == customer.user_id))
    ).scalar_one()
    # 100% of the GROSS. A private customer pays no VAT, so gross == net here
    # and there is deliberately nothing extra the customer had to pay to earn
    # this -- no 5% surcharge, no opt-in, unlike a DROPSHIPPING order.
    assert wallet.balance_cents == 249_00

    credits = (
        await db.execute(
            select(WalletTransaction).where(WalletTransaction.reference_contract_id == contract.id)
        )
    ).scalars().all()
    assert len(credits) == 1
    assert credits[0].source == contract_service.CONTRACT_CASHBACK_SOURCE
    assert contract.cashback_credited_at is not None


@pytest.mark.asyncio
async def test_contract_cashback_is_credited_exactly_once(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    _product, version = await _make_product(
        db, organization_id, price_cents=100_00, vat_percentage=None, contract_cashback_percentage=50
    )
    customer, supply_point = await _make_customer(db, organization_id, kind="PRIVATE", with_login=True)
    producer = await _make_producer(db, organization_id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=producer.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAID"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )

    # Simulates a replayed webhook / a second confirmation arriving: the
    # readable guard is cleared so only the ledger's own idempotency key is
    # left to stop it.
    contract.cashback_credited_at = None
    await db.commit()
    await contract_service.credit_contract_cashback(
        db, organization_id=organization_id, contract=contract, actor_user_id=actor_user_id
    )

    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == customer.user_id))).scalar_one()
    assert wallet.balance_cents == 50_00


@pytest.mark.asyncio
async def test_a_product_without_contract_cashback_credits_nothing(db, organization_id):
    """Every product that exists today has contract_cashback_percentage = 0,
    so paying a contract must change no wallet until an admin opts in."""
    actor_user_id = await _make_actor(db, organization_id)
    _product, version = await _make_product(db, organization_id, contract_cashback_percentage=0)
    customer, supply_point = await _make_customer(db, organization_id, kind="PRIVATE", with_login=True)
    producer = await _make_producer(db, organization_id)

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=version.id, producer_agent_id=producer.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAID"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )

    credits = (
        await db.execute(
            select(WalletTransaction).where(WalletTransaction.reference_contract_id == contract.id)
        )
    ).scalars().all()
    assert credits == []
    assert contract.cashback_credited_at is None
