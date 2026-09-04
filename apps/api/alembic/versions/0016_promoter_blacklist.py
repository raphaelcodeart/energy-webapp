"""Auto-activation for self-service "lavora con noi": adds
agent_profiles.is_blacklisted so a promoter an admin has explicitly
blacklisted (worse than a plain deactivation) goes back through the manual
PENDING_APPROVAL/approve flow if they ever re-apply, while everyone else
becomes an ACTIVE promoter immediately on click -- see network/service.py
apply_as_promoter().

Revision ID: a3d7f92c1e68
Revises: f2a8c4e17d59
Create Date: 2026-08-27 11:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3d7f92c1e68"
down_revision: Union[str, None] = "f2a8c4e17d59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_profiles",
        sa.Column("is_blacklisted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("agent_profiles", "is_blacklisted")
