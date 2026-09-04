import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class AgentProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    display_name: str
    promoter_code: str
    status: str
    photo_url: str | None = None
    current_rank_id: uuid.UUID | None
    rank_code: str | None = None
    rejection_reason: str | None = None
    is_blacklisted: bool = False


class RankProgressRead(BaseModel):
    current_rank_code: str | None
    current_rank_name: str | None
    next_rank_code: str | None
    next_rank_name: str | None
    is_max_rank: bool
    personal_volume_cents: int
    personal_volume_threshold_cents: int
    group_volume_cents: int
    group_volume_threshold_cents: int


class NetworkNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: uuid.UUID
    direct_parent_agent_id: uuid.UUID | None
    status: str


class BranchMemberRead(BaseModel):
    agent_id: uuid.UUID
    depth: int
    display_name: str
    promoter_code: str
    status: str
    rank_code: str | None
    # Direct parent within this branch -- null for the root itself, and null
    # for anyone whose real parent isn't in this fetch (shouldn't happen for a
    # proper descendant list, but defensive). Lets the frontend build the tree
    # from actual edges instead of assuming a fragile pre-order row sequence.
    parent_agent_id: uuid.UUID | None = None


class BranchAgentSummaryRead(BaseModel):
    agent_id: uuid.UUID
    depth: int
    display_name: str
    promoter_code: str
    status: str
    rank_code: str | None
    contracts_total: int
    contracts_by_status: dict[str, int]
    contracts_problem: int
    contracts_in_progress: int
    contracts_processed: int
    commission_cents: int


class BranchSummaryTotals(BaseModel):
    contracts: int
    commission_cents: int
    contracts_by_status: dict[str, int] = {}
    contracts_closed: int = 0
    contracts_rejected: int = 0
    contracts_pending: int = 0
    contracts_in_progress: int = 0
    levels_below: int = 0
    people_total: int = 0


class BranchSummaryRead(BaseModel):
    agents: list[BranchAgentSummaryRead]
    totals: BranchSummaryTotals


class BranchContractRead(BaseModel):
    contract_id: uuid.UUID
    status: str
    customer_id: uuid.UUID
    customer_name: str
    customer_email: str | None
    customer_phone: str | None
    product_name: str
    value_cents: int
    supply_point_label: str | None = None
    expires_at: datetime | None = None
    producer_agent_id: uuid.UUID
    producer_name: str
    commission_cents: int
    # The VIEWING user's own cut of this specific contract (None, not 0, when
    # they have no agent profile at all -- e.g. an org admin browsing someone
    # else's branch, who is never a commission beneficiary).
    my_commission_cents: int | None = None
    is_problem: bool
    admin_note: str | None = None


class MoveAgentRequest(BaseModel):
    new_parent_agent_id: uuid.UUID | None
    reason: str
    effective_at: datetime | None = None


class AgentListItemRead(BaseModel):
    id: uuid.UUID
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    promoter_code: str
    status: str
    photo_url: str | None = None
    current_rank_id: uuid.UUID | None
    rank_code: str | None
    direct_parent_agent_id: uuid.UUID | None
    joined_at: datetime
    rejection_reason: str | None = None
    # None for an admin-created/suggested agent with no login of its own
    # (AgentProfile.user_id is nullable) -- never guess an email for those.
    email: str | None = None
    is_blacklisted: bool = False


class AgentCreateRequest(BaseModel):
    first_name: str
    last_name: str
    promoter_code: str
    parent_agent_id: uuid.UUID | None = None
    current_rank_id: uuid.UUID | None = None
    # Optional: links the new agent to an ALREADY-REGISTERED customer's login
    # (e.g. someone who signed up as a customer via a promoter's referral link
    # and is now being promoted to promoter under that same sponsor) instead of
    # creating a login-less suggestion. See router.py create_agent.
    customer_email: EmailStr | None = None

    @field_validator("first_name", "last_name", "promoter_code", "customer_email", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class RootPromoterCreateRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    # Optional: auto-generated (initials + random suffix) when omitted, same
    # as the self-service "lavora con noi" flow -- see _generate_promoter_code.
    promoter_code: str | None = None

    @field_validator("first_name", "last_name", "email", "promoter_code", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        """A stray leading/trailing space (copy-pasted name/email) must not
        end up baked into the login or the shareable referral code."""
        return v.strip() if isinstance(v, str) else v


class RootPromoterCreateResponse(BaseModel):
    agent_id: uuid.UUID
    display_name: str
    promoter_code: str
    personal_link: str
    email: str
    # Shown to the admin exactly once, in this response -- never stored or
    # logged in plaintext anywhere else. The admin must hand it to the
    # promoter out of band and have them change it at first login.
    temporary_password: str


class RecruitRequest(BaseModel):
    first_name: str
    last_name: str
    promoter_code: str
    current_rank_id: uuid.UUID | None = None

    @field_validator("first_name", "last_name", "promoter_code", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class PromoterApplicationRequest(BaseModel):
    # Both optional: if omitted, the backend derives them from the caller's
    # existing Customer profile (see POST /agents/apply) -- the UI never
    # actually sends these, they exist for a programmatic caller that already
    # knows a different name to use.
    first_name: str | None = None
    last_name: str | None = None


class AgentUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    status: str | None = None
    current_rank_id: uuid.UUID | None = None
    # Set true to blacklist (worse than a plain status=TERMINATED
    # deactivation): a blacklisted promoter who re-applies via "lavora con
    # noi" goes through manual PENDING_APPROVAL/approve instead of
    # auto-activating. Set false to lift a blacklist. Omit to leave unchanged.
    is_blacklisted: bool | None = None


class AgentRejectRequest(BaseModel):
    reason: str | None = None


class OrganizationNetworkLevelsRead(BaseModel):
    people_total: int
    levels_total: int
    people_by_level: dict[int, int]
