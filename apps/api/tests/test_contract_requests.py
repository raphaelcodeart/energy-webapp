"""La pratica di attivazione (Session 52): N punti, N contratti indipendenti,
documenti comuni una volta, un pagamento solo.

What these pin down, in the order a pratica lives it:

- every point is its own contract, with its own package and frozen price,
  and nothing past DRAFT may lack a package;
- a POD/PDR is validated and cannot be contracted twice at once;
- documents uploaded on the pratica fill every contract's slots;
- one Checkout pays every contract, each exactly as if paid alone;
- one monthly invoice of the pratica's subscription reaches each contract
  through its own line, once;
- a contract created outside a pratica still belongs to one.
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime

import pytest
import stripe
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domains.auth import service as auth_service
from app.domains.auth.schemas import RegisterRequest
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import payment_plans
from app.domains.contracts import requests as requests_service
from app.domains.contracts import service as contracts_service
from app.domains.contracts.models import Contract, ContractInstalment, ContractRequest, ContractRequestCheckout
from app.domains.customers.models import Customer
from app.domains.documents import service as documents_service
from app.domains.network import service as network_service
from app.domains.payments import service as payments_service
from app.domains.rbac.models import Role
from app.domains.referral import service as referral_service
from app.domains.wallets.models import WalletTransaction

NOW = datetime(2026, 1, 1, tzinfo=UTC)
WEBHOOK_SECRET = "whsec_test_requests"


# --- Preparazione --------------------------------------------------------------


async def _customer(db, organization_id, *, email: str | None = None):
    db.add(Role(organization_id=organization_id, code="CUSTOMER", name="Customer"))
    await db.commit()
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Pro", last_name="Moter",
        promoter_code=f"REF-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    code = await referral_service.get_or_create_promoter_code(db, organization_id=organization_id, agent_id=agent.id)
    user = await auth_service.register_with_referral(
        db, organization_id=organization_id,
        payload=RegisterRequest(
            organization_id=str(organization_id), referral_code=code.code,
            email=email or f"pratica-{uuid.uuid4().hex[:8]}@example.demo",
            password="correct-horse-battery-staple", kind="PRIVATE", first_name="Mario", last_name="Rossi",
            accept_privacy=True,
        ),
    )
    customer = (await db.execute(select(Customer).where(Customer.user_id == user.id))).scalar_one()
    return user, customer


async def _package(db, organization_id, *, name: str, energy_type: str, price_cents: int, cashback: int = 0):
    product = Product(
        organization_id=organization_id, code=f"P-{uuid.uuid4().hex[:6]}", energy_type=energy_type,
        customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name=name, base_price_cents=price_cents,
        billing_period="ANNUAL", contract_duration_months=12, valid_from=NOW,
        contract_cashback_percentage=cashback,
    )
    db.add(version)
    await db.commit()
    return version


ADDRESS = requests_service.AddressData(street="Via Roma 1", city="Roma", province="RM", postal_code="00100")


async def _open(db, organization_id, user, customer, *, points: int = 1, product_version_id=None) -> ContractRequest:
    return await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=requests_service.HolderData(
            first_name="Mario", last_name="Rossi", email="mario@example.demo", pec=None,
            iban="IT60X0542811101000000123456", address=ADDRESS,
        ),
        actor_user_id=user.id, actor_role="CUSTOMER", promoter_agent_id=None,
        points_count=points, product_version_id=product_version_id,
    )


async def _pratica_with_three_points(db, organization_id):
    user, customer = await _customer(db, organization_id)
    luce_a = await _package(db, organization_id, name="Luce A", energy_type="ELECTRICITY", price_cents=120_00, cashback=100)
    luce_b = await _package(db, organization_id, name="Luce B", energy_type="ELECTRICITY", price_cents=240_00)
    gas = await _package(db, organization_id, name="Gas", energy_type="GAS", price_cents=60_00)
    request = await _open(db, organization_id, user, customer, points=3)
    c1, c2, c3 = await requests_service.list_points(db, request=request)
    for contract, version in ((c1, luce_a), (c2, luce_b), (c3, gas)):
        await requests_service.set_point_product(
            db, request=request, contract=contract, product_version_id=version.id, actor_user_id=user.id
        )
    return user, customer, request, [c1, c2, c3]


# --- POD e contratti -----------------------------------------------------------


@pytest.mark.asyncio
async def test_quanti_pod_creates_that_many_contracts_each_with_its_own_package_and_price(db, organization_id):
    user, customer, request, (c1, c2, c3) = await _pratica_with_three_points(db, organization_id)

    for contract in (c1, c2, c3):
        await db.refresh(contract)
        assert contract.contract_request_id == request.id
        assert contract.customer_id == customer.id
        assert contract.status == "DRAFT"
        assert contract.holder_last_name == "Rossi"
        assert contract.iban == "IT60X0542811101000000123456"
    assert (c1.gross_amount_cents, c2.gross_amount_cents, c3.gross_amount_cents) == (120_00, 240_00, 60_00)

    rows = await contracts_service.to_read_dicts(db, [c1, c3])
    # No POD code asked: the package decides luce or gas, the pratica the address.
    assert [r["energy_type"] for r in rows] == ["ELECTRICITY", "GAS"]
    assert rows[0]["pod_code"] is None
    assert rows[0]["supply_point_label"] == "Energia elettrica - Via Roma 1, Roma"

    request = await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    assert request.status == "SUBMITTED"
    for contract in (c1, c2, c3):
        await db.refresh(contract)
        assert contract.status == "DOCUMENTS_PENDING"


@pytest.mark.asyncio
async def test_changing_quanti_pod_adds_or_drops_empty_points_first(db, organization_id):
    user, customer = await _customer(db, organization_id)
    luce = await _package(db, organization_id, name="Luce", energy_type="ELECTRICITY", price_cents=100_00)
    request = await _open(db, organization_id, user, customer, points=2)
    first, second = await requests_service.list_points(db, request=request)
    await requests_service.set_point_product(
        db, request=request, contract=first, product_version_id=luce.id, actor_user_id=user.id
    )

    points = await requests_service.set_points_count(db, request=request, count=4, actor_user_id=user.id)
    assert len(points) == 4
    points = await requests_service.set_points_count(db, request=request, count=1, actor_user_id=user.id)
    assert [p.id for p in points] == [first.id], "si tolgono prima i POD senza contratto scelto"
    with pytest.raises(requests_service.ContractRequestError, match="almeno un POD"):
        await requests_service.set_points_count(db, request=request, count=0, actor_user_id=user.id)


@pytest.mark.asyncio
async def test_starting_from_a_package_chooses_it_for_every_pod(db, organization_id):
    user, customer = await _customer(db, organization_id)
    luce = await _package(db, organization_id, name="Luce", energy_type="ELECTRICITY", price_cents=100_00)
    request = await _open(db, organization_id, user, customer, points=3, product_version_id=luce.id)
    assert {p.product_version_id for p in await requests_service.list_points(db, request=request)} == {luce.id}


@pytest.mark.asyncio
async def test_a_pratica_cannot_be_sent_while_a_pod_has_no_contract(db, organization_id):
    user, customer = await _customer(db, organization_id)
    request = await _open(db, organization_id, user, customer)
    with pytest.raises(requests_service.ContractRequestError, match="contratto da attivare"):
        await requests_service.submit_request(db, request=request, actor_user_id=user.id)


@pytest.mark.asyncio
async def test_the_database_refuses_a_contract_past_draft_without_a_package(db, organization_id):
    user, customer = await _customer(db, organization_id)
    request = await _open(db, organization_id, user, customer)
    [contract] = await requests_service.list_points(db, request=request)
    contract.status = "SUBMITTED"
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


@pytest.mark.asyncio
async def test_a_pod_can_move_to_its_own_address_and_keeps_it_when_the_pratica_address_changes(db, organization_id):
    from app.domains.customers.models import Address, SupplyPoint

    user, customer, request, (c1, c2, _c3) = await _pratica_with_three_points(db, organization_id)
    await requests_service.update_point_address(
        db, request=request, contract=c2,
        address_data=requests_service.AddressData(street="Via Po 4", city="Torino", province="TO", postal_code="10100"),
        actor_user_id=user.id,
    )
    await requests_service.update_holder(
        db, request=request, actor_user_id=user.id,
        holder=requests_service.HolderData(
            first_name="Mario", last_name="Rossi", email="mario@example.demo", pec=None, iban=None,
            address=requests_service.AddressData(street="Via Nuova 9", city="Roma", province="RM", postal_code="00100"),
        ),
    )

    async def street(contract):
        sp = await db.get(SupplyPoint, contract.supply_point_id)
        return (await db.get(Address, sp.supply_address_id)).street

    assert await street(c1) == "Via Nuova 9"
    assert await street(c2) == "Via Po 4"


@pytest.mark.asyncio
async def test_a_removed_point_is_cancelled_and_no_longer_part_of_the_pratica(db, organization_id):
    user, customer, request, (c1, c2, c3) = await _pratica_with_three_points(db, organization_id)
    await requests_service.remove_point(db, request=request, contract=c2, actor_user_id=user.id)
    await db.refresh(c2)
    assert c2.status == "CANCELLED"
    assert [c.id for c in await requests_service.list_points(db, request=request)] == [c1.id, c3.id]
    [summary] = await requests_service.summaries(db, [request])
    assert summary["points_total"] == 2
    assert summary["total_gross_cents"] == 180_00


@pytest.mark.asyncio
async def test_a_sent_pratica_cannot_be_changed(db, organization_id):
    user, customer, request, (c1, _c2, _c3) = await _pratica_with_three_points(db, organization_id)
    await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    with pytest.raises(requests_service.ContractRequestError, match="già stata inviata"):
        await requests_service.add_point(db, request=request, actor_user_id=user.id)
    with pytest.raises(requests_service.ContractRequestError, match="già stata inviata"):
        await requests_service.remove_point(db, request=request, contract=c1, actor_user_id=user.id)


# --- Documenti -----------------------------------------------------------------


async def _upload(db, organization_id, user, *, document_type: str, contract_id=None, contract_request_id=None):
    return await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract_id, contract_request_id=contract_request_id,
        document_type=document_type, file_bytes=b"%PDF-1.4\nfake", content_type="application/pdf",
        original_filename=f"{document_type}.pdf", actor_user_id=user.id, actor_role="CUSTOMER",
    )


@pytest.mark.asyncio
async def test_documents_uploaded_once_on_the_pratica_fill_every_contract(db, organization_id):
    user, customer, request, contracts = await _pratica_with_three_points(db, organization_id)
    for document_type in ("IDENTITY", "FISCAL_CODE", "UTILITY_BILL"):
        await _upload(db, organization_id, user, document_type=document_type, contract_request_id=request.id)

    await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    for contract in contracts:
        await db.refresh(contract)
        assert contract.status == "UNDER_REVIEW", "i documenti della pratica valgono per ogni punto"
        slots = await documents_service.get_contract_documents_status(
            db, organization_id=organization_id, contract=contract, customer_kind="PRIVATE"
        )
        assert all(slot["document"] is not None for slot in slots if slot["required"])


@pytest.mark.asyncio
async def test_a_point_own_bill_wins_over_the_shared_one(db, organization_id):
    user, customer, request, (c1, c2, _c3) = await _pratica_with_three_points(db, organization_id)
    shared = await _upload(db, organization_id, user, document_type="UTILITY_BILL", contract_request_id=request.id)
    own = await _upload(db, organization_id, user, document_type="UTILITY_BILL", contract_id=c1.id)

    def bill(slots):
        return next(s["document"] for s in slots if s["document_type"] == "UTILITY_BILL")

    assert bill(await documents_service.get_contract_documents_status(
        db, organization_id=organization_id, contract=c1, customer_kind="PRIVATE"
    )).id == own.id
    assert bill(await documents_service.get_contract_documents_status(
        db, organization_id=organization_id, contract=c2, customer_kind="PRIVATE"
    )).id == shared.id


@pytest.mark.asyncio
async def test_a_document_belongs_to_a_contract_or_a_pratica_never_both(db, organization_id):
    user, customer, request, (c1, _c2, _c3) = await _pratica_with_three_points(db, organization_id)
    with pytest.raises(documents_service.DocumentValidationError):
        await _upload(db, organization_id, user, document_type="IDENTITY", contract_id=c1.id, contract_request_id=request.id)


# --- Pagamento -----------------------------------------------------------------


def test_the_monthly_figure_is_each_contract_split_on_its_own_then_added_up():
    contracts = [Contract(gross_amount_cents=cents, status="UNDER_REVIEW") for cents in (100_00, 249_00)]
    by_key = {o.plan.key: o for o in requests_service.plan_options(contracts)}
    # 100,00 / 12 rounds to 8,33 and 249,00 / 12 is exactly 20,75.
    assert by_key[payment_plans.PLAN_MONTHLY_12].instalment_cents == 8_33 + 20_75
    assert by_key[payment_plans.PLAN_MONTHLY_12].rounding_difference_cents == -4
    assert by_key[payment_plans.PLAN_FULL].total_cents == 349_00


def test_only_the_single_payment_is_discounted():
    contracts = [Contract(gross_amount_cents=cents, status="UNDER_REVIEW") for cents in (180_00, 249_00)]
    by_key = {o.plan.key: o for o in requests_service.plan_options(contracts, discount_percentage=32)}
    full = by_key[payment_plans.PLAN_FULL]
    assert full.list_total_cents == 429_00
    assert full.discount_percentage == 32
    assert full.total_cents == 122_40 + 169_32  # 180 - 57,60 ; 249 - 79,68
    assert full.discount_cents == 57_60 + 79_68
    for key in (payment_plans.PLAN_INSTALMENTS_3, payment_plans.PLAN_MONTHLY_12):
        assert by_key[key].discount_cents == 0 and by_key[key].discount_percentage == 0
        assert by_key[key].total_cents == 429_00 + by_key[key].rounding_difference_cents
    # Switched off in Impostazioni (0): nothing changes.
    plain = {o.plan.key: o for o in requests_service.plan_options(contracts, discount_percentage=0)}
    assert plain[payment_plans.PLAN_FULL].total_cents == 429_00 and plain[payment_plans.PLAN_FULL].discount_cents == 0


def test_too_many_contracts_for_one_subscription_leaves_only_the_single_payment():
    contracts = [
        Contract(gross_amount_cents=120_00, status="UNDER_REVIEW")
        for _ in range(requests_service.MAX_SUBSCRIPTION_LINES + 1)
    ]
    by_key = {o.plan.key: o for o in requests_service.plan_options(contracts)}
    assert by_key[payment_plans.PLAN_FULL].available
    assert not by_key[payment_plans.PLAN_MONTHLY_12].available
    assert "al massimo" in by_key[payment_plans.PLAN_MONTHLY_12].unavailable_reason


async def _configure_stripe(db, organization_id) -> None:
    from app.domains.organizations.models import Organization

    org = await db.get(Organization, organization_id)
    org.settings = {
        **(org.settings or {}),
        "stripe_secret_key": "sk_test_fake",
        "stripe_publishable_key": "pk_test_fake",
        "stripe_webhook_secret": WEBHOOK_SECRET,
    }
    await db.commit()


def _signed(payload: dict) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    timestamp = int(time.time())
    signature = hmac.new(WEBHOOK_SECRET.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return body, f"t={timestamp},v1={signature}"


async def _webhook(db, organization_id, payload: dict) -> None:
    body, sig = _signed(payload)
    await payments_service.handle_webhook_event(db, organization_id=organization_id, payload=body, sig_header=sig)


class _FakeSession:
    def __init__(self, session_id: str):
        self.id = session_id
        self.url = f"https://checkout.stripe.test/{session_id}"


def _fake_stripe(monkeypatch, *, created: list, item_ids: dict[str, str] | None = None, lines: list | None = None):
    counter = iter(range(1, 100))

    def create_session(**params):
        created.append(params)
        return _FakeSession(f"cs_pratica_{next(counter)}")

    def retrieve_subscription(subscription_id, **_):
        return stripe.StripeObject.construct_from(
            {
                "id": subscription_id,
                "billing_cycle_anchor": int(time.time()),
                "items": {
                    "data": [
                        {"id": item_id, "price": {"product": {"id": f"prod_{item_id}", "metadata": {"contract_id": cid}}}}
                        for cid, item_id in (item_ids or {}).items()
                    ]
                },
            },
            "sk_test_fake",
        )

    class _Lines:
        def __init__(self, data):
            self._data = data

        def auto_paging_iter(self):
            return iter(self._data)

    def list_lines(invoice_id, **_):
        return _Lines([stripe.StripeObject.construct_from(line, "sk_test_fake") for line in (lines or [])])

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(create_session))
    monkeypatch.setattr(stripe.checkout.Session, "expire", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(stripe.Subscription, "retrieve", staticmethod(retrieve_subscription))
    monkeypatch.setattr(stripe.Subscription, "modify", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(stripe.Invoice, "list_lines", staticmethod(list_lines))


async def _sent_pratica(db, organization_id):
    user, customer, request, contracts = await _pratica_with_three_points(db, organization_id)
    await requests_service.submit_request(db, request=request, actor_user_id=user.id)
    for contract in contracts:
        await db.refresh(contract)
    return user, customer, request, contracts


@pytest.mark.asyncio
async def test_one_checkout_pays_every_contract_of_the_pratica_each_as_if_alone(db, organization_id, monkeypatch):
    await _configure_stripe(db, organization_id)
    user, customer, request, contracts = await _sent_pratica(db, organization_id)
    created: list = []
    _fake_stripe(monkeypatch, created=created)

    await payments_service.create_checkout_session_for_request(
        db, organization_id=organization_id, request=request, plan_key=payment_plans.PLAN_FULL,
        actor_user_id=user.id, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    [params] = created
    assert params["mode"] == "payment"
    # Paid in one go: 32% off by default (Session 64). 120 -> 81,60 ...
    assert [li["price_data"]["unit_amount"] for li in params["line_items"]] == [81_60, 163_20, 40_80]
    assert "sconto 32%" in params["line_items"][0]["price_data"]["product_data"]["description"]
    assert "sconto del 32%" in params["custom_text"]["submit"]["message"]
    assert {li["price_data"]["product_data"]["metadata"]["contract_id"] for li in params["line_items"]} == {
        str(c.id) for c in contracts
    }

    await _webhook(db, organization_id, {
        "id": "evt_pratica_full",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_pratica_1", "metadata": {"kind": "contract_request", "contract_request_id": str(request.id)},
        }},
    })
    for contract in contracts:
        await db.refresh(contract)
        assert contract.paid_at is not None
        assert contract.payment_plan == payment_plans.PLAN_FULL
        # Paid before approval: still waiting for its own documents review.
        assert contract.status == "DOCUMENTS_PENDING"
        rows = list((await db.execute(
            select(ContractInstalment).where(ContractInstalment.contract_id == contract.id)
        )).scalars())
        # The discount is frozen on the contract: the list price stays the contract's value.
        assert contract.payment_discount_cents == contract.gross_amount_cents * 32 // 100
        assert [(r.number, r.status, r.amount_cents) for r in rows] == [
            (1, "PAID", contract.gross_amount_cents - contract.payment_discount_cents)
        ]

    # Only Luce A earns cashback (100%), on what was paid.
    credits = list((await db.execute(
        select(WalletTransaction).where(WalletTransaction.reference_contract_id.in_([c.id for c in contracts]))
    )).scalars())
    assert [(t.reference_contract_id, t.amount_cents) for t in credits] == [(contracts[0].id, 81_60)]


@pytest.mark.asyncio
async def test_a_monthly_invoice_reaches_each_contract_through_its_own_line_once(db, organization_id, monkeypatch):
    await _configure_stripe(db, organization_id)
    user, customer, request, contracts = await _sent_pratica(db, organization_id)
    items = {str(c.id): f"si_{i}" for i, c in enumerate(contracts)}
    created: list = []
    # 120 / 12 = 10,00 ; 240 / 12 = 20,00 ; 60 / 12 = 5,00
    lines = [
        {"id": f"il_{i}", "amount": amount, "parent": {"subscription_item_details": {"subscription_item": f"si_{i}"}}}
        for i, amount in enumerate((10_00, 20_00, 5_00))
    ]
    _fake_stripe(monkeypatch, created=created, item_ids=items, lines=lines)

    await payments_service.create_checkout_session_for_request(
        db, organization_id=organization_id, request=request, plan_key=payment_plans.PLAN_MONTHLY_12,
        actor_user_id=user.id, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    assert created[0]["mode"] == "subscription"
    assert [li["price_data"]["unit_amount"] for li in created[0]["line_items"]] == [10_00, 20_00, 5_00]
    # Stripe only shows "35,00 € al mese": the plan is spelled out next to it.
    assert "12 rate mensili da 35,00 €, per un totale di 420,00 €" in created[0]["custom_text"]["submit"]["message"]
    assert "dopo la 12ª rata" in created[0]["custom_text"]["submit"]["message"]
    assert created[0]["line_items"][1]["price_data"]["product_data"]["description"] == (
        "12 rate mensili da 20,00 € · totale 240,00 €"
    )

    await _webhook(db, organization_id, {
        "id": "evt_pratica_sub",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_pratica_1", "subscription": "sub_pratica", "customer": "cus_x", "invoice": "in_first",
            "metadata": {"kind": "contract_request"},
        }},
    })
    for contract in contracts:
        await db.refresh(contract)
        assert contract.stripe_subscription_id == "sub_pratica"
        assert contract.stripe_subscription_item_id == items[str(contract.id)]

    invoice = {
        "id": "in_month_2", "billing_reason": "subscription_cycle", "amount_paid": 35_00,
        "parent": {"subscription_details": {"subscription": "sub_pratica"}},
    }
    # Delivered twice under two event ids (a manual resend from the dashboard).
    for event_id in ("evt_month_2", "evt_month_2_resend"):
        await _webhook(db, organization_id, {"id": event_id, "type": "invoice.paid", "data": {"object": invoice}})

    for contract in contracts:
        rows = list((await db.execute(
            select(ContractInstalment)
            .where(ContractInstalment.contract_id == contract.id)
            .order_by(ContractInstalment.number)
        )).scalars())
        assert len(rows) == 12
        assert [r.status for r in rows[:3]] == ["PAID", "PAID", "SCHEDULED"]
        assert rows[0].stripe_invoice_id == "in_first"
        assert rows[1].stripe_invoice_id == "in_month_2"

    # Luce A: 100% cashback on each 10,00 instalment -- first month and second, never twice.
    credits = list((await db.execute(
        select(WalletTransaction.amount_cents).where(WalletTransaction.reference_contract_id == contracts[0].id)
    )).scalars())
    assert sorted(credits) == [10_00, 10_00]


@pytest.mark.asyncio
async def test_a_contract_paid_twice_is_reported_not_paid_again(db, organization_id, monkeypatch):
    await _configure_stripe(db, organization_id)
    user, customer, request, contracts = await _sent_pratica(db, organization_id)
    created: list = []
    _fake_stripe(monkeypatch, created=created)
    for _ in range(2):
        await payments_service.create_checkout_session_for_request(
            db, organization_id=organization_id, request=request, plan_key=payment_plans.PLAN_FULL,
            actor_user_id=user.id, success_url="https://x/ok", cancel_url="https://x/ko",
        )
    for n in (1, 2):
        await _webhook(db, organization_id, {
            "id": f"evt_twice_{n}", "type": "checkout.session.completed",
            "data": {"object": {"id": f"cs_pratica_{n}", "metadata": {"kind": "contract_request"}}},
        })

    second = (await db.execute(
        select(ContractRequestCheckout).where(ContractRequestCheckout.stripe_checkout_session_id == "cs_pratica_2")
    )).scalar_one()
    assert "0 contratti pagati" in second.outcome
    assert "3 già pagati" in second.outcome
    credits = list((await db.execute(
        select(WalletTransaction).where(WalletTransaction.reference_contract_id == contracts[0].id)
    )).scalars())
    assert len(credits) == 1


@pytest.mark.asyncio
async def test_stopping_billing_removes_only_that_contract_line(db, organization_id, monkeypatch):
    await _configure_stripe(db, organization_id)
    user, customer, request, contracts = await _sent_pratica(db, organization_id)
    for i, contract in enumerate(contracts):
        contract.stripe_subscription_id = "sub_stop"
        contract.stripe_subscription_item_id = f"si_stop_{i}"
    await db.commit()
    calls: list = []
    monkeypatch.setattr(stripe.SubscriptionItem, "delete", staticmethod(lambda item, **k: calls.append(("item", item))))
    monkeypatch.setattr(stripe.Subscription, "cancel", staticmethod(lambda sub, **k: calls.append(("sub", sub))))

    await payments_service.stop_contract_billing(
        db, organization_id=organization_id, contract=contracts[1], actor_user_id=user.id
    )
    assert calls == [("item", "si_stop_1")]
    await db.refresh(contracts[1])
    assert contracts[1].billing_stopped_at is not None
    await db.refresh(contracts[0])
    assert contracts[0].billing_stopped_at is None


# --- Contratti fuori da una pratica ------------------------------------------------


@pytest.mark.asyncio
async def test_a_contract_created_on_its_own_gets_a_pratica_of_one(db, organization_id):
    user, customer = await _customer(db, organization_id)
    luce = await _package(db, organization_id, name="Luce", energy_type="ELECTRICITY", price_cents=100_00)
    from app.domains.customers.schemas import SupplyPointCreate

    contract = await contracts_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=user.id, product_version_id=luce.id,
        supply_point_payload=SupplyPointCreate(
            energy_type="ELECTRICITY", pod_code="IT001E00000001", street="Via Roma 1", city="Roma", province="RM",
            postal_code="00100",
        ),
        email="mario@example.demo", holder_first_name="Mario", holder_last_name="Rossi",
    )
    request = await db.get(ContractRequest, contract.contract_request_id)
    assert request is not None
    assert request.customer_id == customer.id
    assert request.status == "SUBMITTED", "la pratica di un solo contratto segue il suo invio"
    [summary] = await requests_service.summaries(db, [request])
    assert summary["points_total"] == 1


# --- Le rotte HTTP ------------------------------------------------------------------
#
# The services above are what the business rules live in; these go through
# FastAPI itself -- routing, schemas, access checks -- because a NameError or a
# response_model mismatch in a router is invisible to every service test and
# surfaces as a 500 on the first real customer.


def _client(db, user_id, organization_id, roles):
    import httpx

    from app.core.db import get_db
    from app.core.deps import CurrentUser, get_current_user
    from app.main import app

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id, organization_id=organization_id, roles=roles
    )
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api")


@pytest.mark.asyncio
async def test_the_pratica_routes_work_end_to_end_for_the_customer(db, organization_id):
    user, customer = await _customer(db, organization_id)
    luce = await _package(db, organization_id, name="Luce", energy_type="ELECTRICITY", price_cents=120_00)
    gas = await _package(db, organization_id, name="Gas", energy_type="GAS", price_cents=60_00)
    app, client = _client(db, user.id, organization_id, ["CUSTOMER"])
    try:
        async with client:
            res = await client.post("/contract-requests", json={
                "holder_first_name": " Mario ", "holder_last_name": "Rossi", "email": "mario@example.demo",
                "pec": "", "iban": "IT60 X054 2811 1010 0000 0123 456",
                "street": "Via Roma 1", "city": "Roma", "province": "rm", "postal_code": "00100",
                "points_count": 2,
            })
            assert res.status_code == 201, res.text
            request_id = res.json()["id"]
            assert res.json()["iban"] == "IT60X0542811101000000123456"
            points = res.json()["points"]
            assert [p["position"] for p in points] == [1, 2]

            res = await client.post(f"/contract-requests/{request_id}/submit")
            assert res.status_code == 400, "un POD senza contratto blocca l'invio"

            for point, version in zip(points, (luce, gas), strict=True):
                res = await client.put(
                    f"/contract-requests/{request_id}/points/{point['id']}/product",
                    json={"product_version_id": str(version.id)},
                )
                assert res.status_code == 200, res.text

            res = await client.put(f"/contract-requests/{request_id}/points-count", json={"count": 0})
            assert res.status_code == 400

            res = await client.get(f"/contract-requests/{request_id}/documents")
            assert res.status_code == 200, res.text
            assert {r["document_type"] for r in res.json()["required"]} >= {"IDENTITY", "FISCAL_CODE"}

            res = await client.post(f"/contract-requests/{request_id}/submit")
            assert res.status_code == 200, res.text
            detail = res.json()
            assert detail["status"] == "SUBMITTED"
            assert detail["points_total"] == 2
            assert detail["total_gross_cents"] == 180_00
            assert detail["checkouts"] == [], "i tentativi di pagamento li vede solo lo staff"

            res = await client.get(f"/contract-requests/{request_id}/payment-options")
            assert res.status_code == 200, res.text
            options = {o["key"]: o for o in res.json()["options"]}
            assert options["MONTHLY_12"]["instalment_cents"] == 10_00 + 5_00
            assert len(res.json()["lines"]) == 2

            res = await client.get("/contract-requests/mine")
            assert [r["id"] for r in res.json()] == [request_id]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_another_customer_cannot_see_or_touch_a_pratica(db, organization_id):
    user, customer = await _customer(db, organization_id)
    request = await _open(db, organization_id, user, customer)
    other_user, _ = await _customer_without_role(db, organization_id)
    app, client = _client(db, other_user.id, organization_id, ["CUSTOMER"])
    try:
        async with client:
            assert (await client.get(f"/contract-requests/{request.id}")).status_code == 404
            res = await client.put(f"/contract-requests/{request.id}/points-count", json={"count": 3})
            assert res.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def _customer_without_role(db, organization_id):
    """A second customer in the same organization (the CUSTOMER role already
    exists from the first)."""
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Altro", last_name="Promoter",
        promoter_code=f"REF-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    code = await referral_service.get_or_create_promoter_code(db, organization_id=organization_id, agent_id=agent.id)
    user = await auth_service.register_with_referral(
        db, organization_id=organization_id,
        payload=RegisterRequest(
            organization_id=str(organization_id), referral_code=code.code,
            email=f"altro-{uuid.uuid4().hex[:8]}@example.demo", password="correct-horse-battery-staple",
            kind="PRIVATE", first_name="Luigi", last_name="Verdi", accept_privacy=True,
        ),
    )
    customer = (await db.execute(select(Customer).where(Customer.user_id == user.id))).scalar_one()
    return user, customer


@pytest.mark.asyncio
async def test_a_paid_contract_shows_in_accounting_with_its_instalments(db, organization_id, monkeypatch):
    """Session 54: paying a contract used to leave no real-money trace in
    "Contabilità" -- only its cashback. Every paid instalment is now a row,
    counted in the totals and opening the contract's own detail."""
    from app.domains.accounting import details as accounting_details
    from app.domains.accounting import service as accounting_service

    await _configure_stripe(db, organization_id)
    user, customer, request, contracts = await _sent_pratica(db, organization_id)
    _fake_stripe(monkeypatch, created=[], item_ids={str(c.id): f"si_acc_{i}" for i, c in enumerate(contracts)})
    await payments_service.create_checkout_session_for_request(
        db, organization_id=organization_id, request=request, plan_key=payment_plans.PLAN_MONTHLY_12,
        actor_user_id=user.id, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    await _webhook(db, organization_id, {
        "id": "evt_acc", "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_pratica_1", "subscription": "sub_acc", "invoice": "in_acc",
                            "metadata": {"kind": "contract_request"}}},
    })

    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=user.id)
    payments = [m for m in movements if m["kind"] == "CONTRACT_PAYMENT"]
    assert sorted(m["amount_cents"] for m in payments) == [5_00, 10_00, 20_00]
    assert all(m["payment_method"] == "CARD" and m["contract_request_id"] == request.id for m in payments)

    summary = await accounting_service.my_summary(db, organization_id=organization_id, user_id=user.id)
    assert summary["spent_contracts_cents"] == 35_00
    assert summary["spent_card_cents"] == 35_00
    assert summary["next_instalment_cents"] == 35_00, "la prossima rata di tutti i contratti insieme"

    detail = await accounting_details.build_detail(
        db, organization_id=organization_id, ref=f"contract:{contracts[0].id}", owner_user_id=user.id
    )
    assert detail["kind"] == "CONTRACT"
    assert len(detail["instalments"]) == 12
    assert detail["instalments"][0]["status"] == "PAID"
    assert detail["instalments"][0]["paid_at"] is not None
    assert any(e["label"].startswith("Prossima rata 2/12") for e in detail["timeline"])


