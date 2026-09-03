"""seed + grant the commissions.evaluate_ranks permission to SUPER_ADMIN/
ORGANIZATION_ADMIN only -- same restriction already applied to network.approve
(migration 0011) and tickets.delete (migration 0012): triggering a bulk
promote/demote run across every agent in the org is more consequential than
routine commissions actions, so a plain ADMIN doesn't get it.

Revision ID: d5b1f6a93c27
Revises: c4a9e2d58b13
Create Date: 2026-08-25 10:00:00.000000
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5b1f6a93c27"
down_revision: Union[str, None] = "c4a9e2d58b13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVALUATE_RANKS_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN"}


def upgrade() -> None:
    conn = op.get_bind()
    permissions_table = sa.table("permissions", sa.column("id", sa.UUID()), sa.column("code", sa.String()), sa.column("description", sa.String()))
    role_permissions_table = sa.table("role_permissions", sa.column("role_id", sa.UUID()), sa.column("permission_id", sa.UUID()))
    roles_table = sa.table("roles", sa.column("id", sa.UUID()), sa.column("code", sa.String()))

    new_id = uuid.uuid4()
    conn.execute(
        postgresql.insert(permissions_table)
        .values(id=new_id, code="commissions.evaluate_ranks", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "commissions.evaluate_ranks")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in EVALUATE_RANKS_ROLES:
            conn.execute(
                postgresql.insert(role_permissions_table)
                .values(role_id=role_id, permission_id=permission_id)
                .on_conflict_do_nothing()
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'commissions.evaluate_ranks')"))
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'commissions.evaluate_ranks'"))
