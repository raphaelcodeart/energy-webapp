import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    promoter_code: str
    status: str
    photo_url: str | None = None
    current_rank_id: uuid.UUID | None
    rank_code: str | None
    direct_parent_agent_id: uuid.UUID | None
    joined_at: datetime
    rejection_reason: str | None = None


class AgentCreateRequest(BaseModel):
    display_name: str
    promoter_code: str
    parent_agent_id: uuid.UUID | None = None
    current_rank_id: uuid.UUID | None = None


class RecruitRequest(BaseModel):
    display_name: str
    promoter_code: str
    current_rank_id: uuid.UUID | None = None


class AgentUpdateRequest(BaseModel):
    display_name: str | None = None
    status: str | None = None
    current_rank_id: uuid.UUID | None = None


class AgentRejectRequest(BaseModel):
    reason: str | None = None


class OrganizationNetworkLevelsRead(BaseModel):
    people_total: int
    levels_total: int
    people_by_level: dict[int, int]