# --- Session 55: il promoter compila per il cliente ----------------------------------


async def _promoter_and_customer(db, organization_id):
    """A promoter with a login, who is ALSO a customer (joined through "Lavora
    con noi"), and a customer of their own attributed to their referral code."""
    from app.core.security import hash_password
    from app.domains.users.models import User

    db.add(Role(organization_id=organization_id, code="CUSTOMER", name="Customer"))
    await db.commit()
    promoter_user = User(
        organization_id=organization_id, email=f"promo-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(promoter_user)
    await db.commit()
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Paola", last_name="Promoter",
        promoter_code=f"REF-{uuid.uuid4().hex[:8]}", parent_agent_id=None, user_id=promoter_user.id,
    )
    code = await referral_service.get_or_create_promoter_code(db, organization_id=organization_id, agent_id=agent.id)
    customer_user = await auth_service.register_with_referral(
        db, organization_id=organization_id,
        payload=RegisterRequest(
            organization_id=str(organization_id), referral_code=code.code,
            email=f"cliente-{uuid.uuid4().hex[:6]}@example.demo", password="correct-horse-battery-staple",
            kind="PRIVATE", first_name="Carla", last_name="Cliente", accept_privacy=True,
        ),
    )
    customer = (await db.execute(select(Customer).where(Customer.user_id == customer_user.id))).scalar_one()
    return promoter_user, agent, customer_user, customer


