"""Partner-invoice cashback: a customer/promoter redeems part of what they
already paid an external energy partner (e.g. Eviso) as internal wallet
credit. Covers the full lifecycle (SUBMITTED -> PAYMENT_PENDING -> CREDITED,
and the REJECTED branch), the exactly-two-rows ledger write, and the
INTERNAL-category discount clamp on the catalog side of the same feature.
See docs/cashback-partner-invoices-plan.md."""

import uuid

import pytest

from app.core.security import hash_password
from app.domains.catalog import service as catalog_service
from app.domains.catalog.schemas import ProductCreate, ProductUpdate
from app.domains.invoice_redemptions import service as redemptions_service
from app.domains.organizations import service as organizations_service
from app.domains.organizations.schemas import OrganizationSettingsUpdate, PaymentSettingsUpdate
from app.domains.partners import service as partners_service
from app.domains.partners.schemas import PartnerCreate
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from app.domains.wallets import service as wallet_service


async def _configure_bank_transfer(db, organization_id):
    await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702")
    )


async def _configure_stripe(db, organization_id):
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


async def _make_partner(db, organization_id, *, name: str | None = None):
    return await partners_service.create_partner(
        db, organization_id=organization_id, payload=PartnerCreate(name=name or f"Partner {uuid.uuid4().hex[:6]}")
    )


@pytest.mark.asyncio
async def test_full_redemption_lifecycle_credits_wallet_in_two_rows(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

    redemption = await redemptions_service.submit_redemption(
        db, organization_id=organization_id, customer_user_id=customer.id, partner_id=partner.id,
        declared_amount_cents=10000, file_bytes=b"%PDF-1.4\nfake invoice", content_type="application/pdf",
        original_filename="bolletta.pdf",
    )
    assert redemption.status == "SUBMITTED"
    assert redemption.confirmed_amount_cents is None

    verified = await redemptions_service.verify(
        db, organization_id=organization_id, redemption_id=redemption.id, confirmed_amount_cents=10000,
        actor_user_id=admin.id,
    )
    assert verified.status == "PAYMENT_PENDING"
    assert verified.payment_reference_code is not None
    assert redemptions_service.payment_due_cents(verified.confirmed_amount_cents) == 300  # 3% of 10000

    wallet = await wallet_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer.id)
    assert wallet.balance_cents == 0

    credited = await redemptions_service.confirm_payment(
        db, organization_id=organization_id, redemption_id=redemption.id, actor_user_id=admin.id
    )
    assert credited.status == "CREDITED"

    wallet_after = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after.balance_cents == 10300  # 100% base + 3% bonus

    rows = await wallet_service.list_transactions_for_wallet(
        db, organization_id=organization_id, wallet_id=wallet_after.id
    )
    by_source = {r["source"]: r["amount_cents"] for r in rows}
    assert by_source == {"INVOICE_REDEMPTION_BASE": 10000, "INVOICE_REDEMPTION_BONUS": 300}
    assert all(r["reference_invoice_redemption_id"] == redemption.id for r in rows)


