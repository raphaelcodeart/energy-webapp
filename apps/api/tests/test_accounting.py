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


@pytest.mark.asyncio
async def test_invoice_redemption_credit_rows_carry_the_redemption_id_and_partner_name(db, organization_id):
    """Bonus/base cashback credited from a partner-invoice redemption must be
    traceable back to that redemption -- distinct from order_id, a
    different domain entirely -- with the partner name filling the same
    "what is this about" slot product_name does for an order (see
    accounting/service.py::list_my_movements)."""
    from app.domains.invoice_redemptions import service as redemptions_service
    from app.domains.partners import service as partners_service
    from app.domains.partners.schemas import PartnerCreate

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
    await redemptions_service.confirm_payment(
        db, organization_id=organization_id, redemption_id=redemption.id, actor_user_id=admin.id
    )

    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)

    base_row = next(m for m in movements if m["source"] == "INVOICE_REDEMPTION_BASE")
    bonus_row = next(m for m in movements if m["source"] == "INVOICE_REDEMPTION_BONUS")
    for row in (base_row, bonus_row):
        assert row["invoice_redemption_id"] == redemption.id
        assert row["order_id"] is None
        assert row["product_name"] == partner.name

    # The real-money leg -- the 5% fee actually paid (bank transfer here) to
    # unlock the two LialCash credit rows above. Must be linked to the exact
    # same redemption id, in EUR, never confused with the LialCash rows.
    payment_row = next(m for m in movements if m["kind"] == "REDEMPTION_PAYMENT")
    assert payment_row["invoice_redemption_id"] == redemption.id
    assert payment_row["currency"] == "EUR"
    assert payment_row["amount_cents"] == 500  # 5% of 10000
    assert payment_row["payment_method"] == "BANK_TRANSFER"
    assert payment_row["product_name"] == partner.name
    assert payment_row["amount_cents"] > 0  # a payment is never negative


@pytest.mark.asyncio
async def test_admin_can_see_and_filter_every_customers_movements(db, organization_id):
    """GET /accounting/admin (list_all_movements) -- the whole org's ledger
    in one call, and scoped down to a single customer via customer_user_id."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer_a = await _make_user_with_role(db, organization_id)
    customer_b = await _make_user_with_role(db, organization_id)

    wallet_a = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer_a.id)
    wallet_b = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer_b.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet_a.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet_b.id, amount_cents=2000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )

    all_movements = await accounting_service.list_all_movements(db, organization_id=organization_id)
    amounts_by_customer = {}
    for m in all_movements:
        if m["customer_user_id"] in (customer_a.id, customer_b.id):
            amounts_by_customer.setdefault(m["customer_user_id"], []).append(m["amount_cents"])
    assert amounts_by_customer[customer_a.id] == [1000]
    assert amounts_by_customer[customer_b.id] == [2000]

    filtered = await accounting_service.list_all_movements(
        db, organization_id=organization_id, customer_user_id=customer_a.id
    )
    assert len(filtered) == 1
    assert filtered[0]["amount_cents"] == 1000
    assert filtered[0]["customer_user_id"] == customer_a.id


@pytest.mark.asyncio
async def test_imported_product_order_is_unified_with_regular_orders(db, organization_id):
    """A PURCHASE_DEBIT/ORDER_PAYMENT pair for the parallel "Acquisti
    LialEnergy" imported-products plugin (Session 34) must show up
    identically to a regular order -- same order_id field (populated from
    reference_imported_order_id, not a separate one), same kinds -- since
    the two tables are meant to be indistinguishable everywhere except the
    product-catalog admin screen (see imported_products/models.py)."""
    from app.domains.imported_products import service as imported_products_service

    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    provider = await imported_products_service.create_provider(
        db, organization_id=organization_id, actor_user_id=admin.id,
        provider_type="ALIEXPRESS", name="Test Provider", base_url=None, api_key=None, enabled=True,
    )
    product = await imported_products_service.create_imported_product(
        db, organization_id=organization_id, actor_user_id=admin.id, provider_id=provider.id,
        external_id=None, external_url=None, name="Gadget Importato", description="",
        image_url=None, price_cents=5000, credit_discount_percentage=20, status="ACTIVE",
    )

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    await wallet_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=1000, type_="ADMIN_CREDIT",
        actor_user_id=admin.id, idempotency_key=str(uuid.uuid4()),
    )
    order = await imported_products_service.create_order(
        db, organization_id=organization_id, customer_user_id=customer.id, imported_product_id=product.id,
        credit_applied_cents=1000, actor_user_id=admin.id, require_otp_for_credit_spend=False,
    )
    await imported_products_service.confirm_payment(
        db, organization_id=organization_id, order_id=order.id, actor_user_id=admin.id
    )

    movements = await accounting_service.list_my_movements(db, organization_id=organization_id, user_id=customer.id)

    debit_row = next(m for m in movements if m["kind"] == "WALLET" and m["amount_cents"] < 0)
    assert debit_row["order_id"] == order.id
    assert debit_row["product_name"] == product.name

    payment_row = next(m for m in movements if m["kind"] == "ORDER_PAYMENT")
    assert payment_row["order_id"] == order.id
    assert payment_row["amount_cents"] == 4000
    assert payment_row["product_name"] == product.name
