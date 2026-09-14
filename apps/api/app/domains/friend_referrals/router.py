import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.domains.friend_referrals import service as friend_referrals_service
from app.domains.friend_referrals.schemas import (
    FriendReferralAdminClaimRead,
    FriendReferralClaimUpdate,
    FriendReferralSummaryRead,
)

router = APIRouter(prefix="/friend-referrals", tags=["friend-referrals"])


@router.get("/me", response_model=FriendReferralSummaryRead)
async def get_my_friend_referrals(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FriendReferralSummaryRead:
    """My own one-level referral list. Authentication only, no permission --
    everyone has one of these, promoter or not, and the user id comes from
    the session, never the request (same shape as GET /wallets/me)."""
    summary = await friend_referrals_service.get_my_summary(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    return FriendReferralSummaryRead(**summary)


@router.post("/me/reward-claims", response_model=FriendReferralSummaryRead, status_code=status.HTTP_201_CREATED)
async def request_my_reward(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("friend-referral-reward", max_requests=10, window_seconds=300)),
) -> FriendReferralSummaryRead:
    """Asks the administration for the gift earned at the next milestone. The
    milestone is recomputed server-side from the referrals actually in the
    database -- the client never states which one it thinks it has earned."""
    try:
        await friend_referrals_service.request_reward(
            db, organization_id=current_user.organization_id, user_id=current_user.user_id
        )
    except friend_referrals_service.FriendReferralError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    summary = await friend_referrals_service.get_my_summary(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    return FriendReferralSummaryRead(**summary)


@router.get("/admin/reward-claims", response_model=list[FriendReferralAdminClaimRead])
async def list_reward_claims(
    status_filter: str = "REQUESTED",
    current_user: CurrentUser = Depends(require_permission("customers.read")),
    db: AsyncSession = Depends(get_db),
) -> list[FriendReferralAdminClaimRead]:
    """Gated on customers.read rather than a new permission: this is a list of
    customers asking for something, exactly the tier of information the
    Anagrafiche screens already expose to the same roles."""
    rows = await friend_referrals_service.list_claims(
        db, organization_id=current_user.organization_id, status=status_filter
    )
    return [FriendReferralAdminClaimRead(**row) for row in rows]


@router.patch("/admin/reward-claims/{claim_id}", response_model=FriendReferralAdminClaimRead)
async def handle_reward_claim(
    claim_id: uuid.UUID,
    payload: FriendReferralClaimUpdate,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> FriendReferralAdminClaimRead:
    claim = await friend_referrals_service.handle_claim(
        db, organization_id=current_user.organization_id, claim_id=claim_id,
        status=payload.status, note=payload.note, actor_user_id=current_user.user_id,
    )
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non trovata")
    rows = await friend_referrals_service.list_claims(
        db, organization_id=current_user.organization_id, status="ALL"
    )
    row = next((r for r in rows if r["id"] == claim.id), None)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non trovata")
    return FriendReferralAdminClaimRead(**row)