@pytest.mark.asyncio
async def test_a_promoter_who_is_also_a_customer_can_handle_their_customers_documents(db, organization_id):
    """"Lavora con noi" keeps the CUSTOMER role, and the document check used to
    read only the first role of the token: the promoter was refused the
    documents of the very contracts they had just filled in."""
    from fastapi import HTTPException

    from app.core.deps import CurrentUser
    from app.domains.documents.router import _assert_contract_document_access

    promoter_user, agent, customer_user, customer = await _promoter_and_customer(db, organization_id)
    luce = await _package(db, organization_id, name="Luce", energy_type="ELECTRICITY", price_cents=100_00)
    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=requests_service.HolderData(
            first_name="Carla", last_name="Cliente", email="carla@example.demo", pec=None, iban=None, address=ADDRESS,
        ),
        actor_user_id=promoter_user.id, actor_role="PROMOTER", promoter_agent_id=agent.id,
        points_count=2, product_version_id=luce.id,
    )
    contract, _ = await requests_service.list_points(db, request=request)
    assert contract.activated_by_promoter_id == agent.id

    as_promoter = CurrentUser(user_id=promoter_user.id, organization_id=organization_id, roles=["CUSTOMER", "PROMOTER"])
    assert await _assert_contract_document_access(
        db, current_user=as_promoter, contract=contract, actor_role="CUSTOMER"
    ) == "PROMOTER"
    as_customer = CurrentUser(user_id=customer_user.id, organization_id=organization_id, roles=["CUSTOMER"])
    assert await _assert_contract_document_access(
        db, current_user=as_customer, contract=contract, actor_role="CUSTOMER"
    ) == "CUSTOMER"

    stranger_user, _ = await _customer_without_role(db, organization_id)
    as_stranger = CurrentUser(user_id=stranger_user.id, organization_id=organization_id, roles=["CUSTOMER"])
    with pytest.raises(HTTPException):
        await _assert_contract_document_access(db, current_user=as_stranger, contract=contract, actor_role="CUSTOMER")


