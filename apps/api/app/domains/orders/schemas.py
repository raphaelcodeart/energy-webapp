import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrderRead(BaseModel):
    """Built from a service dict row (see service.py::to_read_dict), not
    model_validate(orm_obj) -- product/customer names are resolved joins."""

    id: uuid.UUID
    customer_user_id: uuid.UUID
    customer_display_name: str
    product_version_id: uuid.UUID
    product_name: str
    created_by_user_id: uuid.UUID
    amount_cents: int
    credit_applied_cents: int
    residual_amount_cents: int
    status: str
    note: str | None
    paid_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime


class OrderQuoteRead(BaseModel):
    """What the checkout screen shows before an order is actually created --
    lets the admin see the credit cap and the customer's balance before
    committing to an amount."""

    product_version_id: uuid.UUID
    product_name: str
    amount_cents: int
    credit_discount_percentage: int
    max_creditable_cents: int
    customer_wallet_balance_cents: int


class OrderCreateRequest(BaseModel):
    customer_user_id: uuid.UUID
    product_version_id: uuid.UUID
    # 0 if paying the full amount by bank transfer -- never inferred, an
    # admin always states explicitly how much credit to apply.
    credit_applied_cents: int = Field(default=0, ge=0)
    note: str | None = Field(default=None, max_length=1000)


class OrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
