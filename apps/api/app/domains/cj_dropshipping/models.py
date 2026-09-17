"""Shop Lial Partner: the CJ Dropshipping integration (Session 60).

A third, fully separate catalog source next to the Shop's own products and
the "Acquisti LialEnergy" imported-products plugin (AliExpress). Separate
tables on purpose, same reasoning as imported_products: nothing here touches
catalog.products, orders or imported_products, so the whole feature can be
switched off or removed without disturbing what already works.

Unlike the AliExpress plugin, which is a hand-filled catalog, this one talks
to CJ's real API: products are searched and imported from CJ with their
variants, priced from CJ's USD cost by the administrator's rules, and a paid
order is sent to CJ, paid from the CJ balance, and followed until delivery
with its tracking number.

To the customer it is simply another Shop tab ("Shop Lial Partner"): same
checkout, same LialCash spending, same "I miei Ordini" and Contabilità as
every other purchase. A purchase here only ever SPENDS LialCash, it never
generates cashback -- same rule as the AliExpress plugin.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

#: How the price a customer pays is rounded: up to x,90 / x,99, or not at all.
PRICE_ROUNDINGS = ("90", "99", "NONE")
#: Who pays the shipping CJ charges: added at checkout, or built into the price.
SHIPPING_MODES = ("CUSTOMER_PAYS", "INCLUDED")

CJ_PRODUCT_STATUSES = ("ACTIVE", "INACTIVE")

CJ_ORDER_STATUSES = ("AWAITING_PAYMENT", "PAID", "CANCELLED")
CJ_ORDER_PAYMENT_METHODS = ("BANK_TRANSFER", "CARD")

#: What happened to a paid order on CJ's side.
#:   NOT_SENT      -- paid (or awaiting payment), not sent to CJ yet
#:   SENDING       -- claimed by one sender; nobody else may send it
#:   SENT          -- order created on CJ, not paid there yet
#:   PROCESSING    -- paid on CJ, being prepared (CJ: UNSHIPPED)
#:   SHIPPED       -- in transit, tracking number known
#:   DELIVERED     -- delivered
#:   ERROR         -- CJ refused it (balance, stock, address...): see forward_error
#:   CJ_CANCELLED  -- cancelled on CJ
FULFILLMENT_STATUSES = (
    "NOT_SENT", "SENDING", "SENT", "PROCESSING", "SHIPPED", "DELIVERED", "ERROR", "CJ_CANCELLED",
)


class CjSettings(UUIDPKMixin, TimestampMixin, Base):
    """The CJ account and the pricing rules of an organization -- one row.

    Its own table rather than keys on organizations.settings: it holds a
    token pair that is rotated by the integration itself, not only typed by
    an administrator, and the pricing rules are typed numbers. `api_key` and
    the tokens are never returned by any endpoint (masked, like Stripe's)."""

    __tablename__ = "cj_settings"
    __table_args__ = (UniqueConstraint("organization_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: CJ's account id, returned with the token; also the webhook signing secret.
    open_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The customer-facing shop tab is shown only when enabled.
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Orders sent to CJ as sandbox orders: nothing is charged or shipped.
    #: On by default, so the first orders of a new setup are rehearsals.
    sandbox: Mapped[bool] = mapped_column(Boolean, default=True)
    #: EUR per 1 USD.
    usd_eur_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.92"))
    markup_percentage: Mapped[int] = mapped_column(Integer, default=100)
    markup_fixed_cents: Mapped[int] = mapped_column(Integer, default=0)
    price_rounding: Mapped[str] = mapped_column(String(8), default="90")
    shipping_mode: Mapped[str] = mapped_column(String(16), default="CUSTOMER_PAYS")
    #: Default "pagabile in LialCash" percentage of a newly imported product.
    default_credit_percentage: Mapped[int] = mapped_column(Integer, default=100)
    destination_country: Mapped[str] = mapped_column(String(2), default="IT")
    #: Send a paid order to CJ (and pay it from the CJ balance) by itself.
    auto_forward: Mapped[bool] = mapped_column(Boolean, default=False)
    last_balance_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    last_balance_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CjProduct(UUIDPKMixin, TimestampMixin, Base):
    """A CJ product the administrator chose to sell, with the Italian name and
    description they gave it. Prices live on the variants."""

    __tablename__ = "cj_products"
    __table_args__ = (UniqueConstraint("organization_id", "cj_pid"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    cj_pid: Mapped[str] = mapped_column(String(64))
    cj_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    #: CJ's own (English) name, kept to recognize the product on CJ.
    name_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str] = mapped_column(String(8000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    images: Mapped[list] = mapped_column(JSONB, default=list)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Where CJ ships it from (CN, US, DE...), chosen at import from its stock.
    origin_country: Mapped[str] = mapped_column(String(2), default="CN")
    #: The cheapest shipping estimate to the destination, at the last sync.
    shipping_estimate_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=100)
    #: Overrides the organization's markup for this product only.
    markup_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sync_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CjVariant(UUIDPKMixin, TimestampMixin, Base):
    """One buyable version of a product (colour, size...). `cost_usd` is what
    CJ charges; `price_cents` is what the customer pays, recomputed from the
    pricing rules at every sync unless `price_override_cents` is set."""

    __tablename__ = "cj_variants"
    __table_args__ = (UniqueConstraint("product_id", "cj_vid"),)

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cj_products.id"), index=True)
    cj_vid: Mapped[str] = mapped_column(String(64))
    cj_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    weight_g: Mapped[int] = mapped_column(Integer, default=0)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    price_override_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    inventory: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Still offered by CJ at the last sync.
    available_on_cj: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CjOrder(UUIDPKMixin, TimestampMixin, Base):
    """A customer's purchase of one variant (in some quantity), mirroring the
    checkout of the other shops -- LialCash with OTP, card or transfer for the
    rest -- plus what only a real dropshipping order has: a delivery address,
    a shipping cost, and its life on CJ until delivery.

    Every amount is frozen when the order is placed, together with the CJ
    cost and exchange rate it was priced from, so the margin of each order can
    be read back later."""

    __tablename__ = "cj_orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="credit_applied_not_over_amount"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    cj_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cj_products.id"))
    cj_variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cj_variants.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    shipping_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    #: unit_price_cents x quantity + shipping_cents.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    credit_applied_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    credit_debit_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallet_transactions.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), default="AWAITING_PAYMENT", index=True)
    payment_method: Mapped[str] = mapped_column(String(16), default="BANK_TRANSFER")
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payment_proof_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_proof_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_proof_uploaded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Consegna ---
    recipient_name: Mapped[str] = mapped_column(String(128))
    recipient_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address_line1: Mapped[str] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(128))
    province: Mapped[str] = mapped_column(String(64))
    postal_code: Mapped[str] = mapped_column(String(16))
    country_code: Mapped[str] = mapped_column(String(2), default="IT")
    logistic_name: Mapped[str] = mapped_column(String(64))
    origin_country: Mapped[str] = mapped_column(String(2), default="CN")
    shipping_days: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- Costo CJ al momento dell'ordine ---
    unit_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    shipping_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal(0))
    usd_eur_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6))

    # --- Vita su CJ ---
    fulfillment_status: Mapped[str] = mapped_column(String(16), default="NOT_SENT", index=True)
    sandbox: Mapped[bool] = mapped_column(Boolean, default=False)
    cj_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    cj_order_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cj_amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    forwarded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    forwarded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    forward_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_cj_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