@pytest.mark.asyncio
async def test_the_customer_is_told_when_their_promoter_sends_a_pratica(db, organization_id):
    from app.domains.notifications.models import Notification

    promoter_user, agent, customer_user, customer = await _promoter_and_customer(db, organization_id)
    luce = await _package(db, organization_id, name="Luce", energy_type="ELECTRICITY", price_cents=100_00)
    request = await requests_service.create_request(
        db, organization_id=organization_id, customer_id=customer.id,
        holder=requests_service.HolderData(
            first_name="Carla", last_name="Cliente", email="carla@example.demo", pec=None, iban=None, address=ADDRESS,
        ),
        actor_user_id=promoter_user.id, actor_role="PROMOTER", promoter_agent_id=agent.id,
        points_count=1, product_version_id=luce.id,
    )
    await requests_service.submit_request(db, request=request, actor_user_id=promoter_user.id)

    notes = list((await db.execute(
        select(Notification).where(Notification.recipient_user_id == customer_user.id)
    )).scalars())
    assert any("Paola Promoter" in (n.body or "") for n in notes)
    [summary] = await requests_service.summaries(db, [request])
    assert summary["activated_by_promoter_name"] == "Paola Promoter"
    assert summary["customer_id"] == customer.id


# --- Session 59: cashback dei contratti a rate, intero in anticipo o rata per rata ---------


