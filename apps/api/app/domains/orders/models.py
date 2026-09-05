import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

# AWAITING_PAYMENT -- created, credit discount (if any) already applied, the
#   residual is owed by bank transfer. Reachable from nowhere else -- the
#   starting state whenever residual > 0.
# PAID -- terminal. Either the residual bank transfer was confirmed by an
#   admin, or credit_applied_cents already covered 100% of amount_cents at
#   creation time (no bank transfer needed, order goes straight here).
# CANCELLED -- terminal, reachable only from AWAITING_PAYMENT. Refunds
#   credit_applied_cents (if any) via a REVERSAL of the PURCHASE_DEBIT row --
#   see orders/service.py::cancel_order.
ORDER_STATUSES = ["AWAITING_PAYMENT", "PAID", "CANCELLED"]

# How the residual (amount_cents - credit_applied_cents) gets paid --
# irrelevant when the residual is 0. BANK_TRANSFER: unchanged since Session
# 24, an admin confirms receipt manually (POST /orders/{id}/confirm-payment).
# CARD: added Session 26 (Stripe), the order is marked PAID automatically by
# the Stripe webhook when checkout completes -- no admin action, see
# payments/router.py and orders/service.py::mark_paid_via_stripe().
ORDER_PAYMENT_METHODS = ["BANK_TRANSFER", "CARD"]


class Order(UUIDPKMixin, TimestampMixin, Base):
    """A DROPSHIPPING/PARTNER product purchase (Phase 4 of
    docs/cashback-partner-invoices-plan.md) -- deliberately NOT a Contract:
    Contract.supply_point_id is NOT NULL by design (every contract is an
    energy supply), which a t-shirt or any other partner/dropship item has
    no equivalent of. Self-checkout added Session 26 (POST /orders/mine) --
    an admin can still create one on a customer's behalf too, both paths
    share the same service function."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("credit_applied_cents >= 0", name="ck_orders_credit_applied_non_negative"),
        CheckConstraint("credit_applied_cents <= amount_cents", name="ck_orders_credit_applied_not_over_amount"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    product_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("product_versions.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    # Frozen at creation from product_version.base_price_cents -- same
    # "frozen at the moment it happens" rule as everywhere else in this
    # codebase (network snapshots, commission calculations), so a later
    # price change never rewrites what a past order actually cost.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    credit_applied_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    # Set only when credit_applied_cents > 0 -- points at the PURCHASE_DEBIT
    # row, so cancel_order() can reverse that exact row instead of minting a
    # fresh, less traceable refund credit.
    credit_debit_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallet_transactions.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), default="AWAITING_PAYMENT", index=True)
    payment_method: Mapped[str] = mapped_column(String(16), default="BANK_TRANSFER")
    # Set only for payment_method=CARD once a Stripe Checkout Session has
    # been created for the residual -- the webhook looks an order up by this
    # (via the session's client_reference_id, which is set to this order's
    # id) to mark it PAID. Unique so a session can never be attached to two
    # orders. A new session (e.g. the customer abandoned checkout and wants
    # to retry) overwrites this rather than appending -- only the latest
    # attempt is ever valid.
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    paid_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
