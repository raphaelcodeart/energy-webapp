"""Marketplace 3 (Shopify dropshipping): pricing, import, the checkout shared
with the other shops (LialCash never 100%, card +surcharge), sending paid
orders to the Shopify store without ever duplicating them, and following
them until delivery. Shopify is replaced by a fake at client.call, the one
door every request goes through."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import stripe
from sqlalchemy import select

from app.core.security import hash_otp_code, hash_password
from app.domains.accounting import details as accounting_details
from app.domains.accounting import service as accounting_service
from app.domains.auth import service as auth_service
from app.domains.auth.models import OtpCode
from app.domains.marketplaces import rules
from app.domains.organizations import service as organizations_service
from app.domains.organizations.models import Organization
from app.domains.organizations.schemas import OrganizationSettingsUpdate
from app.domains.rbac.models import Role, UserRole
from app.domains.shopify_dropshipping import client as shopify_client
from app.domains.shopify_dropshipping import pricing
from app.domains.shopify_dropshipping import service as shopify_service
from app.domains.shopify_dropshipping.models import ShopifySettings, ShopifyVariant
from app.domains.users.models import User
from app.domains.wallets import service as wallet_service

OTP = "333444"
ADDRESS = {
    "recipient_name": "Mario Rossi", "recipient_phone": "3331234567", "address_line1": "Via Roma 1",
    "address_line2": None, "city": "Milano", "province": "MI", "postal_code": "20100",
}
PRODUCT_GID = "gid://shopify/Product/1"


class FakeShopify:
    def __init__(self):
        self.calls: list[str] = []
        self.drafts: dict[str, dict] = {}
        self.orders: dict[str, dict] = {}
        self.fail_complete_once: str | None = None  # "lost": completes but the answer is lost
        self.fail_create: str | None = None
        self.drafts_created = 0

    def _op(self, query: str) -> str:
        for name in ("draftOrderCreate", "draftOrderComplete", "draftOrder(", "orders(first", "order(id", "product(id",
                     "products(first", "shop {"):
            if name in query:
                return name
        raise AssertionError(f"unexpected query {query[:80]}")

    async def __call__(self, settings, query, variables=None):
        op = self._op(query)
        self.calls.append(op)
        variables = variables or {}
        if op == "shop {":
            return {"shop": {"name": "Negozio Test", "currencyCode": "EUR", "myshopifyDomain": "negozio-test.myshopify.com"}}
        if op in ("products(first", "product(id"):
            node = {
                "id": PRODUCT_GID, "title": "Wireless Earbuds", "handle": "earbuds", "vendor": "ACME",
                "status": "ACTIVE", "descriptionHtml": "<p>Great <b>sound</b></p><script>x()</script>",
                "featuredImage": {"url": "https://img/1.jpg"},
                "images": {"nodes": [{"url": "https://img/1.jpg"}, {"url": "https://img/2.jpg"}]},
                "variants": {"nodes": [
                    {"id": "gid://shopify/ProductVariant/11", "title": "Black", "sku": "EB-B", "price": "24.00",
                     "inventoryQuantity": 50, "image": None,
                     "inventoryItem": {"tracked": True, "unitCost": {"amount": "10.00", "currencyCode": "EUR"}}},
                    {"id": "gid://shopify/ProductVariant/12", "title": "White", "sku": "EB-W", "price": "25.00",
                     "inventoryQuantity": 0, "image": None,
                     "inventoryItem": {"tracked": True, "unitCost": None}},
                ]},
            }
            if op == "product(id":
                return {"product": node}
            return {"products": {"nodes": [node], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
        if op == "draftOrderCreate":
            if self.fail_create:
                return {"draftOrderCreate": {"draftOrder": None, "userErrors": [{"field": ["x"], "message": self.fail_create}]}}
            self.drafts_created += 1
            draft_id = f"gid://shopify/DraftOrder/{self.drafts_created}"
            self.drafts[draft_id] = {"input": variables["input"], "order": None}
            return {"draftOrderCreate": {"draftOrder": {"id": draft_id, "name": f"#D{self.drafts_created}"}, "userErrors": []}}
        if op == "draftOrderComplete":
            draft = self.drafts[variables["id"]]
            if draft["order"] is None:
                n = len(self.orders) + 1
                order = {"id": f"gid://shopify/Order/{n}", "name": f"#10{n:02d}", "tags": draft["input"]["tags"],
                         "cancelledAt": None, "displayFulfillmentStatus": "UNFULFILLED", "fulfillments": []}
                self.orders[order["id"]] = order
                draft["order"] = {"id": order["id"], "name": order["name"]}
            if self.fail_complete_once:
                self.fail_complete_once = None
                raise shopify_client.ShopifyApiError("Shopify non risponde (ReadTimeout). Riprova tra poco.", "TEMPORARY")
            return {"draftOrderComplete": {"draftOrder": {"id": variables["id"], "order": draft["order"]}, "userErrors": []}}
        if op == "draftOrder(":
            draft = self.drafts.get(variables["id"])
            return {"draftOrder": None if draft is None else {
                "id": variables["id"], "status": "COMPLETED" if draft["order"] else "OPEN", "order": draft["order"]}}
        if op == "orders(first":
            tag = variables["query"].split("'")[1]
            return {"orders": {"nodes": [
                {"id": o["id"], "name": o["name"], "tags": o["tags"]} for o in self.orders.values() if tag in o["tags"]
            ]}}
        if op == "order(id":
            return {"order": self.orders.get(variables["id"])}
        raise AssertionError(op)

    def count(self, op):
        return sum(1 for c in self.calls if c == op)


@pytest.fixture
def fake_shopify(monkeypatch):
    fake = FakeShopify()
    monkeypatch.setattr(shopify_client, "call", fake)
    return fake


async def _user(db, organization_id, role_code="CUSTOMER"):
    user = User(
        organization_id=organization_id, email=f"{role_code.lower()}-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("x"),
    )
    db.add(user)
    await db.flush()
    role = (
        await db.execute(select(Role).where(Role.organization_id == organization_id, Role.code == role_code))
    ).scalar_one_or_none()
    if role is None:
        role = Role(organization_id=organization_id, code=role_code, name=role_code.title())
        db.add(role)
        await db.flush()
    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))
    await db.commit()
    await db.refresh(user)
    return user


async def _shop(db, organization_id, admin, credit_percentage=None, **settings_updates):
    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702")
    )
    row = await shopify_service.get_settings_row(db, organization_id=organization_id)
    await shopify_service.update_settings(
        db, row=row, actor_user_id=admin.id,
        updates={
            "shop_domain": "https://Negozio-Test.myshopify.com/admin", "access_token": "shpat_secret_abcd",
            "enabled": True, "auto_forward": False, **settings_updates,
        },
    )
    product = await shopify_service.import_product(
        db, row=row, actor_user_id=admin.id, product_id=PRODUCT_GID, name="Auricolari wireless", description=None,
        credit_discount_percentage=credit_percentage, markup_percentage=None, variant_ids=None, activate=True,
    )
    variants = (await db.execute(select(ShopifyVariant).where(ShopifyVariant.product_id == product.id))).scalars().all()
    return row, product, {v.sku: v for v in variants}


async def _otp(db, user_id):
    db.add(OtpCode(
        user_id=user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code_hash=hash_otp_code(OTP),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    ))
    await db.commit()


async def _card_ready(db, organization_id, monkeypatch):
    org = await db.get(Organization, organization_id)
    org.settings = {**(org.settings or {}), "stripe_secret_key": "sk_test_fake", "stripe_publishable_key": "pk_test_fake"}
    await db.commit()
    created = []

    class _Session:
        def __init__(self, n):
            self.id = f"cs_shopify_{n}_{uuid.uuid4().hex[:6]}"
            self.url = f"https://stripe.example/{self.id}"

    monkeypatch.setattr(
        stripe.checkout.Session, "create", staticmethod(lambda **p: created.append(p) or _Session(len(created)))
    )
    return created


async def _paid_order(db, organization_id, fake_shopify):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    order = await shopify_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    await shopify_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    return admin, customer, order


# --- Prezzi e impostazioni ----------------------------------------------------------------------


def test_price_starts_from_cost_or_price_is_marked_up_and_rounded_up():
    row = ShopifySettings(
        currency_rate=Decimal(1), price_basis="COST", markup_percentage=100, markup_fixed_cents=0,
        price_rounding="90", shipping_mode="CUSTOMER_PAYS", shipping_flat_cents=590,
    )
    assert pricing.sale_price_cents(cost=Decimal("10.00"), price=Decimal("24.00"), settings=row) == 2090
    # No cost in the store: the price is the base.
    assert pricing.sale_price_cents(cost=None, price=Decimal("25.00"), settings=row) == 5090
    row.price_basis = "PRICE"
    row.markup_percentage = 0
    row.price_rounding = "NONE"
    assert pricing.sale_price_cents(cost=Decimal("10.00"), price=Decimal("24.00"), settings=row) == 2400
    row.shipping_mode = "INCLUDED"
    assert pricing.sale_price_cents(cost=None, price=Decimal("24.00"), settings=row) == 2990
    assert pricing.shipping_price_cents(settings=row) == 0
    row.currency_rate = Decimal("0.92")  # a store in USD
    row.shipping_mode = "CUSTOMER_PAYS"
    assert pricing.sale_price_cents(cost=None, price=Decimal("10.00"), settings=row) == 920


def test_domain_is_normalized():
    assert shopify_client.normalize_domain("https://Mio-Negozio.myshopify.com/admin") == "mio-negozio.myshopify.com"
    assert shopify_client.normalize_domain("mio-negozio") == "mio-negozio.myshopify.com"
    assert shopify_client.normalize_domain("  ") is None


@pytest.mark.asyncio
async def test_token_is_never_returned_and_new_shop_defaults(db, organization_id, fake_shopify):
    admin = await _user(db, organization_id, "ADMIN")
    row = await shopify_service.get_settings_row(db, organization_id=organization_id)
    assert row.markup_percentage == 100 and row.default_credit_percentage == rules.DEFAULT_CREDIT_PERCENTAGE
    with pytest.raises(shopify_service.ShopifyValidationError):
        await shopify_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": True})
    await shopify_service.update_settings(
        db, row=row, actor_user_id=admin.id,
        updates={"shop_domain": "negozio-test", "access_token": "shpat_1234567890abcd"},
    )
    read = shopify_service.settings_read_dict(row)
    assert read["shop_domain"] == "negozio-test.myshopify.com"
    assert read["access_token_hint"] == "…abcd"
    assert "shpat_1234567890abcd" not in str(read)
    with pytest.raises(shopify_service.ShopifyValidationError):
        await shopify_service.update_settings(
            db, row=row, actor_user_id=admin.id, updates={"shop_domain": "www.example.com"}
        )
    info = await shopify_service.test_connection(db, row=row)
    assert info["shop_name"] == "Negozio Test" and info["shop_currency"] == "EUR"


@pytest.mark.asyncio
async def test_import_saves_variants_with_our_price_at_30_percent_lialcash(db, organization_id, fake_shopify):
    admin = await _user(db, organization_id, "ADMIN")
    row, product, variants = await _shop(db, organization_id, admin)
    assert product.credit_discount_percentage == 30
    assert product.description == "Great sound"  # plain text, no script
    assert variants["EB-B"].price_cents == 2090  # cost 10 +100% -> 20,90
    assert variants["EB-W"].price_cents == 5090  # no cost: price 25 +100%
    with pytest.raises(shopify_service.ShopifyValidationError):
        await shopify_service.import_product(
            db, row=row, actor_user_id=admin.id, product_id=PRODUCT_GID, name="x", description=None,
            credit_discount_percentage=None, markup_percentage=None, variant_ids=None, activate=True,
        )
    # LialCash may be raised, never to 100%.
    with pytest.raises(shopify_service.ShopifyValidationError):
        await shopify_service.update_product(
            db, row=row, product=product, updates={"credit_discount_percentage": 100}, actor_user_id=admin.id
        )
    await shopify_service.update_product(
        db, row=row, product=product, updates={"credit_discount_percentage": 99}, actor_user_id=admin.id
    )
    # A settings change re-prices.
    await shopify_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"markup_percentage": 50})
    await db.refresh(variants["EB-B"])
    assert variants["EB-B"].price_cents == 1590


# --- Checkout ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkout_with_lialcash_never_the_whole_price(db, organization_id, fake_shopify):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin, credit_percentage=99)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=10000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    quote = await shopify_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id, quantity=1
    )
    assert quote["amount_cents"] == 2090 + 590
    assert quote["max_creditable_cents"] < quote["amount_cents"]
    with pytest.raises(shopify_service.ShopifyValidationError):  # out of stock
        await shopify_service.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-W"].id, quantity=1
        )
    # Even a product stored at 100% (by hand in the DB) is never bought whole in LialCash.
    assert shopify_service.max_creditable_cents(amount_cents=1000, credit_discount_percentage=100) == 990
    with pytest.raises(shopify_service.InvalidOtpError):
        await shopify_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
            quantity=1, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
            actor_user_id=customer.id, otp_code="000000", note=None,
        )
    await _otp(db, customer.id)
    order = await shopify_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=1000, payment_method="BANK_TRANSFER",
        actor_user_id=customer.id, otp_code=OTP, note=None,
    )
    assert order.status == "AWAITING_PAYMENT" and order.card_surcharge_cents == 0
    txn = await db.get(wallet_service.WalletTransaction, order.credit_debit_transaction_id)
    assert txn.reference_shopify_order_id == order.id

    await shopify_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)
    euro_rows = [m for m in movements if m["kind"] == "ORDER_PAYMENT" and m["order_id"] == order.id]
    assert euro_rows and euro_rows[0]["amount_cents"] == 2680 - 1000
    wallet_rows = [m for m in movements if m["kind"] == "WALLET" and m["order_id"] == order.id]
    assert wallet_rows and wallet_rows[0]["product_name"] == "Auricolari wireless"
    detail = await accounting_details._order_detail(
        db, organization_id=organization_id, entity_id=order.id, owner_user_id=customer.id
    )
    assert detail["subtitle"].endswith("Marketplace 3")
    assert "Shopify" not in str(detail)


@pytest.mark.asyncio
async def test_card_costs_more_frozen_and_recomputed_on_switch(db, organization_id, fake_shopify, monkeypatch):
    from app.domains.payments import service as payments_service

    created = await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    quote = await shopify_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id, quantity=1
    )
    assert quote["card_surcharge_percentage"] == 5
    assert quote["card_amount_cents"] == 2680 + 134

    order = await shopify_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="CARD",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    assert order.card_surcharge_cents == 134 and shopify_service.amount_due_cents(order) == 2814
    assert created[-1]["line_items"][0]["price_data"]["unit_amount"] == 2814
    assert created[-1]["metadata"]["kind"] == "shopify_order"

    await shopify_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="BANK_TRANSFER"
    )
    assert order.card_surcharge_cents == 0
    # The percentage changes before the customer pays by card: the new one applies.
    await rules.update_config(db, organization_id=organization_id, labels=None, card_surcharge_percentage=10)
    await payments_service.create_checkout_session_for_shopify_order(
        db, organization_id=organization_id, order=order, success_url="https://x/ok", cancel_url="https://x/ko",
    )
    await db.refresh(order)
    assert order.payment_method == "CARD" and order.card_surcharge_cents == 268
    assert created[-1]["line_items"][0]["price_data"]["unit_amount"] == 2680 + 268

    paid = await shopify_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
    )
    assert paid.status == "PAID"
    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)
    euro_rows = [m for m in movements if m["kind"] == "ORDER_PAYMENT" and m["order_id"] == order.id]
    assert euro_rows and euro_rows[0]["amount_cents"] == 2948


@pytest.mark.asyncio
async def test_webhook_marks_the_shopify_order_paid(db, organization_id, fake_shopify, monkeypatch):
    from app.domains.payments import service as payments_service

    await _card_ready(db, organization_id, monkeypatch)
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    _row, _product, variants = await _shop(db, organization_id, admin)
    order = await shopify_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id,
        quantity=1, address=ADDRESS, credit_applied_cents=0, payment_method="CARD",
        actor_user_id=customer.id, otp_code=None, note=None,
    )
    import hashlib
    import hmac
    import json
    import time

    secret = "whsec_shopify_test"
    org = await db.get(Organization, organization_id)
    org.settings = {**org.settings, "stripe_webhook_secret": secret}
    await db.commit()
    body = json.dumps({
        "id": f"evt_{uuid.uuid4().hex[:10]}", "object": "event", "type": "checkout.session.completed",
        "data": {"object": {
            # An older link (the confirmation email's): only the metadata points at the order.
            "id": "cs_old_email_link", "object": "checkout.session",
            "metadata": {"kind": "shopify_order", "shopify_order_id": str(order.id)},
        }},
    }).encode()
    timestamp = int(time.time())
    signature = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    await payments_service.handle_webhook_event(
        db, organization_id=organization_id, payload=body, sig_header=f"t={timestamp},v1={signature}"
    )
    await db.refresh(order)
    assert order.status == "PAID"


# --- Invio al negozio -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paid_order_is_created_in_the_store_once(db, organization_id, fake_shopify):
    admin, _customer, order = await _paid_order(db, organization_id, fake_shopify)
    order = await shopify_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    assert order.fulfillment_status == "SENT" and order.shopify_order_id == "gid://shopify/Order/1"
    draft = next(iter(fake_shopify.drafts.values()))["input"]
    assert draft["lineItems"] == [{"variantId": "gid://shopify/ProductVariant/11", "quantity": 1}]
    assert shopify_service.order_tag(order) in draft["tags"] and len(shopify_service.order_tag(order)) <= 40
    assert draft["shippingAddress"]["city"] == "Milano"
    with pytest.raises(shopify_service.ShopifyValidationError):
        await shopify_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    assert len(fake_shopify.orders) == 1


@pytest.mark.asyncio
async def test_lost_answer_on_complete_never_duplicates(db, organization_id, fake_shopify):
    admin, _customer, order = await _paid_order(db, organization_id, fake_shopify)
    fake_shopify.fail_complete_once = "lost"
    order = await shopify_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    assert order.fulfillment_status == "ERROR" and order.last_error_kind == "TEMPORARY"
    assert order.next_retry_at is not None and order.shopify_draft_order_id
    # The retry reads the draft it already completed: same order, no new draft.
    order = await shopify_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
    assert order.fulfillment_status == "SENT"
    assert len(fake_shopify.orders) == 1 and fake_shopify.drafts_created == 1


@pytest.mark.asyncio
async def test_order_created_by_a_lost_attempt_is_found_by_its_tag(db, organization_id, fake_shopify):
    admin, _customer, order = await _paid_order(db, organization_id, fake_shopify)
    # An earlier attempt created and completed the order, and died before saving anything.
    fake_shopify.orders["gid://shopify/Order/77"] = {
        "id": "gid://shopify/Order/77", "name": "#1077", "tags": ["lialenergy", shopify_service.order_tag(order)],
        "cancelledAt": None, "displayFulfillmentStatus": "UNFULFILLED", "fulfillments": [],
    }
    order = await shopify_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    assert order.shopify_order_id == "gid://shopify/Order/77" and fake_shopify.drafts_created == 0


@pytest.mark.asyncio
async def test_store_refusal_alerts_staff_and_is_not_retried(db, organization_id, fake_shopify):
    admin, _customer, order = await _paid_order(db, organization_id, fake_shopify)
    fake_shopify.fail_create = "Variant is out of stock"
    order = await shopify_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    assert order.fulfillment_status == "ERROR" and order.last_error_kind == "VALIDATION"
    assert order.next_retry_at is None and "out of stock" in order.forward_error


@pytest.mark.asyncio
async def test_tracking_and_delivery_reach_the_customer(db, organization_id, fake_shopify):
    from app.domains.notifications.models import Notification

    admin, customer, order = await _paid_order(db, organization_id, fake_shopify)
    order = await shopify_service.forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)
    remote = fake_shopify.orders[order.shopify_order_id]
    remote["displayFulfillmentStatus"] = "FULFILLED"
    remote["fulfillments"] = [{"status": "SUCCESS", "displayStatus": "IN_TRANSIT", "deliveredAt": None,
                               "trackingInfo": [{"number": "LX123IT", "url": "https://track/LX123IT", "company": "Poste"}]}]
    assert await shopify_service.sync_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.fulfillment_status == "SHIPPED" and order.tracking_number == "LX123IT"
    read = await shopify_service.order_read_dict(db, order, admin=False)
    assert read["delivery_status"] == "SHIPPED" and read["tracking_url"] == "https://track/LX123IT"
    remote["fulfillments"][0]["deliveredAt"] = "2026-09-20T10:00:00Z"
    await shopify_service.sync_orders(db, organization_id=organization_id)
    await db.refresh(order)
    assert order.fulfillment_status == "DELIVERED"
    notes = list((await db.execute(
        select(Notification).where(Notification.recipient_user_id == customer.id, Notification.type == "ORDER_SHIPPED")
    )).scalars())
    assert len(notes) == 2


@pytest.mark.asyncio
async def test_retry_job_sends_paid_orders_that_were_never_sent(db, organization_id, fake_shopify):
    admin, _customer, order = await _paid_order(db, organization_id, fake_shopify)
    row = await shopify_service.get_settings_row(db, organization_id=organization_id)
    await shopify_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"auto_forward": True})
    order.paid_at = order.paid_at - timedelta(minutes=5)
    await db.commit()
    assert await shopify_service.retry_due_orders(db, organization_id=organization_id) == 1
    await db.refresh(order)
    assert order.fulfillment_status == "SENT"
    assert await shopify_service.retry_due_orders(db, organization_id=organization_id) == 0
    assert len(fake_shopify.orders) == 1


@pytest.mark.asyncio
async def test_switched_off_shop_sells_nothing(db, organization_id, fake_shopify):
    admin = await _user(db, organization_id, "ADMIN")
    customer = await _user(db, organization_id)
    row, _product, variants = await _shop(db, organization_id, admin)
    await shopify_service.update_settings(db, row=row, actor_user_id=admin.id, updates={"enabled": False})
    with pytest.raises(shopify_service.ShopifyValidationError):
        await shopify_service.get_quote(
            db, organization_id=organization_id, customer_user_id=customer.id, variant_id=variants["EB-B"].id, quantity=1
        )