async def _set_cashback_mode(db, organization_id, mode: str) -> None:
    from app.domains.organizations.models import Organization

    org = await db.get(Organization, organization_id)
    org.settings = {**(org.settings or {}), "contract_instalment_cashback_mode": mode}
    await db.commit()


async def _pay_first_instalment_of_12(db, organization_id, monkeypatch):
    user, customer, request, contracts = await _sent_pratica(db, organization_id)
    items = {str(c.id): f"si_cb_{i}" for i, c in enumerate(contracts)}
    lines = [
        {"id": f"il_{i}", "amount": amount, "parent": {"subscription_item_details": {"subscription_item": f"si_cb_{i}"}}}
        for i, amount in enumerate((10_00, 20_00, 5_00))
    ]
    _fake_stripe(monkeypatch, created=[], item_ids=items, lines=lines)
    await payments_service.create_checkout_session_for_request(
        db, organization_id=organization_id, request=request, plan_key=payment_plans.PLAN_MONTHLY_12,
        actor_user_id=user.id, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    await _webhook(db, organization_id, {
        "id": "evt_cb_first", "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_pratica_1", "subscription": "sub_cb", "invoice": "in_cb_1",
                            "metadata": {"kind": "contract_request"}}},
    })
    return user, contracts


async def _second_month(db, organization_id, event_id="evt_cb_2"):
    await _webhook(db, organization_id, {"id": event_id, "type": "invoice.paid", "data": {"object": {
        "id": "in_cb_2", "billing_reason": "subscription_cycle", "amount_paid": 35_00,
        "parent": {"subscription_details": {"subscription": "sub_cb"}},
    }}})


