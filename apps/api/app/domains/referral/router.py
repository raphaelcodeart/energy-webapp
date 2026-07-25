from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.domains.referral import service as referral_service
from app.domains.referral.schemas import PromoterCodeRead

router = APIRouter(prefix="/r", tags=["referral"])

REFERRAL_COOKIE_NAME = "lial_referral"


@router.get("/{code}", response_model=PromoterCodeRead)
async def resolve_promoter_link(
    code: str,
    request: Request,
    response: Response,
    organization_id: str,
    db: AsyncSession = Depends(get_db),
) -> PromoterCodeRead:
    """Called when a visitor opens https://dominio.it/r/CODICE-PROMOTER. Validates
    the code, records the click, and sets a signed attribution cookie the customer
    registration flow reads later (within ATTRIBUTION_WINDOW_DAYS)."""
    import uuid as _uuid

    promoter_code = await referral_service.get_active_promoter_code(
        db, organization_id=_uuid.UUID(organization_id), code=code
    )
    if promoter_code is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or expired promoter code")

    _, raw_token = await referral_service.record_referral_click(
        db,
        organization_id=_uuid.UUID(organization_id),
        promoter_code=promoter_code,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        key=REFERRAL_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=referral_service.ATTRIBUTION_WINDOW_DAYS * 24 * 3600,
    )
    return PromoterCodeRead.model_validate(promoter_code)
