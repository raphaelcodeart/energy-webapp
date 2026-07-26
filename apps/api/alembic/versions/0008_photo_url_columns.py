"""add photo_url to customers and agent_profiles

Revision ID: 5e8a3c1f7b92
Revises: 3b6f1a9d2c47
Create Date: 2026-07-26 19:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5e8a3c1f7b92"
down_revision: Union[str, None] = "3b6f1a9d2c47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("photo_url", sa.String(length=1000), nullable=True))
    op.add_column("agent_profiles", sa.Column("photo_url", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_profiles", "photo_url")
    op.drop_column("customers", "photo_url")
