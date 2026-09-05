import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.domains.invoice_redemptions import service as redemptions_service
from app.domains.invoice_redemptions.schemas import (
    InvoiceRedemptionRead,
    InvoiceRedemptionRejectRequest,
    InvoiceRedemptionUrlRead,
    InvoiceRedemptionVerifyRequest,
    PaymentInfoRead,
)

router = APIRouter(prefix="/invoice-redemptions", tags=["invoice-redemptions"])


@router.get("/payment-info", response_model=PaymentInfoRead)
async def get_payment_info(current_user: CurrentUser = Depends(get_current_user)) -> PaymentInfoRead:
    """Where a customer wires the 3% redemption payment -- iban is None until
    an admin sets COMPANY_BANK_IBAN, in which case the wizard tells the
    customer to contact administration instead of showing a blank field."""
    settings = get_settings()
    return PaymentInfoRead(iban=settings.company_bank_iban or None, holder=settings.company_bank_holder)


@router.post("", response_model=InvoiceRedemptionRead, status_code=status.HTTP_201_CREATED)
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
