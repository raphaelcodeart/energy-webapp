import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.domains.invoice_redemptions import service as redemptions_service
from app.domains.invoice_redemptions.schemas import (
    InvoiceRedemptionCheckoutSessionRead,
    InvoiceRedemptionPaymentMethodUpdate,
    InvoiceRedemptionPaymentProofUrlRead,
    InvoiceRedemptionRead,
    InvoiceRedemptionRejectRequest,
    InvoiceRedemptionUrlRead,
    InvoiceRedemptionVerifyRequest,
    PaymentInfoRead,
)
from app.domains.organizations import service as organizations_service
from app.domains.payments import service as payments_service

router = APIRouter(prefix="/invoice-redemptions", tags=["invoice-redemptions"])


def _redemption_error_to_http(exc: redemptions_service.InvoiceRedemptionError) -> HTTPException:
    if isinstance(exc, (redemptions_service.InvalidRedemptionStateError, redemptions_service.InvalidPaymentMethodError,
                         redemptions_service.PaymentMethodNotAvailableError, redemptions_service.PaymentProofError)):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get("/payment-info", response_model=PaymentInfoRead)
async def get_payment_info(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PaymentInfoRead:
    """Where a customer wires the 3% redemption payment. The IBAN an admin
    saved in Impostazioni Azienda (Organization.settings, DB-backed --
    editable from the dashboard) wins; COMPANY_BANK_IBAN in .env is only a
    bootstrapping fallback for a server nobody has configured yet. Either
    way, iban is None (wizard shows "contatta l'amministrazione") until one
    of the two is actually set."""
    org_settings = await organizations_service.get_settings(db, organization_id=current_user.organization_id)
    settings = get_settings()
    iban = org_settings["bank_iban"] or settings.company_bank_iban or None
    holder = org_settings["bank_account_holder"] or settings.company_bank_holder
    return PaymentInfoRead(iban=iban, holder=holder, instructions=org_settings["bank_transfer_instructions"])


@router.post(
    "",
    response_model=InvoiceRedemptionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("invoice-redemption-submit", max_requests=20, window_seconds=300))],
)
async def submit_invoice_redemption(
    partner_id: uuid.UUID = Form(...),
    declared_amount_cents: int = Form(...),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    """Any authenticated user (customer or promoter -- either may have paid
    their own bill to a partner supplier), no permission beyond
    authentication, same reasoning as POST /wallets/transfer."""
    file_bytes = await file.read()
    try:
        redemption = await redemptions_service.submit_redemption(
            db,
            organization_id=current_user.organization_id,
            customer_user_id=current_user.user_id,
            partner_id=partner_id,
            declared_amount_cents=declared_amount_cents,
            file_bytes=file_bytes,
            content_type=file.content_type or "",
            original_filename=file.filename or "fattura",
        )
    except redemptions_service.PartnerNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except redemptions_service.RedemptionValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))


