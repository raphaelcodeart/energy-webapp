"""Idempotenza degli eventi webhook Stripe.

Until now the webhook's only protection against a replay was downstream: a
status guard on the order/redemption plus the UNIQUE idempotency key on the
wallet ledger. That worked for the flows that existed, but only because every
consequence of an event happened to be idempotent on its own.

Contract instalment plans break that. `invoice.paid` fires every month for the
same subscription, `checkout.session.completed` can be redelivered for days,
and Stripe promises at-least-once delivery, not exactly-once -- so "the same
event again" and "the next instalment" had to stop being indistinguishable.

The event id is now recorded BEFORE any handler runs, and the UNIQUE
constraint decides which of two concurrent deliveries proceeds.

Revision ID: e5b2c74a91d8
Revises: d9a04b7e13c5
Create Date: 2026-09-14 14:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5b2c74a91d8"
down_revision: Union[str, None] = "d9a04b7e13c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_stripe_webhook_events"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_stripe_webhook_events_organization_id_organizations",
        ),
        # Stripe event ids are globally unique: this constraint IS the
        # exactly-once guarantee.
        sa.UniqueConstraint("stripe_event_id", name="uq_stripe_webhook_events_event_id"),
    )
    op.create_index("ix_stripe_webhook_events_organization_id", "stripe_webhook_events", ["organization_id"])
    op.create_index("ix_stripe_webhook_events_event_type", "stripe_webhook_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("stripe_webhook_events")
