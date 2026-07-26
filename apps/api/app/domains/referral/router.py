import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.network.models import AgentProfile
from app.domains.referral import service as referral_service
from app.domains.referral.schemas import PromoterCodeRead

# Two separate routers on purpose: /r/{code} is public (an anonymous visitor
# clicking a shared link, no auth) and must never collide with an
# authenticated, agent-scoped path -- /r/mine would otherwise be ambiguous
# with /r/{code} where code="mine".
router = APIRouter(prefix="/r", tags=["referral"])
authenticated_router = APIRouter(prefix="/referral", tags=["referral"])

REFERRAL_COOKIE_NAME = "lial_referral"


@authenticated_router.get("/mine", response_model=PromoterCodeRead | None)
async def get_my_referral_code(
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> PromoterCodeRead | None:
    """Get-or-create the caller's own shareable referral link -- every agent can
    call this, no separate permission needed beyond already having an agent
    profile (same gate as /network/mine)."""
    agent_stmt = select(AgentProfile.id).where(
        AgentProfile.organization_id == current_user.organization_id,
        AgentProfile.user_id == current_user.user_id,
    )
    agent_id = (await db.execute(agent_stmt)).scalar_one_or_none()
    if agent_id is None:
        return None
    promoter_code = await referral_service.get_or_create_promoter_code(
        db, organization_id=current_user.organization_id, agent_id=agent_id
    )
    return PromoterCodeRead.model_validate(promoter_code)


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
