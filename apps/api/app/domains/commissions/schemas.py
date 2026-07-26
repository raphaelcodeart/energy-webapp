import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class CommissionMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    contract_id: uuid.UUID
    movement_type: str
    amount_cents: int
    currency: str
    status: str
    effective_date: date


class SimulationStepRead(BaseModel):
    beneficiary_agent_id: str
    rank_code: str
    gross_amount_cents: int
    movement_type: str
    explanation: str


class SimulateRequest(BaseModel):
    rank_overrides: dict[str, str] | None = None


class RankRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    level: int
    personal_token_cents: int
