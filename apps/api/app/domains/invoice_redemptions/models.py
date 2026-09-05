import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

# SUBMITTED -- customer uploaded proof of payment, waiting for an admin to
#   look at it. confirmed_amount_cents and payment_reference_code are NULL.
# PAYMENT_PENDING -- an admin verified the document and confirmed the real
#   amount (confirmed_amount_cents set, payment_reference_code generated).
#   The customer now knows how much to wire (3% of confirmed_amount_cents)
#   and where to put the reference code.
# CREDITED -- terminal. An admin confirmed the 3% bank transfer arrived; the
#   wallet has been credited with exactly two rows (base + bonus), both
#   tagged with this row's id -- see service.py::confirm_payment().
# REJECTED -- terminal, reachable from SUBMITTED or PAYMENT_PENDING.
INVOICE_REDEMPTION_STATUSES = ["SUBMITTED", "PAYMENT_PENDING", "CREDITED", "REJECTED"]

# Both the redemption's base credit and its bonus, as a percentage of the
# confirmed invoice amount -- e.g. a 100,00E invoice yields a 3,00E payment
# request and, once confirmed, a 103,00E credit (100 base + 3 bonus). A
# single constant because today the "pay X% to redeem, get 100%+X% back"
# structure uses the same figure for both halves; if that's ever decoupled,
# split into REDEMPTION_PAYMENT_PERCENTAGE and REDEMPTION_BONUS_PERCENTAGE.
CASHBACK_PERCENTAGE = 3

ALLOWED_INVOICE_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_INVOICE_BYTES = 15 * 1024 * 1024  # a phone photo of a bill, not a video


class InvoiceRedemption(UUIDPKMixin, TimestampMixin, Base):
    """A customer's claim to redeem, as internal wallet credit, part of what
    they already paid an external energy supplier Lial brokers for (a
    Partner -- e.g. Eviso). Deliberately NOT stored in the `documents` table:
    that table's contract_id is NOT NULL by design (it's for KYC/utility
    documents attached to a Lial contract), and a redemption has no Lial
    contract behind it at all -- this row carries its own storage_key instead,
    reusing core/storage.py's private-bucket upload/presign functions
    directly. See docs/cashback-partner-invoices-plan.md for the full design
    and docs/business-rules.md#internal-wallet for the anti-loop principle
    this whole flow exists to respect (credit is only ever minted against a
    real, admin-confirmed bank transfer -- never against spending credit)."""

    __tablename__ = "invoice_redemptions"
    __table_args__ = (
        CheckConstraint(
            "confirmed_amount_cents IS NULL OR confirmed_amount_cents > 0",
            name="ck_invoice_redemptions_confirmed_amount_positive",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("partners.id"))

    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)

    # What the customer typed in when uploading -- never trusted on its own,
    # only a starting point for the admin's own reading of the document.
    declared_amount_cents: Mapped[int] = mapped_column(BigInteger)
    # Set only once an admin has actually looked at the document -- this,
    # not declared_amount_cents, is what the 3% payment and eventual credit
    # are computed from.
    confirmed_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Short human-typeable code the customer is told to put in the bank
    # transfer's causale, generated the moment confirmed_amount_cents is set
    # -- lets an admin match an incoming wire to this exact redemption
    # without relying on matching a euro amount that many customers could
    # share on the same day.
    payment_reference_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)

    status: Mapped[str] = mapped_column(String(16), default="SUBMITTED", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    credited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    credited_at: Mapped[datetime | None] = mapped_column(nullable=True)
