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


class MoveAgentRequest(BaseModel):
    new_parent_agent_id: uuid.UUID | None
    reason: str
    effective_at: datetime | None = None
