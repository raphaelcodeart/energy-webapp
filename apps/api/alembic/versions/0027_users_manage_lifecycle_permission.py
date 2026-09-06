"""Seeds `users.manage_lifecycle` -- SUPER_ADMIN ONLY, gates the new
PATCH /users/{id}/freeze and /unfreeze endpoints (see
app/domains/users/router.py and service.py). The user's own explicit
request: freezing/deleting an account is sensitive enough to sit behind a
smaller circle than the ADMIN/ORGANIZATION_ADMIN tier that already manages
day-to-day customer/promoter records. Permission seeding follows
0018_wallets.py's exact pattern (same as organization.manage_payments in
0024/c5a8d217e930).

Revision ID: a4d719fe6b82
Revises: f1c8a4d92e63
Create Date: 2026-09-06 02:00:00.000000
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4d719fe6b82"
down_revision: Union[str, None] = "f1c8a4d92e63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MANAGE_LIFECYCLE_ROLES = {"SUPER_ADMIN"}


def upgrade() -> None:
    conn = op.get_bind()
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.UUID()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.UUID()),
        sa.column("permission_id", sa.UUID()),
    )
    roles_table = sa.table("roles", sa.column("id", sa.UUID()), sa.column("code", sa.String()))

    new_id = uuid.uuid4()
    conn.execute(
        postgresql.insert(permissions_table)
        .values(id=new_id, code="users.manage_lifecycle", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "users.manage_lifecycle")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in MANAGE_LIFECYCLE_ROLES:
            conn.execute(
                postgresql.insert(role_permissions_table)
                .values(role_id=role_id, permission_id=permission_id)
                .on_conflict_do_nothing()
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = 'users.manage_lifecycle')"
        )
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'users.manage_lifecycle'"))
