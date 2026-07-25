import uuid

from pydantic import BaseModel, ConfigDict


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    supply_point_id: uuid.UUID
    product_version_id: uuid.UUID
    status: str


class ContractCreate(BaseModel):
    customer_id: uuid.UUID
    supply_point_id: uuid.UUID
    product_version_id: uuid.UUID
    producer_agent_id: uuid.UUID


class ContractTransitionRequest(BaseModel):
    to_status: str
    reason: str | None = None
    notes: str | None = None
