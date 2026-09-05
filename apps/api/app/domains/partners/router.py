import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.domains.partners import service as partners_service
from app.domains.partners.schemas import PartnerCreate, PartnerRead, PartnerUpdate

router = APIRouter(prefix="/partners", tags=["partners"])


@router.get("", response_model=list[PartnerRead])
async def list_partners(
    active_only: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PartnerRead]:
    """Open to any authenticated user, not permission-gated -- a customer
    picks a partner from this list in the redemption wizard (see
    invoice_redemptions/router.py). Admin CRUD below stays partners.manage."""
    partners = await partners_service.list_partners(
        db, organization_id=current_user.organization_id, active_only=active_only
    )
    return [PartnerRead.model_validate(p) for p in partners]


@router.post("", response_model=PartnerRead, status_code=status.HTTP_201_CREATED)
async def create_partner(
    payload: PartnerCreate,
    current_user: CurrentUser = Depends(require_permission("partners.manage")),
    db: AsyncSession = Depends(get_db),
) -> PartnerRead:
    try:
        partner = await partners_service.create_partner(db, organization_id=current_user.organization_id, payload=payload)
    except partners_service.PartnerNameTakenError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return PartnerRead.model_validate(partner)


@router.patch("/{partner_id}", response_model=PartnerRead)
async def update_partner(
    partner_id: uuid.UUID,
    payload: PartnerUpdate,
    current_user: CurrentUser = Depends(require_permission("partners.manage")),
    db: AsyncSession = Depends(get_db),
) -> PartnerRead:
    try:
        partner = await partners_service.update_partner(
            db, organization_id=current_user.organization_id, partner_id=partner_id, payload=payload
        )
    except partners_service.PartnerNameTakenError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if partner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")
    return PartnerRead.model_validate(partner)
