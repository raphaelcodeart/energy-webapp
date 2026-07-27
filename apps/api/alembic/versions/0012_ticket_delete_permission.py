"""seed + grant the tickets.delete permission to SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN
only -- deliberately narrower than tickets.respond (also held by
BACK_OFFICE_OPERATOR), same pattern as network.approve in migration 0011:
permanently deleting a ticket is more consequential than replying to one.

Revision ID: c4a9e2d58b13
Revises: b3f8e1c47a06
Create Date: 2026-07-27 10:00:00.000000
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4a9e2d58b13"
down_revision: Union[str, None] = "b3f8e1c47a06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DELETE_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN"}


def upgrade() -> None:
    conn = op.get_bind()
    permissions_table = sa.table("permissions", sa.column("id", sa.UUID()), sa.column("code", sa.String()), sa.column("description", sa.String()))
    role_permissions_table = sa.table("role_permissions", sa.column("role_id", sa.UUID()), sa.column("permission_id", sa.UUID()))
    roles_table = sa.table("roles", sa.column("id", sa.UUID()), sa.column("code", sa.String()))

    new_id = uuid.uuid4()
    conn.execute(
        postgresql.insert(permissions_table)
        .values(id=new_id, code="tickets.delete", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "tickets.delete")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in DELETE_ROLES:
            conn.execute(
                postgresql.insert(role_permissions_table)
                .values(role_id=role_id, permission_id=permission_id)
                .on_conflict_do_nothing()
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'tickets.delete')"))
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'tickets.delete'"))
