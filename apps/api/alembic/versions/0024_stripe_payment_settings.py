"""Seeds `organization.manage_payments` -- SUPER_ADMIN ONLY, deliberately
stricter than `organization.manage` (SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN,
used for the bank IBAN settings). Gates GET/PATCH
/organizations/me/payment-settings, where the Stripe secret/publishable/
webhook keys live (in the same Organization.settings JSONB, no schema
change needed for that). The user's own framing: whoever can process card
payments for the org is a smaller circle than whoever can see/edit where
bonifico money goes. Permission seeding follows 0018_wallets.py's pattern.

Revision ID: c5a8d217e930
Revises: b3e9f4a7c218
Create Date: 2026-09-05 05:00:00.000000
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5a8d217e930"
down_revision: Union[str, None] = "b3e9f4a7c218"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MANAGE_PAYMENTS_ROLES = {"SUPER_ADMIN"}


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
        .values(id=new_id, code="organization.manage_payments", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "organization.manage_payments")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in MANAGE_PAYMENTS_ROLES:
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
            "(SELECT id FROM permissions WHERE code = 'organization.manage_payments')"
        )
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'organization.manage_payments'"))