@pytest.mark.asyncio
async def test_confirm_payment_twice_does_not_double_credit(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

    redemption = await redemptions_service.submit_redemption(
        db, organization_id=organization_id, customer_user_id=customer.id, partner_id=partner.id,
        declared_amount_cents=5000, file_bytes=b"%PDF-1.4", content_type="application/pdf", original_filename="x.pdf",
    )
    await redemptions_service.verify(
        db, organization_id=organization_id, redemption_id=redemption.id, confirmed_amount_cents=5000,
        actor_user_id=admin.id,
    )
    await redemptions_service.confirm_payment(
        db, organization_id=organization_id, redemption_id=redemption.id, actor_user_id=admin.id
    )

    with pytest.raises(redemptions_service.InvalidRedemptionStateError):
        await redemptions_service.confirm_payment(
            db, organization_id=organization_id, redemption_id=redemption.id, actor_user_id=admin.id
        )

    wallet = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet.balance_cents == 5150  # unchanged by the rejected second call


@pytest.mark.asyncio
async def test_reject_from_submitted_never_touches_the_wallet(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

    redemption = await redemptions_service.submit_redemption(
        db, organization_id=organization_id, customer_user_id=customer.id, partner_id=partner.id,
        declared_amount_cents=2000, file_bytes=b"%PDF-1.4", content_type="application/pdf", original_filename="x.pdf",
    )
    rejected = await redemptions_service.reject(
        db, organization_id=organization_id, redemption_id=redemption.id, reason="Documento illeggibile",
        actor_user_id=admin.id,
    )
    assert rejected.status == "REJECTED"
    assert rejected.rejection_reason == "Documento illeggibile"

    with pytest.raises(redemptions_service.InvalidRedemptionStateError):
        await redemptions_service.verify(
            db, organization_id=organization_id, redemption_id=redemption.id, confirmed_amount_cents=2000,
            actor_user_id=admin.id,
        )

    existing_wallet = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert existing_wallet is None  # never even lazily created


@pytest.mark.asyncio
async def test_submit_rejects_unsupported_content_type_and_unknown_partner(db, organization_id):
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

    with pytest.raises(redemptions_service.RedemptionValidationError):
        await redemptions_service.submit_redemption(
            db, organization_id=organization_id, customer_user_id=customer.id, partner_id=partner.id,
            declared_amount_cents=1000, file_bytes=b"hello", content_type="text/plain", original_filename="x.txt",
        )

    with pytest.raises(redemptions_service.PartnerNotFoundError):
        await redemptions_service.submit_redemption(
            db, organization_id=organization_id, customer_user_id=customer.id, partner_id=uuid.uuid4(),
            declared_amount_cents=1000, file_bytes=b"%PDF-1.4", content_type="application/pdf", original_filename="x.pdf",
        )


@pytest.mark.asyncio
async def test_internal_category_forces_credit_discount_to_zero(db, organization_id):
    actor_user_id = (await _make_user_with_role(db, organization_id, role_code="ADMIN")).id

    product = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        payload=ProductCreate(
            code=f"TEST-{uuid.uuid4().hex[:6]}", customer_type="PRIVATE", category="INTERNAL",
            name="Bolletta Circolare", base_price_cents=1000, credit_discount_percentage=50,
        ),
    )
    versions = (await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=product.id))[1]
    assert versions[0].credit_discount_percentage == 0  # clamped despite requesting 50

    dropship = await catalog_service.create_product(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        payload=ProductCreate(
            code=f"TEST-{uuid.uuid4().hex[:6]}", customer_type="PRIVATE", category="DROPSHIPPING",
            name="Gadget", base_price_cents=2000, credit_discount_percentage=30,
        ),
    )
    dropship_versions = (await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=dropship.id))[1]
    assert dropship_versions[0].credit_discount_percentage == 30  # allowed for a non-INTERNAL category

    # Switching an existing product back to INTERNAL zeroes out its version(s).
    await catalog_service.update_product(
        db, organization_id=organization_id, product_id=dropship.id, actor_user_id=actor_user_id,
        payload=ProductUpdate(category="INTERNAL"),
    )
    reverted_versions = (await catalog_service.get_product_with_versions(db, organization_id=organization_id, product_id=dropship.id))[1]
    assert reverted_versions[0].credit_discount_percentage == 0


