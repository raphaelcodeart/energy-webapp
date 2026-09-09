"""Adds a real payment channel to invoice redemption's "pay X% to redeem"
step (previously bank-transfer-with-reference-code only, manually reconciled,
no self-service card option and no proof upload) -- brings it to parity with
orders/models.py's payment_method/stripe_checkout_session_id/payment_proof_*
columns, added Session 30. See invoice_redemptions/service.py::
create_checkout_session_for_redemption and ::upload_payment_proof.

Revision ID: 6c1d4e9f2a58
Revises: 5f8b3c1a9d47
Create Date: 2026-09-09 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6c1d4e9f2a58"
down_revision: Union[str, None] = "5f8b3c1a9d47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoice_redemptions", sa.Column("payment_method", sa.String(length=16), nullable=True))
    op.add_column(
        "invoice_redemptions", sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True)
    )
    op.create_unique_constraint(
        "uq_invoice_redemptions_stripe_checkout_session_id", "invoice_redemptions", ["stripe_checkout_session_id"]
    )
    op.add_column(
        "invoice_redemptions", sa.Column("payment_proof_storage_key", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "invoice_redemptions", sa.Column("payment_proof_original_filename", sa.String(length=255), nullable=True)
    )
    op.add_column("invoice_redemptions", sa.Column("payment_proof_uploaded_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("invoice_redemptions", "payment_proof_uploaded_at")
    op.drop_column("invoice_redemptions", "payment_proof_original_filename")
    op.drop_column("invoice_redemptions", "payment_proof_storage_key")
    op.drop_constraint(
        "uq_invoice_redemptions_stripe_checkout_session_id", "invoice_redemptions", type_="unique"
    )
    op.drop_column("invoice_redemptions", "stripe_checkout_session_id")
    op.drop_column("invoice_redemptions", "payment_method")
