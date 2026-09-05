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
    # Free-text shown alongside the IBAN wherever a customer is told to pay
    # by bank transfer (invoice-redemption 3%, an order's residual) -- e.g.
    # "Includi il codice fattura nella causale" or bank-specific notes. Kept
    # separate from the IBAN itself so an admin can update the wording
    # without re-typing the account number.
    bank_transfer_instructions: str | None


class OrganizationSettingsUpdate(BaseModel):
    bank_iban: str | None = Field(default=None, max_length=42)
    bank_account_holder: str | None = Field(default=None, max_length=255)
    bank_transfer_instructions: str | None = Field(default=None, max_length=2000)


class PaymentSettingsRead(BaseModel):
    """Never echoes back a secret in full -- `stripe_secret_key` and
    `stripe_webhook_secret` are write-only from the dashboard's point of
    view, only their "is something set" state and a last-4 hint come back,
    same reasoning a password field is never round-tripped in plaintext.
    `stripe_publishable_key` is safe to return whole -- Stripe's own naming
    says so (it's meant to reach the browser)."""

    stripe_publishable_key: str | None
    stripe_secret_key_configured: bool
    stripe_secret_key_last4: str | None
    stripe_webhook_secret_configured: bool


class PaymentSettingsUpdate(BaseModel):
    stripe_publishable_key: str | None = Field(default=None, max_length=255)
    stripe_secret_key: str | None = Field(default=None, max_length=255)
    stripe_webhook_secret: str | None = Field(default=None, max_length=255)
