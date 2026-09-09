"""DROPSHIPPING/PARTNER product purchases with an optional wallet-credit
discount (Phase 4 of the partner-invoice cashback project). Deliberately not
a Contract -- see orders/models.py. Covers the credit-cap enforcement, the
straight-to-PAID shortcut when credit covers 100%, cancellation refunding
the exact debit via a REVERSAL, and INTERNAL products being rejected."""

import uuid

import pytest

from app.core.security import hash_password
from app.domains.catalog import service as catalog_service
from app.domains.catalog.schemas import ProductCreate
from app.domains.orders import service as orders_service
from app.domains.organizations import service as organizations_service
from app.domains.organizations.schemas import OrganizationSettingsUpdate, PaymentSettingsUpdate
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from app.domains.wallets import service as wallet_service


async def _configure_bank_transfer(db, organization_id):
    """Bank transfer (and card) are both gated off by default (Session 26) --
    tests exercising a residual paid by BANK_TRANSFER (the create_order
    default) need it explicitly configured first, same as a real deployment
    would via the admin settings panel."""
    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702")
    )


async def _configure_stripe(db, organization_id):
    """CARD as a payment_method requires both Stripe keys configured (see
    orders/service.py::create_order's availability check) -- same pattern as
    test_card_requires_both_stripe_keys_configured above, factored out for
    tests that only need it as setup, not as the thing under test."""
    await organizations_service.update_payment_settings(
        db, organization_id=organization_id,
        payload=PaymentSettingsUpdate(stripe_publishable_key="pk_test_abc", stripe_secret_key="sk_test_xyz"),
    )


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


async def _make_product_version(db, organization_id, actor_user_id, *, category="DROPSHIPPING", price_cents=5000, discount_pct=20):
    product = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        payload=ProductCreate(
            code=f"ORD-{uuid.uuid4().hex[:6]}", customer_type="PRIVATE", category=category,
            name="Gadget", base_price_cents=price_cents, credit_discount_percentage=discount_pct,
        ),
    )
    _, versions = await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=product.id)
    return versions[0]


@pytest.mark.asyncio
async def test_partial_credit_debits_wallet_and_leaves_residual_awaiting_payment(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    quote = await orders_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id
    )
    assert quote["max_creditable_cents"] == 1000  # 20% of 5000
    assert quote["customer_wallet_balance_cents"] == 2000

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=admin.id,
    )
    assert order.status == "AWAITING_PAYMENT"
    assert order.amount_cents == 5000
    assert order.credit_applied_cents == 1000
    assert order.credit_debit_transaction_id is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 1000  # 2000 - 1000

    confirmed = await orders_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert confirmed.status == "PAID"


@pytest.mark.asyncio
async def test_credit_covering_full_amount_skips_straight_to_paid(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=3000, discount_pct=100)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=3000, actor_user_id=admin.id,
    )
    assert order.status == "PAID"  # no bank transfer needed
    assert order.paid_at is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 0


@pytest.mark.asyncio
async def test_credit_over_cap_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    with pytest.raises(orders_service.InvalidCreditAmountError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=1001, actor_user_id=admin.id,  # cap is 1000
        )


@pytest.mark.asyncio
async def test_credit_exceeding_balance_raises_and_creates_no_order(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=50)
    # customer has no wallet / zero balance -- cap (2500) exceeds it

    with pytest.raises(wallet_service.InsufficientBalanceError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=2500, actor_user_id=admin.id,
        )

    orders = await orders_service.list_orders(db, organization_id=organization_id)
    assert all(o.customer_user_id != customer.id for o in orders)


@pytest.mark.asyncio
async def test_cancel_refunds_the_exact_credit_debit(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=10000, discount_pct=10)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=admin.id,
    )
    mid_wallet = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert mid_wallet.balance_cents == 0

    cancelled = await orders_service.cancel_order(
        db, organization_id=organization_id, order_id=order.id, reason="Prodotto esaurito", actor_user_id=admin.id
    )
    assert cancelled.status == "CANCELLED"

    refunded_wallet = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert refunded_wallet.balance_cents == 1000  # fully refunded

    with pytest.raises(orders_service.InvalidOrderStateError):
        await orders_service.cancel_order(
            db, organization_id=organization_id, order_id=order.id, reason="again", actor_user_id=admin.id
        )
    with pytest.raises(orders_service.InvalidOrderStateError):
        await orders_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)


@pytest.mark.asyncio
async def test_internal_category_product_is_not_orderable(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, category="INTERNAL", price_cents=3000, discount_pct=0)

    with pytest.raises(orders_service.ProductNotEligibleError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id,
        )


