import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.domains.customers.schemas import SupplyPointCreate

IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9A-Z]{13,32}$")
# Deliberately simple (not RFC 5322): good enough to catch typos in a form
# field without pulling in a dedicated email-validation dependency, same
# pragmatic bar as IBAN_PATTERN above.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_iban(v: str | None) -> str | None:
    if v is None:
        return v
    cleaned = v.replace(" ", "").upper()
    if not IBAN_PATTERN.match(cleaned):
        raise ValueError("IBAN non valido")
    return cleaned


def _validate_email(v: str | None) -> str | None:
    if v is None:
        return v
    cleaned = v.strip()
    if not EMAIL_PATTERN.match(cleaned):
        raise ValueError("Email non valida")
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
    email: str | None = None
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
    email: str | None = None

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        return _validate_iban(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        return _validate_email(v)


class ContractSelfServiceCreate(BaseModel):
    """'Attiva Contratto' -- POST /contracts/mine. No producer_agent_id (unlike
    the staff-facing ContractCreate): the customer's own referring promoter is
    resolved server-side, see contracts/service.py::create_contract_self_service.
    email is required here (unlike ContractCreate's optional one) -- the
    activation wizard always collects it, pre-filled from the account's own
    email but freely editable, since a contract's contact email need not match
    the login email (see contracts/models.py::Contract.email)."""

    product_version_id: uuid.UUID
    supply_point: SupplyPointCreate
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        validated = _validate_email(v)
        if validated is None:
            raise ValueError("email is required")
        return validated


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


class ContractStatusHistoryRead(BaseModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    actor_user_id: uuid.UUID
    actor_name: str
    reason: str | None
    notes: str | None
    created_at: datetime
