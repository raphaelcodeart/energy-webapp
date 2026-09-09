import logging
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.email import EmailNotConfiguredError, send_html_email
from app.core.email_templates import render_email
from app.core.storage import UploadValidationError
from app.core.storage import generate_presigned_document_url as storage_presign_document
from app.core.storage import upload_document as storage_upload_document
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.invoice_redemptions.models import (
    ALLOWED_INVOICE_CONTENT_TYPES,
    CASHBACK_PERCENTAGE,
    INVOICE_REDEMPTION_PAYMENT_METHODS,
    MAX_INVOICE_BYTES,
    InvoiceRedemption,
)
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.orders.service import get_available_payment_methods
from app.domains.partners.models import Partner
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service

logger = logging.getLogger(__name__)

PRESIGNED_URL_TTL_SECONDS = 300
PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS = 300


class InvoiceRedemptionError(Exception):
    pass


class PartnerNotFoundError(InvoiceRedemptionError):
    pass


class InvalidRedemptionStateError(InvoiceRedemptionError):
    pass


class RedemptionValidationError(InvoiceRedemptionError):
    pass


class InvalidPaymentMethodError(InvoiceRedemptionError):
    pass


class PaymentMethodNotAvailableError(InvoiceRedemptionError):
    pass


class PaymentProofError(InvoiceRedemptionError):
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
        "payment_method": redemption.payment_method,
        "stripe_checkout_session_id": redemption.stripe_checkout_session_id,
        "payment_proof_uploaded_at": redemption.payment_proof_uploaded_at,
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


