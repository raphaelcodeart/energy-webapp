import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domains.marketplaces.rules import MAX_CREDIT_PERCENTAGE


class ShopifySettingsRead(BaseModel):
    """The access token is never returned: only whether one is saved and its
    last four characters, as for the Stripe keys."""

    shop_domain: str | None
    access_token_configured: bool
    access_token_hint: str | None
    api_version: str
    enabled: bool
    shop_name: str | None
    shop_currency: str | None
    currency_rate: float
    price_basis: str
    markup_percentage: int
    markup_fixed_cents: int
    price_rounding: str
    shipping_mode: str
    shipping_flat_cents: int
    shipping_days: str | None
    default_credit_percentage: int
    max_credit_percentage: int
    auto_forward: bool
    last_connected_at: datetime | None


class ShopifySettingsUpdate(BaseModel):
    """Only the fields sent are changed: a PATCH that moves the markup never
    blanks the stored token."""

    shop_domain: str | None = Field(default=None, max_length=255)
    access_token: str | None = Field(default=None, max_length=255)
    api_version: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    enabled: bool | None = None
    currency_rate: float | None = Field(default=None, gt=0.001, lt=1000)
    price_basis: str | None = None
    markup_percentage: int | None = Field(default=None, ge=0, le=1000)
    markup_fixed_cents: int | None = Field(default=None, ge=0, le=100000)
    price_rounding: str | None = None
    shipping_mode: str | None = None
    shipping_flat_cents: int | None = Field(default=None, ge=0, le=100000)
    shipping_days: str | None = Field(default=None, max_length=32)
    default_credit_percentage: int | None = Field(default=None, ge=0, le=MAX_CREDIT_PERCENTAGE)
    auto_forward: bool | None = None


class ShopifyImportRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=MAX_CREDIT_PERCENTAGE)
    markup_percentage: int | None = Field(default=None, ge=0, le=1000)
    variant_ids: list[str] | None = None
    activate: bool = True


class ShopifyProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    image_url: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=MAX_CREDIT_PERCENTAGE)
    markup_percentage: int | None = Field(default=None, ge=0, le=1000)


class ShopifyVariantUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    active: bool | None = None
    price_override_cents: int | None = Field(default=None, gt=0)


class ShopifyAddress(BaseModel):
    recipient_name: str = Field(min_length=2, max_length=50)
    recipient_phone: str = Field(min_length=6, max_length=20)
    address_line1: str = Field(min_length=3, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=50)
    province: str = Field(min_length=1, max_length=50)
    postal_code: str = Field(min_length=3, max_length=12)


class ShopifyOrderCreditOtpRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    credit_applied_cents: int = Field(gt=0)


class ShopifyOrderSelfCreateRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    address: ShopifyAddress
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class ShopifyOrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ShopifyOrderPaymentMethodUpdate(BaseModel):
    payment_method: str


class CheckoutSessionRead(BaseModel):
    checkout_url: str


class PaymentProofUrlRead(BaseModel):
    url: str