@router.get("/mine", response_model=list[InvoiceRedemptionRead])
async def list_my_invoice_redemptions(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceRedemptionRead]:
    rows = await redemptions_service.list_mine(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    return [InvoiceRedemptionRead(**d) for d in await redemptions_service.hydrate(db, rows)]


@router.get("/mine/{redemption_id}/photo-url", response_model=InvoiceRedemptionUrlRead)
async def get_my_invoice_redemption_photo_url(
    redemption_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionUrlRead:
    redemption = await redemptions_service.get_owned(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, redemption_id=redemption_id
    )
    if redemption is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice redemption not found")
    return InvoiceRedemptionUrlRead(url=redemptions_service.presigned_photo_url(redemption))


@router.patch("/mine/{redemption_id}/payment-method", response_model=InvoiceRedemptionRead)
async def change_my_redemption_payment_method(
    redemption_id: uuid.UUID,
    payload: InvoiceRedemptionPaymentMethodUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    """"Paga con carta invece" / "Paga con bonifico invece" on a
    PAYMENT_PENDING redemption -- only the redemption's own customer."""
    redemption = await redemptions_service.get_owned(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, redemption_id=redemption_id
    )
    if redemption is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice redemption not found")
    try:
        redemption = await redemptions_service.change_payment_method(
            db, organization_id=current_user.organization_id, redemption=redemption,
            new_payment_method=payload.payment_method,
        )
    except redemptions_service.InvoiceRedemptionError as exc:
        raise _redemption_error_to_http(exc) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))


@router.post("/mine/{redemption_id}/checkout-session", response_model=InvoiceRedemptionCheckoutSessionRead)
async def create_my_redemption_checkout_session(
    redemption_id: uuid.UUID,
    success_url: str,
    cancel_url: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionCheckoutSessionRead:
    """Only the redemption's own customer may request a checkout session for
    it -- 404 (not 403) for someone else's redemption, same
    information-hiding reasoning as the rest of this codebase's ownership
    checks. Charges exactly the CASHBACK_PERCENTAGE% redemption fee, never
    the invoice's full value."""
    redemption = await redemptions_service.get_owned(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, redemption_id=redemption_id
    )
    if redemption is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice redemption not found")
    if redemption.status != "PAYMENT_PENDING":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot pay a redemption in status {redemption.status}")
    try:
        checkout_url = await payments_service.create_checkout_session_for_redemption(
            db, organization_id=current_user.organization_id, redemption=redemption,
            success_url=success_url, cancel_url=cancel_url,
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return InvoiceRedemptionCheckoutSessionRead(checkout_url=checkout_url)


@router.post(
    "/mine/{redemption_id}/payment-proof",
    response_model=InvoiceRedemptionRead,
    dependencies=[Depends(rate_limit("payment-proof-upload", max_requests=20, window_seconds=300))],
)
async def upload_my_redemption_payment_proof(
    redemption_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    """Customer attaches a photo/PDF of the bank transfer receipt for the
    redemption fee -- extra evidence for the admin, never a payment
    confirmation by itself (see
    invoice_redemptions/service.py::upload_payment_proof's docstring)."""
    redemption = await redemptions_service.get_owned(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, redemption_id=redemption_id
    )
    if redemption is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice redemption not found")
    file_bytes = await file.read()
    try:
        redemption = await redemptions_service.upload_payment_proof(
            db, organization_id=current_user.organization_id, redemption=redemption,
            file_bytes=file_bytes, content_type=file.content_type or "",
            original_filename=file.filename or "prova-pagamento", actor_user_id=current_user.user_id,
        )
    except redemptions_service.PaymentProofError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))


@router.get("/mine/{redemption_id}/payment-proof-url", response_model=InvoiceRedemptionPaymentProofUrlRead)
async def get_my_redemption_payment_proof_url(
    redemption_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionPaymentProofUrlRead:
    redemption = await redemptions_service.get_owned(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, redemption_id=redemption_id
    )
    if redemption is None or redemption.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment proof not found")
    return InvoiceRedemptionPaymentProofUrlRead(url=redemptions_service.presigned_payment_proof_url(redemption))


@router.get("/admin", response_model=list[InvoiceRedemptionRead])
async def list_invoice_redemptions_admin(
    status_filter: str | None = None,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceRedemptionRead]:
    """wallet.manage-gated, not a lighter catalog/partners permission -- this
    queue is the entry point to minting real wallet credit, same sensitivity
    tier as the rest of the wallet admin surface."""
    rows = await redemptions_service.list_admin_queue(
        db, organization_id=current_user.organization_id, status_filter=status_filter
    )
    return [InvoiceRedemptionRead(**d) for d in await redemptions_service.hydrate(db, rows)]


@router.get("/admin/{redemption_id}/photo-url", response_model=InvoiceRedemptionUrlRead)
async def get_invoice_redemption_photo_url_admin(
    redemption_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionUrlRead:
    redemption = await redemptions_service.get_org_scoped(
        db, organization_id=current_user.organization_id, redemption_id=redemption_id
    )
    if redemption is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice redemption not found")
    return InvoiceRedemptionUrlRead(url=redemptions_service.presigned_photo_url(redemption))


@router.get("/admin/{redemption_id}/payment-proof-url", response_model=InvoiceRedemptionPaymentProofUrlRead)
async def get_invoice_redemption_payment_proof_url_admin(
    redemption_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionPaymentProofUrlRead:
    redemption = await redemptions_service.get_org_scoped(
        db, organization_id=current_user.organization_id, redemption_id=redemption_id
    )
    if redemption is None or redemption.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment proof not found")
    return InvoiceRedemptionPaymentProofUrlRead(url=redemptions_service.presigned_payment_proof_url(redemption))


@router.post("/admin/{redemption_id}/verify", response_model=InvoiceRedemptionRead)
async def verify_invoice_redemption(
    redemption_id: uuid.UUID,
    payload: InvoiceRedemptionVerifyRequest,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    try:
        redemption = await redemptions_service.verify(
            db,
            organization_id=current_user.organization_id,
            redemption_id=redemption_id,
            confirmed_amount_cents=payload.confirmed_amount_cents,
            actor_user_id=current_user.user_id,
        )
    except redemptions_service.InvalidRedemptionStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except redemptions_service.InvoiceRedemptionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))


@router.post("/admin/{redemption_id}/reject", response_model=InvoiceRedemptionRead)
async def reject_invoice_redemption(
    redemption_id: uuid.UUID,
    payload: InvoiceRedemptionRejectRequest,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    try:
        redemption = await redemptions_service.reject(
            db,
            organization_id=current_user.organization_id,
            redemption_id=redemption_id,
            reason=payload.reason,
            actor_user_id=current_user.user_id,
        )
    except redemptions_service.InvalidRedemptionStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except redemptions_service.InvoiceRedemptionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))


@router.post("/admin/{redemption_id}/confirm-payment", response_model=InvoiceRedemptionRead)
async def confirm_invoice_redemption_payment(
    redemption_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    try:
        redemption = await redemptions_service.confirm_payment(
            db, organization_id=current_user.organization_id, redemption_id=redemption_id,
            actor_user_id=current_user.user_id,
        )
    except redemptions_service.InvalidRedemptionStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except redemptions_service.InvoiceRedemptionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))