async def _credits(db, contract):
    return sorted((await db.execute(
        select(WalletTransaction.amount_cents).where(WalletTransaction.reference_contract_id == contract.id)
    )).scalars())


@pytest.mark.asyncio
async def test_upfront_mode_credits_the_whole_cashback_at_the_first_instalment_and_nothing_after(
    db, organization_id, monkeypatch
):
    await _configure_stripe(db, organization_id)
    await _set_cashback_mode(db, organization_id, "UPFRONT")
    _user, contracts = await _pay_first_instalment_of_12(db, organization_id, monkeypatch)
    # Luce A: 120,00 with 100% cashback -- all of it, at once.
    assert await _credits(db, contracts[0]) == [120_00]

    await _second_month(db, organization_id)
    assert await _credits(db, contracts[0]) == [120_00], "nessun altro accredito sulle rate successive"


@pytest.mark.asyncio
async def test_a_contract_credited_in_advance_is_not_credited_again_if_the_setting_changes(
    db, organization_id, monkeypatch
):
    await _configure_stripe(db, organization_id)
    await _set_cashback_mode(db, organization_id, "UPFRONT")
    _user, contracts = await _pay_first_instalment_of_12(db, organization_id, monkeypatch)
    await _set_cashback_mode(db, organization_id, "PER_INSTALMENT")
    await _second_month(db, organization_id)
    assert await _credits(db, contracts[0]) == [120_00]


