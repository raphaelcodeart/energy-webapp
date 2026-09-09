"""GET /accounting/mine -- the customer's own unified LialCash + real-money
movement feed (Session 29+). Exercises accounting/service.py::list_my_movements
directly: a WALLET row for a wallet-only ADMIN_CREDIT, a WALLET row (negative,
outgoing) plus an ORDER_PAYMENT row for a partial-credit bank-transfer order,
and confirms a fully-credit-covered order produces no ORDER_PAYMENT row (no
real money moved)."""

import uuid

import pytest

from app.core.security import hash_password
from app.domains.accounting import service as accounting_service
from app.domains.catalog import service as catalog_service
from app.domains.catalog.schemas import ProductCreate
from app.domains.orders import service as orders_service
from app.domains.organizations import service as organizations_service
from app.domains.organizations.schemas import OrganizationSettingsUpdate
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from app.domains.wallets import service as wallet_service


async def _configure_bank_transfer(db, organization_id):
    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702")
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


async def _make_product_version(db, organization_id, actor_user_id, *, price_cents=5000, discount_pct=20):
    product = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        payload=ProductCreate(
            code=f"ACC-{uuid.uuid4().hex[:6]}", customer_type="PRIVATE", category="DROPSHIPPING",
            name="Gadget Contabilità", base_price_cents=price_cents, credit_discount_percentage=discount_pct,
        ),
    )
    _, versions = await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=product.id)
    return versions[0]


@pytest.mark.asyncio
async def test_wallet_only_credit_produces_a_single_lialcash_row(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1500, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)

    assert len(movements) == 1
    assert movements[0]["kind"] == "WALLET"
    assert movements[0]["currency"] == "LIALCASH"
    assert movements[0]["amount_cents"] == 1500


@pytest.mark.asyncio
async def test_partial_credit_bank_transfer_order_produces_both_rows(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    version = await _make_product_version(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    order = await orders_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, product_version_id=version.id,
        credit_applied_cents=1000, actor_user_id=admin.id, require_otp_for_credit_spend=False,
    )
    await orders_service.confirm_payment(db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id)

    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)

    wallet_rows = [m for m in movements if m["kind"] == "WALLET"]
    order_rows = [m for m in movements if m["kind"] == "ORDER_PAYMENT"]

    # ADMIN_CREDIT (+1000) then PURCHASE_DEBIT (-1000, outgoing) on the wallet
    assert len(wallet_rows) == 2
    debit_row = next(m for m in wallet_rows if m["amount_cents"] < 0)
    assert debit_row["amount_cents"] == -1000
    assert debit_row["currency"] == "LIALCASH"
    assert debit_row["product_name"] == version.name
    assert debit_row["order_id"] == order.id

    # 5000 - 1000 credit = 4000 residual paid in real money via bank transfer
    assert len(order_rows) == 1
    assert order_rows[0]["currency"] == "EUR"
    assert order_rows[0]["amount_cents"] == 4000
    assert order_rows[0]["payment_method"] == "BANK_TRANSFER"
    assert order_rows[0]["product_name"] == version.name
    assert order_rows[0]["order_id"] == order.id


@pytest.mark.asyncio
async def test_fully_credit_covered_order_produces_no_order_payment_row(db, organization_id):
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
        credit_applied_cents=3000, actor_user_id=admin.id, require_otp_for_credit_spend=False,
    )
    assert order.status == "PAID"  # straight-to-paid shortcut, no confirm_payment call

    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)

    assert all(m["kind"] != "ORDER_PAYMENT" for m in movements)
    assert any(m["kind"] == "WALLET" and m["amount_cents"] == -3000 for m in movements)


@pytest.mark.asyncio
async def test_movements_are_sorted_newest_first_and_scoped_to_the_caller(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer_a = await _make_user_with_role(db, organization_id)
    customer_b = await _make_user_with_role(db, organization_id)

    wallet_a = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer_a.id)
    wallet_b = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer_b.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet_a.id, amount_cents=100, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet_a.id, amount_cents=200, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet_b.id, amount_cents=999, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer_a.id)

    assert len(movements) == 2
    assert all(m["amount_cents"] in (100, 200) for m in movements)
    assert movements[0]["created_at"] >= movements[1]["created_at"]
