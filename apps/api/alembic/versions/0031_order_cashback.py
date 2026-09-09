""""Riscuoti subito cashback" on a product order: an admin-toggleable flag per
product version (product_versions.cashback_enabled, same INTERNAL-forced-
False rule as credit_discount_percentage) lets a customer opt, at checkout,
to pay a fixed 5% surcharge on top of whatever they actually owe in new
money -- see orders/service.py::ORDER_CASHBACK_PERCENTAGE. Once the order is
confirmed PAID (bank transfer admin-confirmed, or Stripe webhook), the whole
extra payment (100% + 5%) is credited back to the customer's wallet as
LialCash. orders.cashback_surcharge_cents is frozen at order creation, same
"frozen at the moment it happens" rule as orders.amount_cents.

Revision ID: 5f8b3c1a9d47
Revises: 4a70856b8dd9
Create Date: 2026-09-09 00:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5f8b3c1a9d47"
down_revision: Union[str, None] = "4a70856b8dd9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_versions",
        sa.Column("cashback_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "orders",
        sa.Column("cashback_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "orders",
        sa.Column("cashback_surcharge_cents", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column("orders", sa.Column("cashback_credited_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "cashback_credited_at")
    op.drop_column("orders", "cashback_surcharge_cents")
    op.drop_column("orders", "cashback_requested")
    op.drop_column("product_versions", "cashback_enabled")
