"""Session 34's "Acquisti LialEnergy" plugin -- a parallel catalog/order
system (see imported_products/models.py) for products sourced from an
external provider (AliExpress today), never mixed into catalog.products,
that a customer can partly/fully pay with wallet LialCash but which never
generates cashback of its own. Covers provider/product CRUD, the credit-cap
+ OTP self-checkout path (mirroring test_orders.py), cancellation refunding
via REVERSAL, and the wallet ledger's reference_imported_order_id."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import hash_otp_code, hash_password
from app.domains.auth import service as auth_service
from app.domains.auth.models import OtpCode
from app.domains.imported_products import service as imported_products_service
from app.domains.organizations import service as organizations_service
from app.domains.organizations.schemas import OrganizationSettingsUpdate
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from app.domains.wallets import service as wallet_service

VALID_OTP_CODE = "111222"


async def _seed_credit_spend_otp(db, user_id):
    db.add(
        OtpCode(
            user_id=user_id,
            purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE,
            code_hash=hash_otp_code(VALID_OTP_CODE),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    await db.commit()


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


async def _make_imported_product(db, organization_id, actor_user_id, *, price_cents=5000, discount_pct=20):
    provider = await imported_products_service.create_provider(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        provider_type="ALIEXPRESS", name="AliExpress IT", base_url=None, api_key="secret-key-1234", enabled=True,
    )
    product = await imported_products_service.create_imported_product(
        db, organization_id=organization_id, actor_user_id=actor_user_id, provider_id=provider.id,
        external_id=None, external_url=None, name="Power Bank importato", description="",
        image_url=None, price_cents=price_cents, credit_discount_percentage=discount_pct, status="ACTIVE",
    )
    return provider, product


@pytest.mark.asyncio
async def test_provider_api_key_is_masked_in_the_read_dict(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    provider = await imported_products_service.create_provider(
        db, organization_id=organization_id, actor_user_id=admin.id,
        provider_type="ALIEXPRESS", name="AliExpress IT", base_url="https://api.example.com",
        api_key="super-secret-abcd1234", enabled=True,
    )
    read = imported_products_service.to_provider_read_dict(provider)
    assert read["api_key_configured"] is True
    assert read["api_key_last4"] == "1234"
    assert "api_key" not in read


@pytest.mark.asyncio
async def test_partial_credit_debits_wallet_and_leaves_residual_awaiting_payment(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    quote = await imported_products_service.get_quote(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id
    )
    assert quote["max_creditable_cents"] == 1000  # 20% of 5000
    assert quote["customer_wallet_balance_cents"] == 2000

    await _seed_credit_spend_otp(db, customer.id)
    order = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=1000, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
    )
    assert order.status == "AWAITING_PAYMENT"
    assert order.amount_cents == 5000
    assert order.credit_applied_cents == 1000
    assert order.credit_debit_transaction_id is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 1000  # 2000 - 1000

    txn = await db.get(wallet_service.WalletTransaction, order.credit_debit_transaction_id)
    assert txn.reference_imported_order_id == order.id
    assert txn.reference_order_id is None

    confirmed = await imported_products_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )
    assert confirmed.status == "PAID"


@pytest.mark.asyncio
async def test_credit_covering_full_amount_skips_straight_to_paid(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=3000, discount_pct=100)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=3000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    await _seed_credit_spend_otp(db, customer.id)
    order = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=3000, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
    )
    assert order.status == "PAID"
    assert order.paid_at is not None

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 0


@pytest.mark.asyncio
async def test_credit_over_cap_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    await _seed_credit_spend_otp(db, customer.id)
    with pytest.raises(imported_products_service.InvalidCreditAmountError):
        await imported_products_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
            credit_applied_cents=1001, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,  # cap is 1000
        )


@pytest.mark.asyncio
async def test_spending_credit_without_a_valid_otp_is_rejected(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    with pytest.raises(imported_products_service.InvalidOtpError):
        await imported_products_service.create_order(
            db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
            credit_applied_cents=500, actor_user_id=customer.id, otp_code="000000",
        )


@pytest.mark.asyncio
async def test_cancel_refunds_the_exact_credit_debit_via_reversal(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=5000, discount_pct=20)

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    await _seed_credit_spend_otp(db, customer.id)
    order = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=1000, actor_user_id=customer.id, otp_code=VALID_OTP_CODE,
    )
    wallet_mid = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_mid.balance_cents == 1000

    cancelled = await imported_products_service.cancel_order(
        db, organization_id=organization_id, order_id=order.id, reason="Cliente ha cambiato idea", actor_user_id=admin.id,
    )
    assert cancelled.status == "CANCELLED"

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 2000  # fully refunded


@pytest.mark.asyncio
async def test_product_never_offers_cashback_fields(db, organization_id):
    """No cashback_requested/cashback_surcharge_cents exist on this order at
    all (see models.py::ImportedProductOrder's docstring) -- to_read_dict's
    output shape is the closest thing to an enforced contract here."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    await _configure_bank_transfer(db, organization_id)
    _provider, product = await _make_imported_product(db, organization_id, admin.id, price_cents=5000, discount_pct=0)

    order = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=0, actor_user_id=customer.id,
    )
    row = await imported_products_service.to_read_dict(db, order)
    assert "cashback_requested" not in row
    assert "cashback_surcharge_cents" not in row
    assert row["residual_amount_cents"] == 5000
