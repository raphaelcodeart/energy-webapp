"""Adds payment_method (BANK_TRANSFER/CARD) and stripe_checkout_session_id
to orders -- lets a self-checkout customer choose how to pay the residual
after any credit discount, and lets the Stripe webhook find the right order
to mark PAID. See app/domains/payments/ and
docs/cashback-partner-invoices-plan.md.

Revision ID: d6f3b8a1c574
Revises: c5a8d217e930
Create Date: 2026-09-05 06:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6f3b8a1c574"
down_revision: Union[str, None] = "c5a8d217e930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("payment_method", sa.String(length=16), nullable=False, server_default="BANK_TRANSFER"),
    )
    op.add_column(
        "orders",
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_orders_stripe_checkout_session_id", "orders", ["stripe_checkout_session_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_orders_stripe_checkout_session_id", "orders", type_="unique")
    op.drop_column("orders", "stripe_checkout_session_id")
    op.drop_column("orders", "payment_method")
