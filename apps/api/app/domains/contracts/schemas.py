import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9A-Z]{13,32}$")


def _validate_iban(v: str | None) -> str | None:
    if v is None:
        return v
    cleaned = v.replace(" ", "").upper()
    if not IBAN_PATTERN.match(cleaned):
        raise ValueError("IBAN non valido")
    return cleaned


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    supply_point_id: uuid.UUID
    product_version_id: uuid.UUID
    status: str
    notes: str | None = None
    iban: str | None = None
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
    iban: str | None = None

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        return _validate_iban(v)


class ContractIbanUpdate(BaseModel):
    iban: str

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        result = _validate_iban(v)
        if result is None:
            raise ValueError("iban is required")
        return result


class ContractTransitionRequest(BaseModel):
    to_status: str
    reason: str | None = None
    notes: str | None = None
