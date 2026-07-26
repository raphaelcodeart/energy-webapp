"""populate ranks.personal_volume_threshold_cents / group_volume_threshold_cents
with placeholder promotion-progress figures (were present in the schema since
0001 but always left at 0 -- see docs/open-questions.md #1 and
docs/business-rules.md#rank-promotion-progress-placeholder)

Revision ID: a1f6d9c3e872
Revises: 8c4e7b2a9d15
Create Date: 2026-07-27 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1f6d9c3e872"
down_revision: Union[str, None] = "8c4e7b2a9d15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# code -> (personal_volume_threshold_cents, group_volume_threshold_cents).
# Placeholder figures, not confirmed Lial Energy policy -- see the docstring
# above. Personal volume is what an agent has PERSONALLY produced (as
# contract producer); group volume is the total across their entire
# downline including themselves. Both are cumulative totals ("lifetime"),
# not evaluated over ranks.evaluation_window_months -- that column remains
# an unused placeholder for a future rolling-window iteration.
THRESHOLDS = {
    "S1": (0, 0),
    "S2": (1500, 1500),
    "S3": (3000, 4000),
    "TL1": (3000, 8000),
    "TL2": (3000, 12000),
    "TL3": (3000, 16000),
    "TL4": (3000, 20000),
    "MD1": (3000, 25000),
    "MD2": (3000, 30000),
    "MD3": (3000, 35000),
    "MD4": (3000, 40000),
    "MD5": (3000, 45000),
}


def upgrade() -> None:
    conn = op.get_bind()
    ranks = sa.table(
        "ranks",
        sa.column("code", sa.String),
        sa.column("personal_volume_threshold_cents", sa.BigInteger),
        sa.column("group_volume_threshold_cents", sa.BigInteger),
    )
    for code, (personal, group) in THRESHOLDS.items():
        conn.execute(
            ranks.update()
            .where(ranks.c.code == code)
            .values(personal_volume_threshold_cents=personal, group_volume_threshold_cents=group)
        )


def downgrade() -> None:
    conn = op.get_bind()
    ranks = sa.table(
        "ranks",
        sa.column("code", sa.String),
        sa.column("personal_volume_threshold_cents", sa.BigInteger),
        sa.column("group_volume_threshold_cents", sa.BigInteger),
    )
    conn.execute(ranks.update().values(personal_volume_threshold_cents=0, group_volume_threshold_cents=0))
