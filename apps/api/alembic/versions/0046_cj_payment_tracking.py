"""Shop Lial Partner: the payment to CJ tracked apart from the order on CJ.

Starting with a CJ balance of 0 must not lose or block orders: an order is
created on CJ once, paid from the balance only when the balance covers it,
and otherwise waits as PAYMENT_REQUIRED (payable on CJ's page) without
looking "in preparation". Adds CJ's own identifiers and amounts, the payment
status, and retry bookkeeping. Existing orders already paid on CJ become PAID.

Revision ID: a8d4e6f0b315
Revises: f7c3d5e9a204
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8d4e6f0b315"
down_revision: Union[str, None] = "f7c3d5e9a204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cj_orders", sa.Column("cj_order_code", sa.String(64), nullable=True))
    op.add_column("cj_orders", sa.Column("cj_shipment_order_id", sa.String(64), nullable=True))
    op.add_column("cj_orders", sa.Column("cj_pay_url", sa.String(1000), nullable=True))
    op.add_column(
        "cj_orders", sa.Column("cj_payment_status", sa.String(24), nullable=False, server_default="NOT_REQUIRED")
    )
    op.add_column("cj_orders", sa.Column("cj_product_amount_usd", sa.Numeric(10, 2), nullable=True))
    op.add_column("cj_orders", sa.Column("cj_postage_amount_usd", sa.Numeric(10, 2), nullable=True))
    op.add_column("cj_orders", sa.Column("cj_ioss_amount_usd", sa.Numeric(10, 2), nullable=True))
    op.add_column("cj_orders", sa.Column("cj_paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cj_orders", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("cj_orders", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cj_orders", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cj_orders", sa.Column("last_error_kind", sa.String(24), nullable=True))
    op.create_index("ix_cj_orders_cj_payment_status", "cj_orders", ["cj_payment_status"])
    op.create_index("ix_cj_orders_next_retry_at", "cj_orders", ["next_retry_at"])
    op.execute(
        "UPDATE cj_orders SET cj_payment_status = 'PAID', cj_paid_at = forwarded_at "
        "WHERE fulfillment_status IN ('PROCESSING', 'SHIPPED', 'DELIVERED')"
    )
    op.execute(
        "UPDATE cj_orders SET cj_payment_status = 'PENDING' "
        "WHERE fulfillment_status = 'SENT'"
    )
    # The shop now works hybrid by default: create on CJ at once, pay only
    # when the balance covers it.
    op.execute("UPDATE cj_settings SET auto_forward = true")


def downgrade() -> None:
    op.drop_index("ix_cj_orders_next_retry_at", table_name="cj_orders")
    op.drop_index("ix_cj_orders_cj_payment_status", table_name="cj_orders")
    for column in (
        "last_error_kind", "next_retry_at", "last_attempt_at", "attempt_count", "cj_paid_at",
        "cj_ioss_amount_usd", "cj_postage_amount_usd", "cj_product_amount_usd", "cj_payment_status",
        "cj_pay_url", "cj_shipment_order_id", "cj_order_code",
    ):
        op.drop_column("cj_orders", column)
