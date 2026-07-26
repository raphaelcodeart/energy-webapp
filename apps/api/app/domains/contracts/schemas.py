import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    supply_point_id: uuid.UUID
    product_version_id: uuid.UUID
    status: str
    notes: str | None = None
    created_at: datetime
    activated_at: datetime | None = None
    expires_at: datetime | None = None
    # Denormalized display fields -- never the sole source of truth (the FKs
    # above are), but every list view needs a human-readable name, not a raw
    # UUID, so the service populates these instead of every caller doing its
    # own N+1 lookup. None only if the referenced row was hard-deleted.
    product_name: str | None = None
    supply_point_label: str | None = None


class ContractCreate(BaseModel):
    customer_id: uuid.UUID
    supply_point_id: uuid.UUID
    product_version_id: uuid.UUID
    producer_agent_id: uuid.UUID
    notes: str | None = None


class ContractTransitionRequest(BaseModel):
    to_status: str
    reason: str | None = None
    notes: str | None = None
