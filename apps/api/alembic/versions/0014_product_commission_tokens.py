"""add commission_tokens (per-rank gettone override) to product_versions -- lets
each product (e.g. "Luce Energia Circolare" vs "Luce Standard") pay a different
personal token per rank instead of sharing the single org-wide Rank.personal_
token_cents. See commissions/services/run_calculation.py::_build_chain.

Revision ID: e7f3a1c9b246
Revises: d5b1f6a93c27
Create Date: 2026-08-26 09:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7f3a1c9b246"
down_revision: Union[str, None] = "d5b1f6a93c27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_versions",
        sa.Column("commission_tokens", postgresql.JSONB, nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("product_versions", "commission_tokens")