@pytest.mark.asyncio
async def test_a_month_confirmed_by_hand_and_then_collected_by_stripe_earns_cashback_once(
    db, organization_id, monkeypatch
):
    from app.domains.contracts import instalments as instalments_service

    await _configure_stripe(db, organization_id)
    user, contracts = await _pay_first_instalment_of_12(db, organization_id, monkeypatch)
    assert await _credits(db, contracts[0]) == [10_00], "per rata è il comportamento predefinito"

    # Stripe fails month 2, the customer pays it by transfer and an
    # administrator confirms it; then Stripe's own retry of that same invoice
    # goes through too.
    await _webhook(db, organization_id, {"id": "evt_cb_2_failed", "type": "invoice.payment_failed", "data": {"object": {
        "id": "in_cb_2", "billing_reason": "subscription_cycle", "amount_due": 35_00,
        "parent": {"subscription_details": {"subscription": "sub_cb"}},
    }}})
    await instalments_service.confirm_manually(db, contract=contracts[0], number=2, actor_user_id=user.id)
    await contracts_service.credit_contract_instalment_cashback(
        db, organization_id=organization_id, contract=contracts[0], instalment_number=2
    )
    await _second_month(db, organization_id)
    assert await _credits(db, contracts[0]) == [10_00, 10_00]