def presigned_payment_proof_url(redemption: InvoiceRedemption) -> str:
    assert redemption.payment_proof_storage_key is not None  # guaranteed by the router's own check
    return storage_presign_document(
        storage_key=redemption.payment_proof_storage_key, expires_in_seconds=PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS
    )


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
    is no separate resting "verified but payment not yet requested" state.
    payment_method starts at BANK_TRANSFER (the original, only-ever-existed
    behavior); the customer can switch to CARD via change_payment_method()
    below while still PAYMENT_PENDING."""
    redemption = await get_org_scoped(db, organization_id=organization_id, redemption_id=redemption_id)
    if redemption is None:
        raise InvoiceRedemptionError("Invoice redemption not found")
    if redemption.status != "SUBMITTED":
        raise InvalidRedemptionStateError(f"Cannot verify a redemption in status {redemption.status}")

    redemption.confirmed_amount_cents = confirmed_amount_cents
    redemption.payment_reference_code = _generate_payment_reference_code()
    redemption.payment_method = "BANK_TRANSFER"
    redemption.status = "PAYMENT_PENDING"
    redemption.verified_by_user_id = actor_user_id
    redemption.verified_at = utcnow()

    # confirmed_amount_cents is a required int here (not the nullable field on
    # the model) -- compute directly rather than through payment_due_cents(),
    # whose Optional signature exists for reading an unverified redemption.
    due = round(confirmed_amount_cents * CASHBACK_PERCENTAGE / 100)
    total_after_payment = confirmed_amount_cents + due
    partner = await db.get(Partner, redemption.partner_id)
    partner_name = partner.name if partner else "il partner"

    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=redemption.customer_user_id,
        type_="INVOICE_REDEMPTION_VERIFIED", entity_type="invoice_redemption", entity_id=redemption.id,
        title=f"Fattura verificata: paga {due / 100:.2f} EUR per riscattare {confirmed_amount_cents / 100:.2f} EUR",
        body=f"Codice da inserire nella causale del bonifico: {redemption.payment_reference_code}",
    )
    await db.commit()
    await db.refresh(redemption)

    customer_user = await db.get(User, redemption.customer_user_id)
    if customer_user is not None:
        html = render_email(
            preheader="La tua fattura è stata verificata: puoi completare il riscatto",
            heading="Fattura verificata",
            body_html=(
                f"<p>La fattura {partner_name} da te caricata (importo dichiarato "
                f"{redemption.declared_amount_cents / 100:.2f} &euro;) è stata verificata da un amministratore "
                f"per un importo di <strong>{confirmed_amount_cents / 100:.2f} &euro;</strong>.</p>"
                f"<p>Per riscattare questo importo come LialCash sul tuo wallet devi completare il pagamento "
                f"del {CASHBACK_PERCENTAGE}% richiesto:</p>"
                f"<p style=\"font-size:22px; font-weight:700; color:#f97316; margin:20px 0;\">"
                f"{due / 100:.2f} &euro;</p>"
                f"<p>Puoi pagare subito con carta, oppure con bonifico bancario indicando nella causale il "
                f"codice <strong>{redemption.payment_reference_code}</strong> (necessario per farci abbinare "
                f"il tuo bonifico a questa richiesta).</p>"
                f"<p>Una volta ricevuto il pagamento (automaticamente per la carta, dopo verifica per il "
                f"bonifico) riceverai <strong>{total_after_payment / 100:.2f} LialCash</strong> "
                f"({confirmed_amount_cents / 100:.2f} + {due / 100:.2f} di bonus {CASHBACK_PERCENTAGE}%) "
                "sul tuo wallet Lial Energy.</p>"
            ),
            cta_label="Vai al riscatto cashback",
            cta_url=f"{get_settings().public_app_base_url}/customer",
        )
        try:
            send_html_email(
                to=customer_user.email,
                subject="Fattura verificata: completa il riscatto - Lial Energy",
                html_body=html,
                text_body=(
                    f"La tua fattura {partner_name} è stata verificata per {confirmed_amount_cents / 100:.2f} EUR. "
                    f"Paga {due / 100:.2f} EUR (carta o bonifico, causale {redemption.payment_reference_code}) "
                    f"per ricevere {total_after_payment / 100:.2f} LialCash sul tuo wallet."
                ),
            )
        except EmailNotConfiguredError:
            logger.warning("Invoice-redemption-verified email not sent (SMTP not configured), redemption=%s", redemption.id)

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
    partner = await db.get(Partner, redemption.partner_id)
    partner_name = partner.name if partner else "il partner"

    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=redemption.customer_user_id,
        type_="INVOICE_REDEMPTION_REJECTED", entity_type="invoice_redemption", entity_id=redemption.id,
        title="La tua richiesta di riscatto fattura è stata rifiutata", body=reason,
    )
    await db.commit()
    await db.refresh(redemption)

    customer_user = await db.get(User, redemption.customer_user_id)
    if customer_user is not None:
        html = render_email(
            preheader="La tua richiesta di riscatto fattura è stata rifiutata",
            heading="Richiesta di riscatto rifiutata",
            body_html=(
                f"<p>La tua richiesta di riscatto della fattura {partner_name} "
                f"(importo dichiarato {redemption.declared_amount_cents / 100:.2f} &euro;) è stata rifiutata "
                "da un amministratore.</p>"
                f"<p><strong>Motivo:</strong> {reason}</p>"
                "<p>Nessun importo è stato addebitato o accreditato. Se ritieni si tratti di un errore, "
                "contatta l'assistenza.</p>"
            ),
            cta_label="Vai al riscatto cashback",
            cta_url=f"{get_settings().public_app_base_url}/customer",
        )
        try:
            send_html_email(
                to=customer_user.email,
                subject="Riscatto fattura rifiutato - Lial Energy",
                html_body=html,
                text_body=f"La tua richiesta di riscatto della fattura {partner_name} è stata rifiutata. Motivo: {reason}",
            )
        except EmailNotConfiguredError:
            logger.warning("Invoice-redemption-rejected email not sent (SMTP not configured), redemption=%s", redemption.id)

    return redemption


async def change_payment_method(
    db: AsyncSession, *, organization_id: uuid.UUID, redemption: InvoiceRedemption, new_payment_method: str
) -> InvoiceRedemption:
    """"Paga con carta invece" / "Paga con bonifico invece" on a
    PAYMENT_PENDING redemption -- mirrors orders/service.py::
    change_payment_method exactly (same two methods, same availability
    check, same "drop the stale Stripe session when switching away from
    CARD" rule)."""
    if redemption.status != "PAYMENT_PENDING":
        raise InvalidRedemptionStateError(f"Cannot change payment method for a redemption in status {redemption.status}")
    if new_payment_method not in INVOICE_REDEMPTION_PAYMENT_METHODS:
        raise InvalidPaymentMethodError(f"payment_method must be one of {INVOICE_REDEMPTION_PAYMENT_METHODS}")

    if new_payment_method != redemption.payment_method:
        available = await get_available_payment_methods(db, organization_id=organization_id)
        if new_payment_method == "BANK_TRANSFER" and not available["bank_transfer"]:
            raise PaymentMethodNotAvailableError("Il pagamento con bonifico non è configurato.")
        if new_payment_method == "CARD" and not available["card"]:
            raise PaymentMethodNotAvailableError("Il pagamento con carta non è configurato.")
        if redemption.payment_method == "CARD":
            redemption.stripe_checkout_session_id = None
        redemption.payment_method = new_payment_method
        await db.commit()
        await db.refresh(redemption)
    return redemption


async def attach_stripe_checkout_session(db: AsyncSession, *, redemption: InvoiceRedemption, session_id: str) -> InvoiceRedemption:
    redemption.stripe_checkout_session_id = session_id
    await db.commit()
    await db.refresh(redemption)
    return redemption


async def upload_payment_proof(
    db: AsyncSession, *, organization_id: uuid.UUID, redemption: InvoiceRedemption,
    file_bytes: bytes, content_type: str, original_filename: str, actor_user_id: uuid.UUID,
) -> InvoiceRedemption:
    """Attaches a customer-uploaded photo/PDF of the bank transfer receipt --
    purely advisory extra evidence for whoever clicks "Conferma pagamento
    ricevuto" in the admin panel; never changes redemption.status by itself.
    Mirrors orders/service.py::upload_payment_proof exactly."""
    if redemption.status != "PAYMENT_PENDING":
        raise PaymentProofError(f"Cannot attach a payment proof to a redemption in status {redemption.status}")
    if redemption.payment_method != "BANK_TRANSFER":
        raise PaymentProofError("La prova di pagamento è prevista solo per i riscatti pagati con bonifico.")

    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"invoice-redemption-payment-proofs/{redemption.customer_user_id}",
        )
    except UploadValidationError as exc:
        raise PaymentProofError(str(exc)) from exc

    redemption.payment_proof_storage_key = storage_key
    redemption.payment_proof_original_filename = original_filename
    redemption.payment_proof_uploaded_at = utcnow()

    partner = await db.get(Partner, redemption.partner_id)
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="INVOICE_REDEMPTION_PAYMENT_PROOF_UPLOADED", entity_type="invoice_redemption", entity_id=redemption.id,
        title=f"Prova di pagamento caricata: riscatto {partner.name if partner else 'fattura'}",
        body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(redemption)
    return redemption


