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


class CommissionMovementDetailRead(BaseModel):
    """Full traceability for one commission movement -- which contract, which
    customer, which promoter earned it, from how many levels below the
    contract's producer, at what rank, and the exact breakdown that produced
    the amount. See commissions/services/admin_ledger.py."""

    id: uuid.UUID
    contract_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    product_name: str
    value_cents: int
    agent_id: uuid.UUID
    agent_name: str
    agent_promoter_code: str
    agent_current_rank_code: str | None
    producer_agent_id: uuid.UUID
    producer_name: str
    depth_from_producer: int | None
    movement_type: str
    rank_at_calculation: str | None
    base_amount_cents: int | None
    already_distributed_cents: int | None
    entrepreneurial_difference_cents: int | None
    amount_cents: int
    explanation: str | None
    status: str
    effective_date: date
    paid_date: date | None


class CommissionLevelTotalsRead(BaseModel):
    depth: int
    contracts: int
    value_cents: int
    commission_cents: int


class CommissionPaymentRequest(BaseModel):
    note: str | None = None


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


class RankEvaluationChangeRead(BaseModel):
    agent_id: uuid.UUID
    display_name: str
    previous_rank_code: str | None
    new_rank_code: str
    direction: str  # "PROMOTED" | "DEMOTED"
