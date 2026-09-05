"""Phases 1-2 of the partner-invoice cashback project (see
docs/cashback-partner-invoices-plan.md): the invoice_redemptions table
itself, plus the two columns wallet_transactions needs to link back to it
and tag WHY an ADMIN_CREDIT row exists (source).

Revision ID: f7d5b2e6c391
Revises: e2c8a913f047
Create Date: 2026-09-05 02:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7d5b2e6c391"
down_revision: Union[str, None] = "e2c8a913f047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invoice_redemptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("customer_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("partners.id"), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("declared_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("confirmed_amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("payment_reference_code", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="SUBMITTED"),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credited_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("storage_key", name="uq_invoice_redemptions_storage_key"),
        sa.UniqueConstraint("payment_reference_code", name="uq_invoice_redemptions_payment_reference_code"),
        sa.CheckConstraint(
            "confirmed_amount_cents IS NULL OR confirmed_amount_cents > 0",
            name="ck_invoice_redemptions_confirmed_amount_positive",
        ),
    )
    op.create_index("ix_invoice_redemptions_organization_id", "invoice_redemptions", ["organization_id"])
    op.create_index("ix_invoice_redemptions_customer_user_id", "invoice_redemptions", ["customer_user_id"])
    op.create_index("ix_invoice_redemptions_status", "invoice_redemptions", ["status"])

    op.add_column("wallet_transactions", sa.Column("source", sa.String(length=32), nullable=True))
    op.add_column(
        "wallet_transactions",
        sa.Column(
            "reference_invoice_redemption_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoice_redemptions.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("wallet_transactions", "reference_invoice_redemption_id")
    op.drop_column("wallet_transactions", "source")

    op.drop_index("ix_invoice_redemptions_status", table_name="invoice_redemptions")
    op.drop_index("ix_invoice_redemptions_customer_user_id", table_name="invoice_redemptions")
    op.drop_index("ix_invoice_redemptions_organization_id", table_name="invoice_redemptions")
    op.drop_table("invoice_redemptions")
