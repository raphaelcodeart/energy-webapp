import uuid

from pydantic import BaseModel, ConfigDict, Field


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str


class OrganizationSettingsRead(BaseModel):
    """Subset of Organization.settings (JSONB) that has a typed shape --
    admin-editable company configuration, starting with the bank account
    customers wire bonifico payments to (see
    invoice_redemptions/router.py's GET /payment-info and
    docs/cashback-partner-invoices-plan.md). Deliberately NOT the whole raw
    settings dict: only fields with a real schema here are ever
    read/written through this endpoint, so an admin can't accidentally
    stuff arbitrary JSON into it."""

    bank_iban: str | None
    bank_account_holder: str | None


class OrganizationSettingsUpdate(BaseModel):
    bank_iban: str | None = Field(default=None, max_length=42)
    bank_account_holder: str | None = Field(default=None, max_length=255)
