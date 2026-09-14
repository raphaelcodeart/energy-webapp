import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FriendReferralItemRead(BaseModel):
    id: uuid.UUID
    display_name: str
    #: INVITED / IN_PROGRESS / ACTIVE -- see service.list_my_referrals. Only
    #: ACTIVE counts towards the gift.
    state: str
    source: str
    invited_at: datetime


class FriendReferralClaimRead(BaseModel):
    id: uuid.UUID
    milestone: int
    status: str
    note: str | None = None
    requested_at: datetime
    handled_at: datetime | None = None


class FriendReferralSummaryRead(BaseModel):
    code: str
    invited_total: int
    active_total: int
    reward_every: int
    missing_for_next_reward: int
    claimable_milestone: int | None = None
    referrals: list[FriendReferralItemRead] = []
    claims: list[FriendReferralClaimRead] = []


class FriendReferralAdminClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    referrer_user_id: uuid.UUID
    referrer_name: str
    referrer_email: str | None = None
    milestone: int
    status: str
    note: str | None = None
    requested_at: datetime
    handled_at: datetime | None = None


class FriendReferralClaimUpdate(BaseModel):
    #: FULFILLED (gift given) or REJECTED. There is deliberately no way back
    #: to REQUESTED: a handled request stays handled, and a second gift means
    #: a second milestone.
    status: str = Field(pattern="^(FULFILLED|REJECTED)$")
    note: str | None = Field(default=None, max_length=500)
