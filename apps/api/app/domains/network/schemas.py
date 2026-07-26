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
    current_rank_id: uuid.UUID | None


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
    producer_agent_id: uuid.UUID
    producer_name: str
    commission_cents: int
    is_problem: bool


class MoveAgentRequest(BaseModel):
    new_parent_agent_id: uuid.UUID | None
    reason: str
    effective_at: datetime | None = None


class AgentListItemRead(BaseModel):
    id: uuid.UUID
    display_name: str
    promoter_code: str
    status: str
    current_rank_id: uuid.UUID | None
    rank_code: str | None
    direct_parent_agent_id: uuid.UUID | None
    joined_at: datetime


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
