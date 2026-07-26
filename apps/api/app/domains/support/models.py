import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

TICKET_CATEGORIES = {"ASSISTENZA_TECNICA", "FATTURAZIONE", "CONTRATTO", "COMMISSIONI", "ALTRO"}
TICKET_STATUSES = {"OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"}
TICKET_OPENER_ROLES = {"CUSTOMER", "PROMOTER"}


class Ticket(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "tickets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    opened_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    # Snapshot, not derived at read time -- a role change later must not rewrite
    # who a ticket "belongs to" for visibility purposes (same pattern as
    # network snapshots / commission calculations elsewhere in this codebase).
    opened_by_role: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(32), default="ALTRO")
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    # Optional: lets a customer/promoter open a ticket directly "about this
    # contract" so the admin doesn't have to go hunting for context.
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=True
    )


class TicketMessage(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "ticket_messages"

    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id"), index=True)
    author_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    # Snapshot for the same reason as Ticket.opened_by_role -- "who replied as
    # what" must never change retroactively.
    author_role: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
