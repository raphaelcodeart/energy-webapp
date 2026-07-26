"""add product_type to products, make energy_type nullable, add notes to
contracts, add pec to customers

Revision ID: 5c8e2f4a1d7b
Revises: 3f7c1a9b2e6d
Create Date: 2026-07-26 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c8e2f4a1d7b"
down_revision: Union[str, None] = "3f7c1a9b2e6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("product_type", sa.String(length=32), nullable=False, server_default="ENERGY_CONTRACT"),
    )
    op.alter_column("products", "energy_type", existing_type=sa.String(length=16), nullable=True)
    op.add_column("contracts", sa.Column("notes", sa.String(length=2000), nullable=True))
    op.add_column("customers", sa.Column("pec", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "pec")
    op.drop_column("contracts", "notes")
    op.alter_column("products", "energy_type", existing_type=sa.String(length=16), nullable=False)
    op.drop_column("products", "product_type")