@pytest.mark.asyncio
async def test_unconfigured_payment_method_is_rejected_and_creates_no_order(db, organization_id):
    """Session 26: bank transfer and card are both off by default (an admin
    must configure an IBAN / Stripe keys first) -- this is the server-side
    half of "the button isn't even clickable if it's not configured"."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)
    # deliberately NOT calling _configure_bank_transfer -- nothing is set up

    with pytest.raises(orders_service.PaymentMethodNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id, payment_method="BANK_TRANSFER",
        )
    with pytest.raises(orders_service.PaymentMethodNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id, payment_method="CARD",
        )

    orders = await orders_service.list_orders(db, organization_id=organization_id)
    assert all(o.customer_user_id != customer.id for o in orders)


@pytest.mark.asyncio
async def test_card_requires_both_stripe_keys_configured(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    # Only the publishable key set -- still not enough, both are required.
    await organizations_service.update_payment_settings(
        db, organization_id=organization_id, payload=PaymentSettingsUpdate(stripe_publishable_key="pk_test_abc")
    )
    with pytest.raises(orders_service.PaymentMethodNotAvailableError):
        await orders_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
            credit_applied_cents=0, actor_user_id=admin.id, payment_method="CARD",
        )

    await organizations_service.update_payment_settings(
        db, organization_id=organization_id, payload=PaymentSettingsUpdate(stripe_secret_key="sk_test_xyz")
    )
    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=admin.id, payment_method="CARD",
    )
    assert order.status == "AWAITING_PAYMENT"
    assert order.payment_method == "CARD"


@pytest.mark.asyncio
async def test_confirm_payment_refuses_a_card_order(db, organization_id):
    """"Conferma bonifico ricevuto" (the manual admin action) must never be
    usable to mark a CARD order paid -- only mark_paid_via_stripe(), reached
    exclusively from the Stripe webhook, may do that. Enforced server-side
    (not just hidden in admin-orders-panel.tsx), so an admin calling the API
    directly still can't shortcut Stripe's own confirmation."""
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=admin.id, payment_method="CARD",
    )

    with pytest.raises(orders_service.InvalidOrderStateError):
        await orders_service.confirm_payment(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
        )

    refreshed = await orders_service.get_org_scoped(db, organization_id=organization_id, order_id=order.id)
    assert refreshed.status == "AWAITING_PAYMENT"


@pytest.mark.asyncio
async def test_full_credit_ignores_unconfigured_payment_method(db, organization_id):
    """residual == 0 means nothing is ever actually charged, so an
    unavailable (or even invalid) payment_method must not block the order --
    it's stored but never acted upon."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=3000, discount_pct=100)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=3000, actor_user_id=admin.id, payment_method="CARD",  # unconfigured, irrelevant here
    )
    assert order.status == "PAID"


@pytest.mark.asyncio
async def test_create_order_notifies_staff_but_not_the_actor(db, organization_id):
    """New-order visibility for staff (task: "nuovo ordine -> notifica
    amministratore"), same STAFF_NOTIFY_ROLES convention as
    contracts/service.py::create_contract's CONTRACT_CREATED. The customer
    who placed it is excluded even though the order itself grants them no
    staff role (this only matters when an admin creates an order on a
    customer's behalf -- that admin shouldn't see their own action as a
    notification)."""
    from app.domains.notifications import service as notifications_service

    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    other_admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=admin.id,
    )

    actor_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=admin.id
    )
    assert not any(n.type == "ORDER_CREATED" for n in actor_notifications)

    other_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=other_admin.id
    )
    assert any(n.type == "ORDER_CREATED" for n in other_notifications)


@pytest.mark.asyncio
async def test_confirm_payment_notifies_staff_and_sends_paid_email(db, organization_id):
    """Bank-transfer confirmation (task: "Rendi pagato") must notify staff
    and email the customer that payment is complete -- separate from the
    "ordine ricevuto" email sent at creation."""
    from unittest.mock import AsyncMock, patch

    from app.domains.notifications import service as notifications_service

    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    other_admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id,
    )

    with patch.object(orders_service, "_send_order_paid_email", new_callable=AsyncMock) as mock_email:
        confirmed = await orders_service.confirm_payment(
            db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
        )

    assert confirmed.status == "PAID"
    mock_email.assert_awaited_once()
    assert mock_email.call_args.kwargs["order"].id == order.id

    other_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=other_admin.id
    )
    assert any(n.type == "ORDER_PAID" for n in other_notifications)


