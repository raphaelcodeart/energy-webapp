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
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from app.domains.wallets import service as wallet_service


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
