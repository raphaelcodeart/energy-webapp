"""Idempotenza a livello di evento Stripe.

Until now the webhook's only protection against a replay was downstream: the
order/redemption guard (`if status != AWAITING_PAYMENT: return`) plus the
UNIQUE idempotency key on the wallet ledger. That works for the flows that
existed, but it is protection by coincidence -- it holds because every
consequence of an event happened to be idempotent on its own.

Contract subscriptions break that. `invoice.paid` fires every month for the
same subscription, `checkout.session.completed` can be redelivered for days,
and Stripe explicitly does not promise exactly-once delivery. So the event id
itself is now recorded, and an event already processed is acknowledged and
dropped before any handler runs.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class StripeWebhookEvent(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "stripe_webhook_events"
    __table_args__ = (
        # Stripe event ids are globally unique, so this alone is the
        # exactly-once guarantee -- inserted BEFORE the handler runs, so two
        # concurrent deliveries of the same event cannot both get through.
        UniqueConstraint("stripe_event_id", name="uq_stripe_webhook_events_event_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    stripe_event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    #: Set once the handler finished. A row with this still NULL means the
    #: event was received but its processing died -- worth looking at, and
    #: distinguishable from one that completed.
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: Short note about what was done (or why nothing was), for support.
    outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)