# --- Bonifico (Session 65) -----------------------------------------------------------


async def _configure_bank(db, organization_id) -> None:
    from app.domains.organizations.models import Organization

    org = await db.get(Organization, organization_id)
    org.settings = {**(org.settings or {}), "bank_iban": "IT66W0883330410000000015702", "bank_account_holder": "Lial Energy"}
    await db.commit()


@pytest.mark.asyncio
async def test_a_pratica_paid_by_bank_transfer_is_paid_only_when_an_admin_confirms(db, organization_id):
    await _configure_bank(db, organization_id)
    user, customer, request, contracts = await _sent_pratica(db, organization_id)

    request = await requests_service.request_bank_transfer(db, request=request, actor_user_id=user.id)
    assert request.bank_transfer_total_cents == 81_60 + 163_20 + 40_80  # one-go discount, 32%
    for contract in contracts:
        await db.refresh(contract)
        assert contract.paid_at is None
        assert (contract.payment_plan, contract.payment_method) == (payment_plans.PLAN_FULL, "BANK_TRANSFER")
        assert contract.payment_discount_cents == contract.gross_amount_cents * 32 // 100
    [summary] = await requests_service.summaries(db, [request])
    assert summary["bank_transfer_pending"] is True and summary["points_payable"] == 3

    admin_id = user.id  # the permission is checked by the router; the service records who confirmed
    paid = await requests_service.confirm_bank_transfer(db, request=request, actor_user_id=admin_id)
    assert len(paid) == 3
    for contract in contracts:
        await db.refresh(contract)
        assert contract.paid_at is not None and contract.payment_method == "BANK_TRANSFER"
        assert contract.payment_discount_cents == contract.gross_amount_cents * 32 // 100
        rows = list((await db.execute(
            select(ContractInstalment).where(ContractInstalment.contract_id == contract.id)
        )).scalars())
        assert [(r.status, r.amount_cents, r.payment_source) for r in rows] == [
            ("PAID", contract.gross_amount_cents - contract.payment_discount_cents, "ADMIN")
        ]
    credits = list((await db.execute(
        select(WalletTransaction).where(WalletTransaction.reference_contract_id.in_([c.id for c in contracts]))
    )).scalars())
    assert [t.amount_cents for t in credits] == [81_60]  # Luce A, 100% of what was paid
    [summary] = await requests_service.summaries(db, [request])
    assert summary["bank_transfer_pending"] is False and summary["points_paid"] == 3
    with pytest.raises(requests_service.BankTransferError):
        await requests_service.confirm_bank_transfer(db, request=request, actor_user_id=admin_id)


@pytest.mark.asyncio
async def test_bank_transfer_needs_an_iban_configured(db, organization_id):
    user, _customer, request, _contracts = await _sent_pratica(db, organization_id)
    with pytest.raises(requests_service.BankTransferError):
        await requests_service.request_bank_transfer(db, request=request, actor_user_id=user.id)

