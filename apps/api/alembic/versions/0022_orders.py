"""Phase 4 of the partner-invoice cashback project (see
docs/cashback-partner-invoices-plan.md): DROPSHIPPING/PARTNER product
purchases with an optional wallet-credit discount. Deliberately a new
`orders` table, not an extension of `contracts` -- Contract.supply_point_id
is NOT NULL by design (every contract is an energy supply), which has no
equivalent for e.g. a partner t-shirt.

Also adds wallet_transactions.reference_order_id (the PURCHASE_DEBIT leg of
an order) and the corresponding orders.credit_debit_transaction_id back-
reference -- created in this order specifically so neither FK is dangling
at any point: wallet_transactions already exists (0018), so
credit_debit_transaction_id can reference it immediately; orders is created
before the ALTER on wallet_transactions that references it back.

Revision ID: a1f6e0c92d84
Revises: f7d5b2e6c391
Create Date: 2026-09-05 03:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1f6e0c92d84"
down_revision: Union[str, None] = "f7d5b2e6c391"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("customer_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "product_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_versions.id"), nullable=False
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("credit_applied_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "credit_debit_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallet_transactions.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="AWAITING_PAYMENT"),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("paid_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint("credit_applied_cents >= 0", name="ck_orders_credit_applied_non_negative"),
        sa.CheckConstraint("credit_applied_cents <= amount_cents", name="ck_orders_credit_applied_not_over_amount"),
    )
    op.create_index("ix_orders_organization_id", "orders", ["organization_id"])
    op.create_index("ix_orders_customer_user_id", "orders", ["customer_user_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.add_column(
        "wallet_transactions",
        sa.Column("reference_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wallet_transactions", "reference_order_id")

    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_customer_user_id", table_name="orders")
    op.drop_index("ix_orders_organization_id", table_name="orders")
    op.drop_table("orders")
