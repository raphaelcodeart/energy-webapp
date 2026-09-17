"""Pratiche: payment by bank transfer, confirmed by an administrator.

The customer announces the transfer (single payment, the one-go discount
frozen on each contract); an administrator confirms it arrived, which pays
every contract exactly as a card payment would. Optional receipt upload.

Revision ID: c1f6a8b2d537
Revises: b9e5f7a1c426
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1f6a8b2d537"
down_revision: Union[str, None] = "b9e5f7a1c426"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contract_requests", sa.Column("bank_transfer_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contract_requests", sa.Column("bank_transfer_total_cents", sa.BigInteger(), nullable=True))
    op.add_column("contract_requests", sa.Column("bank_transfer_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "contract_requests",
        sa.Column("bank_transfer_confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_contract_requests_bank_transfer_confirmed_by_user_id_users",
        "contract_requests", "users", ["bank_transfer_confirmed_by_user_id"], ["id"],
    )
    op.add_column("contract_requests", sa.Column("payment_proof_storage_key", sa.String(500), nullable=True))
    op.add_column("contract_requests", sa.Column("payment_proof_original_filename", sa.String(255), nullable=True))
    op.add_column("contract_requests", sa.Column("payment_proof_uploaded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_constraint(
        "fk_contract_requests_bank_transfer_confirmed_by_user_id_users", "contract_requests", type_="foreignkey"
    )
    for column in (
        "payment_proof_uploaded_at", "payment_proof_original_filename", "payment_proof_storage_key",
        "bank_transfer_confirmed_by_user_id", "bank_transfer_confirmed_at", "bank_transfer_total_cents",
        "bank_transfer_requested_at",
    ):
        op.drop_column("contract_requests", column)
