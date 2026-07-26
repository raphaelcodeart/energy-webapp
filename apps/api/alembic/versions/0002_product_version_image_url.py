"""add image_url to product_versions

Revision ID: 8a1f2c9e3b4d
Revises: c04a107284c3
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a1f2c9e3b4d"
down_revision: Union[str, None] = "c04a107284c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_versions",
        sa.Column("image_url", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product_versions", "image_url")
