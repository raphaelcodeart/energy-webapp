"""Adds `orders.payment_proof_storage_key` / `payment_proof_original_filename`
/ `payment_proof_uploaded_at` -- lets a customer paying by bank transfer
attach a photo/PDF of the transfer receipt as extra evidence for the admin
deciding whether to confirm payment (POST /orders/{id}/confirm-payment).
Purely advisory: uploading a proof never changes order.status by itself.
All three columns nullable, no backfill needed for existing orders.

Revision ID: 4a70856b8dd9
Revises: d74478f46f4c
Create Date: 2026-09-09 00:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4a70856b8dd9"
down_revision: Union[str, None] = "d74478f46f4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_proof_storage_key", sa.String(length=500), nullable=True))
    op.add_column("orders", sa.Column("payment_proof_original_filename", sa.String(length=255), nullable=True))
    op.add_column("orders", sa.Column("payment_proof_uploaded_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "payment_proof_uploaded_at")
    op.drop_column("orders", "payment_proof_original_filename")
    op.drop_column("orders", "payment_proof_storage_key")
