import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

# What a notification is ABOUT -- drives which sidebar nav item gets the
# unread dot on the frontend (see app-shell.tsx NOTIFICATION_NAV_MAP) and
# which icon/label the bell dropdown shows.
NOTIFICATION_TYPES = {
    "CONTRACT_CREATED",
    "TICKET_CREATED",
    "PROMOTER_APPROVAL_REQUESTED",
    "PROMOTER_APPROVED",
    "PROMOTER_REJECTED",
    "COMMISSION_EARNED",
}


class Notification(UUIDPKMixin, TimestampMixin, Base):
    """Per-recipient-user row (not per-role) -- fanned out at creation time by
    notifications/service.py::notify_staff() so read/unread state is tracked
    correctly per person even when several admins share the same role. See
    docs/business-rules.md#notifications."""

    __tablename__ = "notifications"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    type: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
