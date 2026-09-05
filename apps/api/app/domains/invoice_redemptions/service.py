import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.storage import UploadValidationError
from app.core.storage import generate_presigned_document_url as storage_presign_document
from app.core.storage import upload_document as storage_upload_document
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.invoice_redemptions.models import (
    ALLOWED_INVOICE_CONTENT_TYPES,
    CASHBACK_PERCENTAGE,
    MAX_INVOICE_BYTES,
    InvoiceRedemption,
)
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.partners.models import Partner
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service

PRESIGNED_URL_TTL_SECONDS = 300


class InvoiceRedemptionError(Exception):
    pass


class PartnerNotFoundError(InvoiceRedemptionError):
    pass


class InvalidRedemptionStateError(InvoiceRedemptionError):
    pass


class RedemptionValidationError(InvoiceRedemptionError):
    pass


def payment_due_cents(confirmed_amount_cents: int | None) -> int | None:
    if confirmed_amount_cents is None:
        return None
    return round(confirmed_amount_cents * CASHBACK_PERCENTAGE / 100)


async def _resolve_display_name(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Single-user version of wallets/service.py::_resolve_display_names --
    duplicated rather than imported since that one is a private, batch-only
    helper local to the wallets domain; same lookup order (agent, then
    customer, then email) for the same reason: a redeemer may be a promoter,
    a customer, or both."""
    agent = (
        await db.execute(
            select(AgentProfile.display_name).where(
                AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if agent:
        return agent

    customer = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if customer is not None:
        profile = await db.get(CustomerProfile, customer.id)
        company = await db.get(Company, customer.id)
        name = display_name_for(customer.kind, profile, company)
        if name != "—":
            return name

    user = await db.get(User, user_id)
    return user.email if user else "—"


def _generate_payment_reference_code() -> str:
    """Short, human-typeable code for the bank transfer's causale -- lets an
    admin match an incoming wire to this exact redemption without relying on
    a euro amount that several customers could share on the same day.
    Uniqueness is a DB constraint (uq via the model's unique=True), not
    guessed here -- same division of responsibility as
    network/service.py::_generate_promoter_code."""
    return f"RIS-{secrets.token_hex(3).upper()}"


async def to_read_dict(db: AsyncSession, redemption: InvoiceRedemption) -> dict:
    partner = await db.get(Partner, redemption.partner_id)
    customer_name = await _resolve_display_name(
        db, organization_id=redemption.organization_id, user_id=redemption.customer_user_id
    )
    return {
        "id": redemption.id,
        "partner_id": redemption.partner_id,
        "partner_name": partner.name if partner else "—",
        "customer_user_id": redemption.customer_user_id,
        "customer_display_name": customer_name,
        "original_filename": redemption.original_filename,
        "content_type": redemption.content_type,
        "declared_amount_cents": redemption.declared_amount_cents,
        "confirmed_amount_cents": redemption.confirmed_amount_cents,
        "payment_due_cents": payment_due_cents(redemption.confirmed_amount_cents),
        "payment_reference_code": redemption.payment_reference_code,
        "status": redemption.status,
        "rejection_reason": redemption.rejection_reason,
        "created_at": redemption.created_at,
        "verified_at": redemption.verified_at,
        "credited_at": redemption.credited_at,
    }


async def hydrate(db: AsyncSession, redemptions: list[InvoiceRedemption]) -> list[dict]:
    return [await to_read_dict(db, r) for r in redemptions]


async def submit_redemption(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    partner_id: uuid.UUID,
    declared_amount_cents: int,
    file_bytes: bytes,
    content_type: str,
    original_filename: str,
) -> InvoiceRedemption:
    partner = await db.get(Partner, partner_id)
    if partner is None or partner.organization_id != organization_id or not partner.is_active:
        raise PartnerNotFoundError("Partner not found")
    if declared_amount_cents <= 0:
        raise RedemptionValidationError("declared_amount_cents must be positive")
    if content_type not in ALLOWED_INVOICE_CONTENT_TYPES:
        raise RedemptionValidationError(f"Unsupported content type: {content_type}")
    if len(file_bytes) > MAX_INVOICE_BYTES:
        raise RedemptionValidationError("File too large (max 15 MB)")

    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type, key_prefix=f"invoice-redemptions/{customer_user_id}"
        )
    except UploadValidationError as exc:
        raise RedemptionValidationError(str(exc)) from exc

    redemption = InvoiceRedemption(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        partner_id=partner_id,
        storage_key=storage_key,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=len(file_bytes),
        declared_amount_cents=declared_amount_cents,
        status="SUBMITTED",
    )
    db.add(redemption)
    await db.commit()
    await db.refresh(redemption)
    return redemption


async def list_mine(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[InvoiceRedemption]:
    stmt = (
        select(InvoiceRedemption)
        .where(InvoiceRedemption.organization_id == organization_id, InvoiceRedemption.customer_user_id == user_id)
        .order_by(InvoiceRedemption.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, redemption_id: uuid.UUID
) -> InvoiceRedemption | None:
    redemption = await db.get(InvoiceRedemption, redemption_id)
    if redemption is None or redemption.organization_id != organization_id:
        return None
    if redemption.customer_user_id != user_id:
        return None
    return redemption


async def get_org_scoped(
    db: AsyncSession, *, organization_id: uuid.UUID, redemption_id: uuid.UUID
) -> InvoiceRedemption | None:
    redemption = await db.get(InvoiceRedemption, redemption_id)
    if redemption is None or redemption.organization_id != organization_id:
        return None
    return redemption


async def list_admin_queue(
    db: AsyncSession, *, organization_id: uuid.UUID, status_filter: str | None = None
) -> list[InvoiceRedemption]:
    stmt = select(InvoiceRedemption).where(InvoiceRedemption.organization_id == organization_id)
    if status_filter:
        stmt = stmt.where(InvoiceRedemption.status == status_filter)
    stmt = stmt.order_by(InvoiceRedemption.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


def presigned_photo_url(redemption: InvoiceRedemption) -> str:
    return storage_presign_document(storage_key=redemption.storage_key, expires_in_seconds=PRESIGNED_URL_TTL_SECONDS)


async def verify(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    redemption_id: uuid.UUID,
    confirmed_amount_cents: int,
    actor_user_id: uuid.UUID,
) -> InvoiceRedemption:
    """The single admin action that both confirms the real amount AND opens
    the payment window -- see docs/cashback-partner-invoices-plan.md, there
    is no separate resting "verified but payment not yet requested" state."""
    redemption = await get_org_scoped(db, organization_id=organization_id, redemption_id=redemption_id)
    if redemption is None:
        raise InvoiceRedemptionError("Invoice redemption not found")
    if redemption.status != "SUBMITTED":
        raise InvalidRedemptionStateError(f"Cannot verify a redemption in status {redemption.status}")

    redemption.confirmed_amount_cents = confirmed_amount_cents
    redemption.payment_reference_code = _generate_payment_reference_code()
    redemption.status = "PAYMENT_PENDING"
    redemption.verified_by_user_id = actor_user_id
    redemption.verified_at = utcnow()

    # confirmed_amount_cents is a required int here (not the nullable field on
    # the model) -- compute directly rather than through payment_due_cents(),
    # whose Optional signature exists for reading an unverified redemption.
    due = round(confirmed_amount_cents * CASHBACK_PERCENTAGE / 100)
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=redemption.customer_user_id,
        type_="INVOICE_REDEMPTION_VERIFIED", entity_type="invoice_redemption", entity_id=redemption.id,
        title=f"Fattura verificata: paga {due / 100:.2f} EUR per riscattare {confirmed_amount_cents / 100:.2f} EUR",
        body=f"Codice da inserire nella causale del bonifico: {redemption.payment_reference_code}",
    )
    await db.commit()
    await db.refresh(redemption)
    return redemption


async def reject(
    db: AsyncSession, *, organization_id: uuid.UUID, redemption_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> InvoiceRedemption:
    redemption = await get_org_scoped(db, organization_id=organization_id, redemption_id=redemption_id)
    if redemption is None:
        raise InvoiceRedemptionError("Invoice redemption not found")
    if redemption.status not in ("SUBMITTED", "PAYMENT_PENDING"):
        raise InvalidRedemptionStateError(f"Cannot reject a redemption in status {redemption.status}")

    redemption.status = "REJECTED"
    redemption.rejection_reason = reason

    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=redemption.customer_user_id,
        type_="INVOICE_REDEMPTION_REJECTED", entity_type="invoice_redemption", entity_id=redemption.id,
        title="La tua richiesta di riscatto fattura è stata rifiutata", body=reason,
    )
    await db.commit()
    await db.refresh(redemption)
    return redemption


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, redemption_id: uuid.UUID, actor_user_id: uuid.UUID
) -> InvoiceRedemption:
    """Admin confirms the 3% bank transfer arrived -- the only place a real,
    external money inflow turns into wallet credit for this flow. Writes
    TWO wallet_transactions (base + bonus), never one combined row, so the
    ledger always shows the split explicitly (see
    docs/cashback-partner-invoices-plan.md). Idempotency keys are derived
    from the redemption's own id, not client-supplied -- the status guard
    above already makes this action exactly-once per redemption, a retried
    call after a partial failure re-hits the same two keys and no-ops."""
    redemption = await get_org_scoped(db, organization_id=organization_id, redemption_id=redemption_id)
    if redemption is None:
        raise InvoiceRedemptionError("Invoice redemption not found")
    if redemption.status != "PAYMENT_PENDING":
        raise InvalidRedemptionStateError(f"Cannot confirm payment for a redemption in status {redemption.status}")
    assert redemption.confirmed_amount_cents is not None  # guaranteed by verify()

    partner = await db.get(Partner, redemption.partner_id)
    partner_name = partner.name if partner else "partner"
    bonus_cents = payment_due_cents(redemption.confirmed_amount_cents)
    assert bonus_cents is not None

    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=redemption.customer_user_id
    )
    await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=redemption.confirmed_amount_cents,
        type_="ADMIN_CREDIT", actor_user_id=actor_user_id, source="INVOICE_REDEMPTION_BASE",
        reference_invoice_redemption_id=redemption.id,
        note=f"Riscatto fattura {partner_name}",
        idempotency_key=f"invoice-redemption:{redemption.id}:base",
    )
    await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=bonus_cents,
        type_="ADMIN_CREDIT", actor_user_id=actor_user_id, source="INVOICE_REDEMPTION_BONUS",
        reference_invoice_redemption_id=redemption.id,
        note=f"Bonus {CASHBACK_PERCENTAGE}% riscatto fattura {partner_name}",
        idempotency_key=f"invoice-redemption:{redemption.id}:bonus",
    )

    redemption.status = "CREDITED"
    redemption.credited_by_user_id = actor_user_id
    redemption.credited_at = utcnow()
    await db.commit()
    await db.refresh(redemption)
    return redemption
