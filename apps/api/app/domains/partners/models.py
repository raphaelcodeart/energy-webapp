import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class Partner(UUIDPKMixin, TimestampMixin, Base):
    """An external energy supplier Lial Energy brokers for (e.g. Eviso) --
    NOT a Lial product. A customer who already pays one of these directly
    can redeem part of that spend as internal wallet credit by uploading
    proof of payment; see invoice_redemptions.models.InvoiceRedemption. Kept
    deliberately tiny (name + logo) -- see docs/cashback-partner-invoices-plan.md
    for whether richer fields (contact, commission split) are wanted later."""

    __tablename__ = "partners"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_partners_organization_name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