async def _credit_redemption(
    db: AsyncSession, *, organization_id: uuid.UUID, redemption: InvoiceRedemption, actor_user_id: uuid.UUID | None
) -> None:
    """The one place a real, external money inflow (bank transfer confirmed
    by an admin, or a card charge confirmed by Stripe) turns into wallet
    credit for this flow. Writes TWO wallet_transactions (base + bonus),
    never one combined row, so the ledger always shows the split explicitly
    (see docs/cashback-partner-invoices-plan.md). Idempotency keys are
    derived from the redemption's own id, not client-supplied -- the status
    guard in both callers already makes this exactly-once per redemption; a
    retried call after a partial failure (or, for Stripe, a retried webhook
    delivery) re-hits the same two keys and no-ops via credit_wallet's own
    idempotency check."""
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

    total_credited_cents = redemption.confirmed_amount_cents + bonus_cents
    method_label = "bonifico bancario" if redemption.payment_method == "BANK_TRANSFER" else "carta (Stripe)"
    customer_user = await db.get(User, redemption.customer_user_id)
    if customer_user is not None:
        html = render_email(
            preheader="Hai ricevuto un accredito cashback",
            heading="Cashback accreditato sul tuo wallet",
            body_html=(
                f"<p>Il riscatto della fattura {partner_name} è stato confermato "
                f"(pagamento del {CASHBACK_PERCENTAGE}% ricevuto via {method_label}).</p>"
                f"<p style=\"font-size:22px; font-weight:700; color:#f97316; margin:20px 0;\">"
                f"+{total_credited_cents / 100:.2f} LialCash</p>"
                f"<p>Di cui {redemption.confirmed_amount_cents / 100:.2f} LialCash dall'importo riscattato e "
                f"{bonus_cents / 100:.2f} LialCash di bonus {CASHBACK_PERCENTAGE}%.</p>"
                "<p>L'importo è già disponibile sul tuo wallet Lial Energy.</p>"
            ),
            cta_label="Vai al wallet",
            cta_url=f"{get_settings().public_app_base_url}/customer",
        )
        try:
            send_html_email(
                to=customer_user.email,
                subject="Cashback accreditato - Lial Energy",
                html_body=html,
                text_body=f"Cashback accreditato: +{total_credited_cents / 100:.2f} LialCash sul tuo wallet Lial Energy.",
            )
        except EmailNotConfiguredError:
            logger.warning("Cashback-credited email not sent (SMTP not configured), redemption=%s", redemption.id)


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, redemption_id: uuid.UUID, actor_user_id: uuid.UUID
) -> InvoiceRedemption:
    """Admin confirms the bank-transfer payment arrived. See
    _credit_redemption for the actual crediting logic, shared with the
    automatic Stripe path below."""
    redemption = await get_org_scoped(db, organization_id=organization_id, redemption_id=redemption_id)
    if redemption is None:
        raise InvoiceRedemptionError("Invoice redemption not found")
    if redemption.status != "PAYMENT_PENDING":
        raise InvalidRedemptionStateError(f"Cannot confirm payment for a redemption in status {redemption.status}")
    if redemption.payment_method == "CARD":
        # This is the manual bank-transfer confirmation action ("Conferma
        # bonifico ricevuto") -- a CARD redemption can only ever reach
        # CREDITED via mark_paid_via_stripe(), called from the Stripe
        # webhook once Stripe itself confirms the charge. Refusing it here
        # (not just hiding the button in admin-invoice-redemptions-panel.tsx)
        # is the actual enforcement: an admin must never be able to mint
        # wallet credit for a Stripe-selected redemption without Stripe's
        # own confirmation -- exactly the "non deve poter rubare soldi"
        # requirement this whole cashback feature exists to satisfy. Same
        # rule, same reasoning, as orders/service.py::confirm_payment.
        raise InvalidRedemptionStateError(
            "Questo riscatto si paga con carta: la conferma arriva automaticamente da Stripe, "
            "non è richiesta (né consentita) un'azione manuale."
        )

    await _credit_redemption(db, organization_id=organization_id, redemption=redemption, actor_user_id=actor_user_id)
    return redemption


async def mark_paid_via_stripe(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str
) -> InvoiceRedemption:
    """Called only from the Stripe webhook (payments/router.py) once
    checkout.session.completed fires -- the one case in this domain where
    CREDITED is reached with no human actor (actor_user_id stays NULL, same
    convention as orders/service.py::mark_paid_via_stripe)."""
    stmt = select(InvoiceRedemption).where(
        InvoiceRedemption.organization_id == organization_id,
        InvoiceRedemption.stripe_checkout_session_id == stripe_checkout_session_id,
    )
    redemption = (await db.execute(stmt)).scalar_one_or_none()
    if redemption is None:
        raise InvoiceRedemptionError("Invoice redemption not found for this Stripe checkout session")
    if redemption.status != "PAYMENT_PENDING":
        # Stripe can and does retry webhook delivery -- a second delivery
        # for an already-CREDITED redemption is expected, not an error.
        return redemption

    await _credit_redemption(db, organization_id=organization_id, redemption=redemption, actor_user_id=None)
    return redemption
