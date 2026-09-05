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
    payment_method: str
    note: str | None
    paid_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime


class OrderQuoteRead(BaseModel):
    """What the checkout screen shows before an order is actually created --
    lets the buyer (customer self-checkout or admin) see the credit cap, the
    customer's balance, and which payment methods for the residual are even
    switched on before committing to anything. A frontend must grey out or
    hide "Paga con bonifico"/"Paga con carta" entirely when the matching flag
    is false -- the backend enforces this too (create_order rejects an
    unavailable method), this is what lets the UI never offer it in the
    first place."""

    product_version_id: uuid.UUID
    product_name: str
    amount_cents: int
    credit_discount_percentage: int
    max_creditable_cents: int
    customer_wallet_balance_cents: int
    bank_transfer_available: bool
    card_available: bool


class OrderCreateRequest(BaseModel):
    customer_user_id: uuid.UUID
    product_version_id: uuid.UUID
    # 0 if the credit discount alone covers the price -- never inferred, the
    # caller always states explicitly how much credit to apply.
    credit_applied_cents: int = Field(default=0, ge=0)
    # Only meaningful when credit_applied_cents < amount_cents -- see
    # ORDER_PAYMENT_METHODS. Ignored (order goes straight to PAID) when
    # credit covers 100%.
    payment_method: str = "BANK_TRANSFER"
    note: str | None = Field(default=None, max_length=1000)


class OrderSelfCreateRequest(BaseModel):
    """Same as OrderCreateRequest minus customer_user_id -- self-checkout
    (POST /orders/mine) always forces the caller's own user_id server-side,
    never accepts it from the body (same rule as wallet transfer's
    from_wallet_id)."""

    product_version_id: uuid.UUID
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    note: str | None = Field(default=None, max_length=1000)


class OrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CheckoutSessionRead(BaseModel):
    checkout_url: str
