import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CjSettingsRead(BaseModel):
    """The API key is never returned: only whether one is saved and its last
    four characters, as for the Stripe keys."""

    api_key_configured: bool
    api_key_hint: str | None
    connected: bool
    token_expires_at: datetime | None
    enabled: bool
    sandbox: bool
    usd_eur_rate: float
    markup_percentage: int
    markup_fixed_cents: int
    price_rounding: str
    shipping_mode: str
    default_credit_percentage: int
    destination_country: str
    auto_forward: bool
    last_balance_usd: float | None
    last_balance_at: datetime | None


class CjSettingsUpdate(BaseModel):
    """Only the fields sent are changed: a PATCH that moves the markup never
    blanks the stored key."""

    api_key: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None
    sandbox: bool | None = None
    usd_eur_rate: float | None = Field(default=None, gt=0.1, lt=10)
    markup_percentage: int | None = Field(default=None, ge=0, le=1000)
    markup_fixed_cents: int | None = Field(default=None, ge=0, le=100000)
    price_rounding: str | None = None
    shipping_mode: str | None = None
    default_credit_percentage: int | None = Field(default=None, ge=0, le=100)
    auto_forward: bool | None = None


class CjImportRequest(BaseModel):
    pid: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=100)
    markup_percentage: int | None = Field(default=None, ge=0, le=1000)
    vids: list[str] | None = None
    activate: bool = True


class CjProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    image_url: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=100)
    markup_percentage: int | None = Field(default=None, ge=0, le=1000)


class CjVariantUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    active: bool | None = None
    price_override_cents: int | None = Field(default=None, gt=0)


class CjAddress(BaseModel):
    recipient_name: str = Field(min_length=2, max_length=50)
    recipient_phone: str = Field(min_length=6, max_length=20)
    address_line1: str = Field(min_length=3, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=50)
    province: str = Field(min_length=1, max_length=50)
    postal_code: str = Field(min_length=3, max_length=12)


class CjOrderCreditOtpRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    credit_applied_cents: int = Field(gt=0)


class CjOrderSelfCreateRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)
    address: CjAddress
    credit_applied_cents: int = Field(default=0, ge=0)
    payment_method: str = "BANK_TRANSFER"
    otp_code: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class CjOrderCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CjOrderPaymentMethodUpdate(BaseModel):
    payment_method: str


class CheckoutSessionRead(BaseModel):
    checkout_url: str


class PaymentProofUrlRead(BaseModel):
    url: str
