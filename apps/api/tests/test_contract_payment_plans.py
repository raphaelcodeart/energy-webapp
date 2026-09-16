"""Pagamento del contratto: soluzione unica, 3 rate, 12 rate.

Contracts only -- the Shop's own checkout is a separate, working flow and is
not touched by any of this.

Two things these pin down. The arithmetic, because an instalment plan that is
a few euro off is worse than no instalment plan; and the webhook, because
Stripe promises at-least-once delivery and an instalment plan fires
`invoice.paid` every month for the same subscription -- so "the same event
again" must be distinguishable from "the next instalment".
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import payment_plans
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import Contract
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from app.domains.payments import service as payments_service
from app.domains.payments.models import StripeWebhookEvent
from app.domains.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WEBHOOK_SECRET = "whsec_test_secret"


# --- L'aritmetica delle rate -------------------------------------------------


def test_a_price_that_divides_evenly_has_no_rounding_at_all():
    """The case that matters most: 249,00 is the contract the business keeps
    describing, and it divides exactly by both 3 and 12."""
    for key, expected_instalment in (
        (payment_plans.PLAN_FULL, 249_00),
        (payment_plans.PLAN_INSTALMENTS_3, 83_00),
        (payment_plans.PLAN_MONTHLY_12, 20_75),
    ):
        plan = payment_plans.plan_by_key(key)
        b = payment_plans.breakdown_for(plan, 249_00)
        assert b.instalment_cents == expected_instalment
        assert b.total_cents == 249_00
        assert b.rounding_difference_cents == 0


def test_a_price_that_does_not_divide_reports_the_difference_instead_of_hiding_it():
    plan = payment_plans.plan_by_key(payment_plans.PLAN_MONTHLY_12)
    b = payment_plans.breakdown_for(plan, 100_00)
    assert b.instalment_cents == 8_33
    assert b.total_cents == 99_96
    assert b.contract_total_cents == 100_00
    # Never silently absorbed: the customer is shown this figure.
    assert b.rounding_difference_cents == -4


def test_the_rounding_difference_can_never_be_large():
    """Whatever the price, splitting it must never move the total by more
    than a few cents -- that is what makes showing the figure honest rather
    than alarming."""
    for total in range(100, 100_000, 137):
        for plan in payment_plans.PAYMENT_PLANS:
            b = payment_plans.breakdown_for(plan, total)
            assert abs(b.rounding_difference_cents) <= plan.instalments // 2


def test_an_amount_too_small_to_split_drops_that_option():
    """Stripe refuses a zero-amount recurring price, and "12 rate da 0,00"
    would be nonsense before it was an error."""
    keys = {b.plan.key for b in payment_plans.available_breakdowns(5)}
    assert payment_plans.PLAN_FULL in keys
    assert payment_plans.PLAN_MONTHLY_12 not in keys


# --- Il webhook ---------------------------------------------------------------


async def _make_payable_contract(db, organization_id, *, gross_cents: int = 249_00) -> Contract:
    user = User(
        organization_id=organization_id, email=f"c-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.flush()
    customer = Customer(
        organization_id=organization_id, kind="PRIVATE", user_id=user.id,
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
    product = Product(
        organization_id=organization_id, code=f"P-{uuid.uuid4().hex[:6]}",
        energy_type="ELECTRICITY", customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Energia Circolare",
        base_price_cents=gross_cents, valid_from=NOW,
    )
    db.add(version)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Prod", last_name="Uttore",
        promoter_code=f"PR-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    await db.commit()

    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id,
        supply_point_id=supply_point.id, product_version_id=version.id,
        producer_agent_id=agent.id, actor_user_id=user.id, correlation_id=str(uuid.uuid4()),
    )
    for step in ["SUBMITTED", "UNDER_REVIEW", "APPROVED"]:
        contract = await contract_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=step,
            actor_user_id=user.id, reason="test", notes=None, correlation_id=str(uuid.uuid4()),
        )
    # APPROVED auto-cascades to PAYMENT_PENDING -- the point a customer can pay.
    assert contract.status == "PAYMENT_PENDING"
    # Since Session 50 an approved contract activates on payment only once an
    # administrator has accepted the commission preview.
    from app.domains.commissions.services.preview import build_commission_preview

    preview = await build_commission_preview(db, organization_id=organization_id, contract=contract)
    await contract_service.accept_commission_plan(
        db, organization_id=organization_id, contract=contract, checksum=preview["checksum"],
        actor_user_id=user.id,
    )
    return contract


def _signed(payload: dict) -> tuple[bytes, str]:
    """A genuinely signed webhook body, so the test goes through
    construct_event() rather than around it -- the shortcut that let a real
    bug (StripeObject has no .get()) reach production twice."""
    body = json.dumps(payload).encode()
    timestamp = int(time.time())
    signature = hmac.new(
        WEBHOOK_SECRET.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return body, f"t={timestamp},v1={signature}"


async def _configure_stripe(db, organization_id) -> None:
    """Writes the keys straight onto the organization rather than through
    update_payment_settings() -- that takes a Pydantic payload, and a test
    only needs the stored shape the readers actually look at."""
    from app.domains.organizations.models import Organization

    org = await db.get(Organization, organization_id)
    org.settings = {
        **(org.settings or {}),
        "stripe_secret_key": "sk_test_fake",
        "stripe_publishable_key": "pk_test_fake",
        "stripe_webhook_secret": WEBHOOK_SECRET,
    }
    await db.commit()


@pytest.mark.asyncio
async def test_a_paid_checkout_activates_the_contract(db, organization_id):
    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id)
    await contract_service.attach_stripe_checkout_session(
        db, contract=contract, session_id="cs_test_1", plan_key=payment_plans.PLAN_FULL
    )

    body, sig = _signed({
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_1",
            "metadata": {"kind": "contract", "contract_id": str(contract.id)},
        }},
    })
    await payments_service.handle_webhook_event(
        db, organization_id=organization_id, payload=body, sig_header=sig
    )

    await db.refresh(contract)
    # PAID auto-cascades through ACTIVATION_PENDING into ACTIVE -- the same
    # hop that triggers commissions for every other contract.
    assert contract.status == "ACTIVE"
    assert contract.paid_at is not None


@pytest.mark.asyncio
async def test_the_same_event_delivered_twice_changes_nothing(db, organization_id):
    """Stripe promises at-least-once, not exactly-once."""
    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id)
    await contract_service.attach_stripe_checkout_session(
        db, contract=contract, session_id="cs_test_2", plan_key=payment_plans.PLAN_FULL
    )
    payload = {
        "id": "evt_test_2",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_2", "metadata": {"kind": "contract"}}},
    }
    for _ in range(3):
        body, sig = _signed(payload)
        await payments_service.handle_webhook_event(
            db, organization_id=organization_id, payload=body, sig_header=sig
        )

    rows = list((await db.execute(
        select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_test_2")
    )).scalars())
    assert len(rows) == 1, "l'evento deve essere registrato una sola volta"
    await db.refresh(contract)
    assert contract.status == "ACTIVE"


@pytest.mark.asyncio
async def test_the_success_url_is_not_what_marks_a_contract_paid(db, organization_id):
    """A customer can open the success URL by hand. Only a signed webhook
    moves a contract to PAID."""
    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id)
    await contract_service.attach_stripe_checkout_session(
        db, contract=contract, session_id="cs_test_3", plan_key=payment_plans.PLAN_MONTHLY_12
    )
    await db.refresh(contract)
    assert contract.status == "PAYMENT_PENDING"
    assert contract.paid_at is None


@pytest.mark.asyncio
async def test_an_unsigned_or_tampered_payload_is_refused(db, organization_id):
    await _configure_stripe(db, organization_id)
    with pytest.raises(payments_service.WebhookVerificationError):
        await payments_service.handle_webhook_event(
            db, organization_id=organization_id,
            payload=b'{"id":"evt_x","type":"checkout.session.completed"}',
            sig_header="t=1,v1=deadbeef",
        )


@pytest.mark.asyncio
async def test_a_failed_instalment_warns_everybody_without_suspending_the_contract(db, organization_id):
    """One declined monthly charge is not grounds for automatically cutting
    off somebody's energy contract -- but somebody has to find out."""
    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id)
    await contract_service.attach_stripe_checkout_session(
        db, contract=contract, session_id="cs_test_4", plan_key=payment_plans.PLAN_MONTHLY_12
    )
    body, sig = _signed({
        "id": "evt_test_4",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_4", "metadata": {"kind": "contract"}, "subscription": "sub_test_4"}},
    })
    await payments_service.handle_webhook_event(
        db, organization_id=organization_id, payload=body, sig_header=sig
    )
    await db.refresh(contract)
    assert contract.status == "ACTIVE"

    outcome = await contract_service.record_subscription_invoice(
        db, organization_id=organization_id, subscription_id="sub_test_4",
        paid=False, amount_cents=20_75,
    )
    assert "NON riscossa" in outcome
    await db.refresh(contract)
    assert contract.status == "ACTIVE", "un addebito fallito non sospende il contratto da solo"


@pytest.mark.asyncio
async def test_a_successful_instalment_is_recorded(db, organization_id):
    await _configure_stripe(db, organization_id)
    contract = await _make_payable_contract(db, organization_id)
    contract.stripe_subscription_id = "sub_test_5"
    await db.commit()

    outcome = await contract_service.record_subscription_invoice(
        db, organization_id=organization_id, subscription_id="sub_test_5",
        paid=True, amount_cents=20_75,
    )
    assert "incassata" in outcome


@pytest.mark.asyncio
async def test_an_event_for_an_unknown_subscription_is_harmless(db, organization_id):
    outcome = await contract_service.record_subscription_invoice(
        db, organization_id=organization_id, subscription_id="sub_nonexistent",
        paid=True, amount_cents=100,
    )
    assert "nessun contratto" in outcome
