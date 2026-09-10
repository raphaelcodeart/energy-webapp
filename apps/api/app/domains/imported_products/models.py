import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

# Extend this list when a second dropshipping/API source is added -- the
# admin config screen (POST /imported-products/providers) reads it to
# populate its "tipo di servizio" dropdown. Not an enforced DB constraint
# (a String column, same "flat list an admin/data-migration can extend
# without a code deploy" reasoning as rbac/models.py::PERMISSIONS), so
# adding a new value here alone is enough for it to become selectable.
IMPORT_PROVIDER_TYPES = ["ALIEXPRESS"]


class ImportProvider(UUIDPKMixin, TimestampMixin, Base):
    """A configured external catalog source (Session 34's "plugin" system
    for the Shop's 'Acquisti LialEnergy' subcategory -- see
    docs/cashback-partner-invoices-plan.md). Deliberately its own table, not
    a few more keys on Organization.settings like Stripe's -- an org can
    have several of these (one per supplier/API), unlike the single Stripe
    account. api_key is never returned raw by any endpoint (see
    service.py::to_provider_read_dict, same masking convention as
    organizations/service.py::get_payment_settings)."""

    __tablename__ = "import_providers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    provider_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class ImportedProduct(UUIDPKMixin, TimestampMixin, Base):
    """One item in the imported catalog -- visually a normal Shop product to
    the customer (never labelled "AliExpress" anywhere customer-facing), but
    intentionally NOT a row in catalog.products: keeping the two tables
    separate is what lets this whole feature be added/removed without ever
    touching Product/ProductVersion or anything that already depends on
    them (contracts, commissions, the admin catalog). For now added/edited
    by hand from the admin panel; external_id/external_url exist so a real
    provider sync can match/dedupe against them later without a schema
    change. Never offers cashback-on-purchase (unlike a DROPSHIPPING/
    PARTNER Product -- see catalog/models.py::ProductVersion.cashback_enabled):
    these products only ever let a customer spend existing LialCash, never
    mint new cashback, so there is no cashback_enabled column here at all."""

    __tablename__ = "imported_products"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("import_providers.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Admin-only reference to the original listing -- never sent to the
    # customer-facing read schema.
    external_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(2000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    # 0-100: same meaning/enforcement point as
    # catalog/models.py::ProductVersion.credit_discount_percentage -- how
    # much of price_cents a customer may pay from wallet LialCash instead of
    # bank transfer/card.
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")  # ACTIVE / INACTIVE
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


# Same three-state lifecycle as orders/models.py::ORDER_STATUSES, same
# meaning -- kept as its own list rather than importing the orders one so
# this domain stays a self-contained plugin with zero import coupling to
# `orders`.
IMPORTED_ORDER_STATUSES = ["AWAITING_PAYMENT", "PAID", "CANCELLED"]
IMPORTED_ORDER_PAYMENT_METHODS = ["BANK_TRANSFER", "CARD"]


class ImportedProductOrder(UUIDPKMixin, TimestampMixin, Base):
    """Mirrors orders/models.py::Order's checkout mechanics exactly (credit
    discount, OTP-gated self-checkout, bank transfer/card residual, Stripe
    webhook confirmation, payment-proof upload) but for an ImportedProduct
    instead of a ProductVersion, and with no cashback fields at all: an
    imported-product purchase only ever consumes LialCash, it never
    generates any (see ImportedProduct's docstring) -- the parallel "system
    a customer burns cashback in" the user asked for, deliberately isolated
    from the real `orders` table so this whole feature stays removable
    without touching anything that already works."""

    __tablename__ = "imported_product_orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="ck_imported_orders_credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="ck_imported_orders_credit_applied_not_over_amount"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    imported_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("imported_products.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

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
