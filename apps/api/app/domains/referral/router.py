
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


async def _resolve_friend_link(db: AsyncSession, *, organization_id, code: str) -> PromoterCodeRead:
    """A plain customer's invite link, answered in the same shape a promoter
    link is -- the public registration page only ever reads the code and the
    name to show "Invitato da ...", and does not need to know (or tell the
    visitor) which of the two kinds of link they followed."""
    from app.domains.customers.models import Company, Customer, CustomerProfile
    from app.domains.customers.service import display_name_for
    from app.domains.friend_referrals import service as friend_referrals_service
    from app.domains.users.models import User

    friend_code = await friend_referrals_service.get_active_code(
        db, organization_id=organization_id, code=code
    )
    if friend_code is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or expired promoter code")
    # Refuse a link whose owner has nobody active to attribute new customers
    # to, HERE rather than after the visitor has filled in the whole form.
    if await friend_referrals_service.promoter_code_for_referrer(
        db, organization_id=organization_id, user_id=friend_code.user_id
    ) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid or expired promoter code")

    customer = (
        await db.execute(
            select(Customer).where(
                Customer.organization_id == organization_id, Customer.user_id == friend_code.user_id
            )
        )
    ).scalar_one_or_none()
    display_name = None
    if customer is not None:
        profile = await db.get(CustomerProfile, customer.id)
        company = await db.get(Company, customer.id)
        display_name = display_name_for(customer.kind, profile, company)
    if not display_name or display_name == "—":
        user = await db.get(User, friend_code.user_id)
        display_name = user.email if user else None

    return PromoterCodeRead(
        id=friend_code.id,
        code=friend_code.code,
        personal_link=f"/r/{friend_code.code}",
        status=friend_code.status,
        promoter_display_name=display_name,
    )


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
        # Not a promoter code -- it may be an ordinary customer's "segnala un
        # amico" link (friend_referral_codes), which lands on this same
        # public page. Resolved here, with no click tracking and no
        # attribution cookie: the segnalatori list is informational and the
        # commercial attribution for this registration is decided at signup
        # from the referrer's OWN promoter, not from a cookie. See
        # friend_referrals/models.py.
        return await _resolve_friend_link(db, organization_id=_uuid.UUID(organization_id), code=code)

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
    agent = await db.get(AgentProfile, promoter_code.agent_id)
    return PromoterCodeRead(
        id=promoter_code.id,
        code=promoter_code.code,
        personal_link=promoter_code.personal_link,
        status=promoter_code.status,
        promoter_display_name=agent.display_name if agent else None,
    )
