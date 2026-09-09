"""payments/service.py::handle_webhook_event, exercised end-to-end with a
REAL Stripe-style signed payload (not a mock) -- specifically to catch bugs
in how the code reads fields off the real `stripe.StripeObject` that
`stripe.Webhook.construct_event()` parses the payload into. A prior version
of this function called `.get(...)` on that object (a dict method
`StripeObject` deliberately doesn't implement in this SDK version, it raises
AttributeError) -- every other test in this suite called
orders_service.mark_paid_via_stripe()/invoice_redemptions_service.
mark_paid_via_stripe() directly, bypassing construct_event() and the real
StripeObject entirely, so that bug shipped to production twice before being
caught by an actual user report. These tests build the same HMAC-SHA256
signature scheme Stripe itself uses, so construct_event() parses a real
payload the same way it would a genuine webhook delivery."""

import hashlib
import hmac
import json
import time
import uuid

import pytest

from app.core.security import hash_password
from app.domains.catalog import service as catalog_service
from app.domains.catalog.schemas import ProductCreate
from app.domains.invoice_redemptions import service as redemptions_service
from app.domains.orders import service as orders_service
from app.domains.organizations import service as organizations_service
from app.domains.organizations.schemas import PaymentSettingsUpdate
from app.domains.partners import service as partners_service
from app.domains.partners.schemas import PartnerCreate
from app.domains.payments import service as payments_service
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User

WEBHOOK_SECRET = "whsec_test_signing_secret"


def _sign(payload_bytes: bytes, secret: str = WEBHOOK_SECRET) -> str:
    """Same scheme stripe.Webhook.construct_event() verifies:
    t=<unix-timestamp>,v1=hmac_sha256(secret, f"{timestamp}.{payload}")."""
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload_bytes.decode()}"
    signature = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def _checkout_session_completed_event(*, session_id: str, kind: str | None, order_id: uuid.UUID | None = None,
                                       redemption_id: uuid.UUID | None = None) -> bytes:
    """A real, minimal checkout.session.completed event body -- same shape
    Stripe actually sends, just trimmed to the fields this codebase reads."""
    metadata = {}
    if kind is not None:
        metadata["kind"] = kind
    if order_id is not None:
        metadata["order_id"] = str(order_id)
    if redemption_id is not None:
        metadata["invoice_redemption_id"] = str(redemption_id)
    body = {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "status": "complete",
                "payment_status": "paid",
                "metadata": metadata,
            }
        },
    }
    return json.dumps(body).encode()


async def _get_or_create_role(db, organization_id, *, role_code: str) -> Role:
    from sqlalchemy import select

    existing = (
        await db.execute(select(Role).where(Role.organization_id == organization_id, Role.code == role_code))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    role = Role(organization_id=organization_id, code=role_code, name=role_code.title())
    db.add(role)
    await db.flush()
    return role


async def _make_user_with_role(db, organization_id, *, role_code: str = "CUSTOMER"):
    user = User(
        organization_id=organization_id, email=f"{role_code.lower()}-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.flush()
    role = await _get_or_create_role(db, organization_id, role_code=role_code)
    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))
    await db.commit()
    await db.refresh(user)
    return user


async def _configure_stripe(db, organization_id):
    await organizations_service.update_payment_settings(
        db, organization_id=organization_id,
        payload=PaymentSettingsUpdate(
            stripe_publishable_key="pk_test_abc", stripe_secret_key="sk_test_xyz",
            stripe_webhook_secret=WEBHOOK_SECRET,
        ),
    )


async def _make_product_version(db, organization_id, actor_user_id, *, price_cents=5000):
    product = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        payload=ProductCreate(
            code=f"PAY-{uuid.uuid4().hex[:6]}", customer_type="PRIVATE", category="DROPSHIPPING",
            name="Gadget Webhook Test", base_price_cents=price_cents, credit_discount_percentage=0,
        ),
    )
    _, versions = await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=product.id)
    return versions[0]


@pytest.mark.asyncio
async def test_webhook_marks_an_order_paid_with_a_real_signed_payload(db, organization_id):
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD",
    )
    session_id = f"cs_test_{uuid.uuid4().hex[:16]}"
    await orders_service.attach_stripe_checkout_session(db, order=order, session_id=session_id)

    payload = _checkout_session_completed_event(session_id=session_id, kind="order", order_id=order.id)
    sig_header = _sign(payload)

    await payments_service.handle_webhook_event(
        db, organization_id=organization_id, payload=payload, sig_header=sig_header
    )

    refreshed = await orders_service.get_org_scoped(db, organization_id=organization_id, order_id=order.id)
    assert refreshed.status == "PAID"


@pytest.mark.asyncio
async def test_webhook_with_no_kind_metadata_defaults_to_order(db, organization_id):
    """A session created before metadata.kind existed (or any other
    unexpected/missing value) must still resolve as an order -- the
    original and only kind before this routing existed."""
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD",
    )
    session_id = f"cs_test_{uuid.uuid4().hex[:16]}"
    await orders_service.attach_stripe_checkout_session(db, order=order, session_id=session_id)

    payload = _checkout_session_completed_event(session_id=session_id, kind=None)
    sig_header = _sign(payload)

    await payments_service.handle_webhook_event(
        db, organization_id=organization_id, payload=payload, sig_header=sig_header
    )

    refreshed = await orders_service.get_org_scoped(db, organization_id=organization_id, order_id=order.id)
    assert refreshed.status == "PAID"


@pytest.mark.asyncio
async def test_webhook_marks_an_invoice_redemption_credited_with_a_real_signed_payload(db, organization_id):
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    partner = await partners_service.create_partner(
        db, organization_id=organization_id, payload=PartnerCreate(name=f"Partner {uuid.uuid4().hex[:6]}")
    )

    redemption = await redemptions_service.submit_redemption(
        db, organization_id=organization_id, customer_user_id=customer.id, partner_id=partner.id,
        declared_amount_cents=10000, file_bytes=b"%PDF-1.4", content_type="application/pdf",
        original_filename="x.pdf",
    )
    redemption = await redemptions_service.verify(
        db, organization_id=organization_id, redemption_id=redemption.id, confirmed_amount_cents=10000,
        actor_user_id=admin.id,
    )
    redemption = await redemptions_service.change_payment_method(
        db, organization_id=organization_id, redemption=redemption, new_payment_method="CARD"
    )
    session_id = f"cs_test_{uuid.uuid4().hex[:16]}"
    await redemptions_service.attach_stripe_checkout_session(db, redemption=redemption, session_id=session_id)

    payload = _checkout_session_completed_event(session_id=session_id, kind="invoice_redemption", redemption_id=redemption.id)
    sig_header = _sign(payload)

    await payments_service.handle_webhook_event(
        db, organization_id=organization_id, payload=payload, sig_header=sig_header
    )

    refreshed = await redemptions_service.get_org_scoped(db, organization_id=organization_id, redemption_id=redemption.id)
    assert refreshed.status == "CREDITED"


@pytest.mark.asyncio
async def test_webhook_rejects_a_bad_signature(db, organization_id):
    await _configure_stripe(db, organization_id)
    payload = _checkout_session_completed_event(session_id="cs_test_doesnotmatter", kind="order")
    bad_sig = _sign(payload, secret="whsec_wrong_secret")

    with pytest.raises(payments_service.WebhookVerificationError):
        await payments_service.handle_webhook_event(
            db, organization_id=organization_id, payload=payload, sig_header=bad_sig
        )
