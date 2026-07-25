import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class DomainOutbox(UUIDPKMixin, TimestampMixin, Base):
    """Transactional outbox (ADR 0005): critical domain events are written here in
    the SAME transaction as the state change they describe, and only published
    (processed) after that transaction has committed. Guarantees no event fires for
    a change that rolled back, and no committed change silently fails to notify."""

    __tablename__ = "domain_outbox"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
