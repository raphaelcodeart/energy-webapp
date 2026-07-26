import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.domains.support.models import TICKET_CATEGORIES, TICKET_STATUSES


class TicketMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_user_id: uuid.UUID
    author_role: str
    author_name: str | None = None
    body: str
    created_at: datetime


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    opened_by_user_id: uuid.UUID
    opened_by_role: str
    opened_by_name: str | None = None
    subject: str
    category: str
    status: str
    contract_id: uuid.UUID | None
    created_at: datetime
    message_count: int = 0
    last_message_at: datetime | None = None


class TicketDetailRead(TicketRead):
    messages: list[TicketMessageRead] = []


class TicketCreate(BaseModel):
    subject: str
    category: str = "ALTRO"
    message: str
    contract_id: uuid.UUID | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in TICKET_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(TICKET_CATEGORIES)}")
        return v


class TicketMessageCreate(BaseModel):
    body: str


class TicketStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in TICKET_STATUSES:
            raise ValueError(f"status must be one of {sorted(TICKET_STATUSES)}")
        return v
