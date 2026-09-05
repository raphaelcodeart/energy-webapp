import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class InvoiceRedemptionRead(BaseModel):
    """Built from a service dict row (see service.py::_to_read_dict), not
    model_validate(orm_obj) -- partner_name/customer_display_name are
    resolved joins, same reasoning as WalletTransactionRead."""

    id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    customer_user_id: uuid.UUID
    customer_display_name: str
    original_filename: str
    content_type: str
    declared_amount_cents: int
    confirmed_amount_cents: int | None
    # 3% of confirmed_amount_cents, rounded -- what the customer must wire to
    # move from PAYMENT_PENDING to CREDITED. None until confirmed_amount_cents
    # is set (i.e. before an admin has verified the document).
    payment_due_cents: int | None
    payment_reference_code: str | None
    status: str
    rejection_reason: str | None
    created_at: datetime
    verified_at: datetime | None
    credited_at: datetime | None


class InvoiceRedemptionUrlRead(BaseModel):
    url: str


class PaymentInfoRead(BaseModel):
    iban: str | None
    holder: str
    instructions: str | None


class InvoiceRedemptionVerifyRequest(BaseModel):
    """Admin confirms what the invoice actually says -- this, not what the
    customer typed at upload, is what the 3% payment and eventual credit are
    computed from."""

    confirmed_amount_cents: int = Field(gt=0)


class InvoiceRedemptionRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
