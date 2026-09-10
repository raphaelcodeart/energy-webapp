import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ImportProviderCreate(BaseModel):
    provider_type: str
    name: str = Field(min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = True


class ImportProviderUpdate(BaseModel):
    """All optional -- only fields actually present in the request overwrite
    (exclude_unset, same discipline as organizations/service.py::
    update_payment_settings), so leaving api_key out of a PATCH that's only
    renaming the provider never blanks out an already-stored key."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class ImportProviderRead(BaseModel):
    """api_key is never returned raw -- same masked-last4 convention as
    organizations/service.py::get_payment_settings's Stripe secret key."""

    id: uuid.UUID
    provider_type: str
    name: str
    base_url: str | None
    api_key_configured: bool
    api_key_last4: str | None
    enabled: bool
    created_at: datetime


class ImportedProductCreate(BaseModel):
    provider_id: uuid.UUID
    external_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = Field(default=None, max_length=1000)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    image_url: str | None = Field(default=None, max_length=1000)
    price_cents: int = Field(gt=0)
    credit_discount_percentage: int = Field(default=0, ge=0, le=100)
    status: str = "ACTIVE"


class ImportedProductUpdate(BaseModel):
    external_id: str | None = Field(default=None, max_length=255)
    external_url: str | None = Field(default=None, max_length=1000)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=1000)
    price_cents: int | None = Field(default=None, gt=0)
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=100)
    status: str | None = None


class ImportedProductAdminRead(BaseModel):
    """Full detail, including the provider/external linkage -- admin catalog
    view only. See ImportedProductRead for the customer-facing shape."""

    id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str
    external_id: str | None
    external_url: str | None
    name: str
    description: str
    image_url: str | None
    price_cents: int
    credit_discount_percentage: int
    status: str
    created_at: datetime


class ImportedProductRead(BaseModel):
    """Customer-facing shop card -- deliberately omits provider_id/
    external_id/external_url, so nothing in the API response hints these
    are AliExpress-sourced items (see models.py::ImportedProduct's
    docstring)."""

    id: uuid.UUID
    name: str
    description: str
    image_url: str | None
    price_cents: int
    credit_discount_percentage: int


class ImportedOrderRead(BaseModel):
    """Same shape as orders/schemas.py::OrderRead minus every cashback
    field -- an imported-product order never has one."""

    id: uuid.UUID
    customer_user_id: uuid.UUID
    customer_display_name: str
    imported_product_id: uuid.UUID
    product_name: str
    product_image_url: str | None = None
    created_by_user_id: uuid.UUID
    amount_cents: int
    credit_applied_cents: int
    residual_amount_cents: int
    status: str
    payment_method: str
    stripe_checkout_session_id: str | None = None
    payment_proof_uploaded_at: datetime | None = None
    note: str | None
    paid_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime


class ImportedOrderQuoteRead(BaseModel):
    imported_product_id: uuid.UUID
    product_name: str
    amount_cents: int
    credit_discount_percentage: int
    max_creditable_cents: int
    customer_wallet_balance_cents: int
    bank_transfer_available: bool
    card_available: bool


class ImportedOrderCreateRequest(BaseModel):
    customer_user_id: uuid.UUID
    imported_product_id: uuid.UUID
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    note: str | None = Field(default=None, max_length=1000)


class ImportedOrderSelfCreateRequest(BaseModel):
    imported_product_id: uuid.UUID
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class ImportedOrderCreditOtpRequest(BaseModel):
    imported_product_id: uuid.UUID
    credit_applied_cents: int = Field(gt=0)


class ImportedOrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ImportedOrderPaymentMethodUpdate(BaseModel):
    payment_method: str


class PaymentProofUrlRead(BaseModel):
    url: str


class CheckoutSessionRead(BaseModel):
    checkout_url: str
