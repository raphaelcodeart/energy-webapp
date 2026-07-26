"""add contract_duration_months to product_versions, activated_at/expires_at
to contracts, label to supply_points

Revision ID: 7d3f9a1c6e82
Revises: 5c8e2f4a1d7b
Create Date: 2026-07-26 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d3f9a1c6e82"
down_revision: Union[str, None] = "5c8e2f4a1d7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_versions",
        sa.Column("contract_duration_months", sa.Integer(), nullable=True, server_default="12"),
    )
    op.add_column("contracts", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contracts", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_contracts_expires_at"), "contracts", ["expires_at"], unique=False)
    op.add_column("supply_points", sa.Column("label", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("supply_points", "label")
    op.drop_index(op.f("ix_contracts_expires_at"), table_name="contracts")
    op.drop_column("contracts", "expires_at")
    op.drop_column("contracts", "activated_at")
    op.drop_column("product_versions", "contract_duration_months")
