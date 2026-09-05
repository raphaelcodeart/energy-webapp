"""Seeds `organization.manage` (SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN,
deliberately not BACK_OFFICE_OPERATOR/SALES_MANAGER) -- gates
GET/PATCH /organizations/me/settings, the admin-editable company
configuration screen (starting with the bank IBAN customers wire bonifico
payments to, see docs/cashback-partner-invoices-plan.md). No schema change:
Organization.settings (JSONB) already existed, this only lets it actually
be read/written through an endpoint. Permission seeding follows
0018_wallets.py's exact pattern.

Revision ID: b3e9f4a7c218
Revises: a1f6e0c92d84
Create Date: 2026-09-05 04:00:00.000000
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3e9f4a7c218"
down_revision: Union[str, None] = "a1f6e0c92d84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORGANIZATION_MANAGE_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN"}


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
        .values(id=new_id, code="organization.manage", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "organization.manage")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in ORGANIZATION_MANAGE_ROLES:
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
            "(SELECT id FROM permissions WHERE code = 'organization.manage')"
        )
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'organization.manage'"))