@pytest.mark.asyncio
async def test_mark_paid_via_stripe_notifies_staff_and_sends_paid_email(db, organization_id):
    """The webhook path (payments/service.py::handle_webhook_event ->
    mark_paid_via_stripe) must produce the same staff notification and
    customer "payment completed" email as the bank-transfer path -- no
    admin action involved, Stripe alone triggers it."""
    from unittest.mock import AsyncMock, patch

    from app.domains.notifications import service as notifications_service

    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=6900, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD",
    )
    order = await orders_service.attach_stripe_checkout_session(db, order=order, session_id=f"cs_test_{uuid.uuid4().hex}")

    with patch.object(orders_service, "_send_order_paid_email", new_callable=AsyncMock) as mock_email:
        paid = await orders_service.mark_paid_via_stripe(
            db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
        )

    assert paid.status == "PAID"
    assert paid.paid_by_user_id is None  # no human actor -- Stripe confirmed it
    mock_email.assert_awaited_once()

    admin_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=admin.id
    )
    assert any(n.type == "ORDER_PAID" for n in admin_notifications)

    # A retried webhook delivery for the same (already-PAID) session must
    # stay a no-op -- no second email, no error.
    with patch.object(orders_service, "_send_order_paid_email", new_callable=AsyncMock) as mock_email_retry:
        await orders_service.mark_paid_via_stripe(
            db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
        )
    mock_email_retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_product_order_payment_never_touches_the_wallet(db, organization_id):
    """The wallet is credited ONLY by the invoice-redemption cashback flow
    (invoice_redemptions/service.py::confirm_payment) -- a normal product
    purchase, paid in full with no credit applied, must leave the customer's
    wallet completely untouched all the way through payment confirmation,
    whether that confirmation comes from an admin (bank transfer) or from
    Stripe (card)."""
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=10000, discount_pct=0)

    wallet_before = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_before.balance_cents == 0

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD",
    )
    order = await orders_service.attach_stripe_checkout_session(db, order=order, session_id=f"cs_test_{uuid.uuid4().hex}")
    paid = await orders_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=order.stripe_checkout_session_id
    )
    assert paid.status == "PAID"

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 0  # a 100 EUR product paid in full credits the wallet exactly 0 EUR


@pytest.mark.asyncio
async def test_change_payment_method_switches_and_clears_stale_stripe_session(db, organization_id):
    """Switching a CARD order to BANK_TRANSFER must clear
    stripe_checkout_session_id -- otherwise a late/retried webhook for the
    abandoned Stripe session could still mark this order paid off a card
    payment unrelated to the bank transfer the customer switched to."""
    await _configure_stripe(db, organization_id)
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD",
    )
    order = await orders_service.attach_stripe_checkout_session(db, order=order, session_id=f"cs_test_{uuid.uuid4().hex}")
    assert order.stripe_checkout_session_id is not None

    switched = await orders_service.change_payment_method(
        db, organization_id=organization_id, order=order, new_payment_method="BANK_TRANSFER"
    )
    assert switched.payment_method == "BANK_TRANSFER"
    assert switched.stripe_checkout_session_id is None

    # And back to CARD -- a fresh checkout-session request would attach a
    # new session id later; nothing to clear going the other direction.
    back_to_card = await orders_service.change_payment_method(
        db, organization_id=organization_id, order=switched, new_payment_method="CARD"
    )
    assert back_to_card.payment_method == "CARD"


@pytest.mark.asyncio
async def test_change_payment_method_rejects_once_paid(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=3000, discount_pct=100)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=3000, actor_user_id=customer.id,
    )
    assert order.status == "PAID"

    with pytest.raises(orders_service.InvalidOrderStateError):
        await orders_service.change_payment_method(
            db, organization_id=organization_id, order=order, new_payment_method="CARD"
        )


@pytest.mark.asyncio
async def test_change_payment_method_rejects_unavailable_method(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="BANK_TRANSFER",
    )
    # Stripe is not configured in this test -- switching to CARD must fail.
    with pytest.raises(orders_service.PaymentMethodNotAvailableError):
        await orders_service.change_payment_method(
            db, organization_id=organization_id, order=order, new_payment_method="CARD"
        )


@pytest.mark.asyncio
async def test_upload_payment_proof_stores_it_and_notifies_staff(db, organization_id):
    from app.domains.notifications import service as notifications_service

    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    other_admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="BANK_TRANSFER",
    )
    assert order.payment_proof_uploaded_at is None

    updated = await orders_service.upload_payment_proof(
        db, organization_id=organization_id, order=order, file_bytes=b"%PDF fake receipt",
        content_type="application/pdf", original_filename="bonifico.pdf", actor_user_id=customer.id,
    )
    assert updated.payment_proof_uploaded_at is not None
    assert updated.payment_proof_original_filename == "bonifico.pdf"

    url = orders_service.presigned_payment_proof_url(updated)
    assert url

    other_notifications = await notifications_service.list_my_notifications(
        db, organization_id=organization_id, user_id=other_admin.id
    )
    assert any(n.type == "ORDER_PAYMENT_PROOF_UPLOADED" for n in other_notifications)


@pytest.mark.asyncio
async def test_upload_payment_proof_rejects_a_card_order(db, organization_id):
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=0, actor_user_id=customer.id, payment_method="CARD",
    )
    with pytest.raises(orders_service.PaymentProofError):
        await orders_service.upload_payment_proof(
            db, organization_id=organization_id, order=order, file_bytes=b"%PDF fake",
            content_type="application/pdf", original_filename="x.pdf", actor_user_id=customer.id,
        )