@pytest.mark.asyncio
async def test_verify_defaults_payment_method_to_bank_transfer(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

    redemption = await redemptions_service.submit_redemption(
        db, organization_id=organization_id, customer_user_id=customer.id, partner_id=partner.id,
        declared_amount_cents=10000, file_bytes=b"%PDF-1.4", content_type="application/pdf",
        original_filename="x.pdf",
    )
    verified = await redemptions_service.verify(
        db, organization_id=organization_id, redemption_id=redemption.id, confirmed_amount_cents=10000,
        actor_user_id=admin.id,
    )
    assert verified.payment_method == "BANK_TRANSFER"


@pytest.mark.asyncio
async def test_change_payment_method_switches_and_clears_stale_stripe_session(db, organization_id):
    await _configure_stripe(db, organization_id)
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

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
    redemption = await redemptions_service.attach_stripe_checkout_session(
        db, redemption=redemption, session_id=f"cs_test_{uuid.uuid4().hex}"
    )
    assert redemption.stripe_checkout_session_id is not None

    switched = await redemptions_service.change_payment_method(
        db, organization_id=organization_id, redemption=redemption, new_payment_method="BANK_TRANSFER"
    )
    assert switched.payment_method == "BANK_TRANSFER"
    assert switched.stripe_checkout_session_id is None


@pytest.mark.asyncio
async def test_change_payment_method_rejects_unavailable_method(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

    redemption = await redemptions_service.submit_redemption(
        db, organization_id=organization_id, customer_user_id=customer.id, partner_id=partner.id,
        declared_amount_cents=10000, file_bytes=b"%PDF-1.4", content_type="application/pdf",
        original_filename="x.pdf",
    )
    redemption = await redemptions_service.verify(
        db, organization_id=organization_id, redemption_id=redemption.id, confirmed_amount_cents=10000,
        actor_user_id=admin.id,
    )
    # Stripe is not configured -- switching to CARD must fail.
    with pytest.raises(redemptions_service.PaymentMethodNotAvailableError):
        await redemptions_service.change_payment_method(
            db, organization_id=organization_id, redemption=redemption, new_payment_method="CARD"
        )


@pytest.mark.asyncio
async def test_confirm_payment_refuses_a_card_redemption(db, organization_id):
    """"Conferma bonifico ricevuto" (the manual admin action) must never be
    usable to mint wallet credit for a CARD-selected redemption -- only
    mark_paid_via_stripe(), reached exclusively from the Stripe webhook, may
    do that. This is the anti-fraud invariant the whole feature exists to
    respect: an admin (or anyone who compromised an admin session) must
    never be able to mint free wallet credit without Stripe actually
    confirming a real charge."""
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

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

    with pytest.raises(redemptions_service.InvalidRedemptionStateError):
        await redemptions_service.confirm_payment(
            db, organization_id=organization_id, redemption_id=redemption.id, actor_user_id=admin.id
        )

    refreshed = await redemptions_service.get_org_scoped(db, organization_id=organization_id, redemption_id=redemption.id)
    assert refreshed.status == "PAYMENT_PENDING"
    wallet = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet is None  # no credit ever minted


@pytest.mark.asyncio
async def test_mark_paid_via_stripe_credits_wallet_and_is_idempotent_on_retry(db, organization_id):
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

    redemption = await redemptions_service.submit_redemption(
        db, organization_id=organization_id, customer_user_id=customer.id, partner_id=partner.id,
        declared_amount_cents=6000, file_bytes=b"%PDF-1.4", content_type="application/pdf",
        original_filename="x.pdf",
    )
    redemption = await redemptions_service.verify(
        db, organization_id=organization_id, redemption_id=redemption.id, confirmed_amount_cents=6000,
        actor_user_id=admin.id,
    )
    redemption = await redemptions_service.change_payment_method(
        db, organization_id=organization_id, redemption=redemption, new_payment_method="CARD"
    )
    redemption = await redemptions_service.attach_stripe_checkout_session(
        db, redemption=redemption, session_id=f"cs_test_{uuid.uuid4().hex}"
    )

    paid = await redemptions_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=redemption.stripe_checkout_session_id
    )
    assert paid.status == "CREDITED"
    assert paid.credited_by_user_id is None  # no human actor -- Stripe confirmed this

    wallet = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet.balance_cents == 6180  # 6000 base + 3% (180) bonus

    # Stripe retries webhook delivery -- a second call for the same session
    # must be a no-op, never a double credit.
    retried = await redemptions_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=redemption.stripe_checkout_session_id
    )
    assert retried.status == "CREDITED"
    wallet_after_retry = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer.id)
    assert wallet_after_retry.balance_cents == 6180


@pytest.mark.asyncio
async def test_upload_payment_proof_stores_it_and_rejects_for_card_method(db, organization_id):
    await _configure_bank_transfer(db, organization_id)
    await _configure_stripe(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

    redemption = await redemptions_service.submit_redemption(
        db, organization_id=organization_id, customer_user_id=customer.id, partner_id=partner.id,
        declared_amount_cents=10000, file_bytes=b"%PDF-1.4", content_type="application/pdf",
        original_filename="x.pdf",
    )
    redemption = await redemptions_service.verify(
        db, organization_id=organization_id, redemption_id=redemption.id, confirmed_amount_cents=10000,
        actor_user_id=admin.id,
    )
    assert redemption.payment_method == "BANK_TRANSFER"

    updated = await redemptions_service.upload_payment_proof(
        db, organization_id=organization_id, redemption=redemption, file_bytes=b"%PDF-1.4\nreceipt",
        content_type="application/pdf", original_filename="bonifico.pdf", actor_user_id=customer.id,
    )
    assert updated.payment_proof_uploaded_at is not None
    assert redemptions_service.presigned_payment_proof_url(updated)

    switched = await redemptions_service.change_payment_method(
        db, organization_id=organization_id, redemption=updated, new_payment_method="CARD"
    )
    with pytest.raises(redemptions_service.PaymentProofError):
        await redemptions_service.upload_payment_proof(
            db, organization_id=organization_id, redemption=switched, file_bytes=b"%PDF-1.4\nreceipt",
            content_type="application/pdf", original_filename="x.pdf", actor_user_id=customer.id,
        )


@pytest.mark.asyncio
async def test_submit_rejects_content_that_does_not_match_its_claimed_type(db, organization_id):
    """A file claiming to be a PDF but whose bytes don't start with the real
    PDF magic signature must be rejected -- the client-supplied Content-Type
    header alone is not trusted (see core/storage.py::_verify_magic_bytes)."""
    customer = await _make_user_with_role(db, organization_id)
    partner = await _make_partner(db, organization_id)

    with pytest.raises(redemptions_service.RedemptionValidationError):
        await redemptions_service.submit_redemption(
            db, organization_id=organization_id, customer_user_id=customer.id, partner_id=partner.id,
            declared_amount_cents=1000, file_bytes=b"<html>not a pdf</html>", content_type="application/pdf",
            original_filename="x.pdf",
        )
