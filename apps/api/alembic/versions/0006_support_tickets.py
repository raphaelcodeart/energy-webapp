"""add tickets/ticket_messages tables, seed tickets.create/tickets.respond
permissions and grant them to existing roles

Revision ID: 9a2c7e5f0b14
Revises: 7d3f9a1c6e82
Create Date: 2026-07-26 12:00:00.000000
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9a2c7e5f0b14"
down_revision: Union[str, None] = "7d3f9a1c6e82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors app/domains/rbac/models.py DEFAULT_ROLE_PERMISSIONS -- which existing
# role codes should be granted each new permission. SUPER_ADMIN/ORGANIZATION_ADMIN
# already get every permission code via PERMISSIONS (the full list), so they're
# included in both grants below.
TICKETS_CREATE_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "PROMOTER", "CUSTOMER"}
TICKETS_RESPOND_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN", "BACK_OFFICE_OPERATOR"}


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("opened_by_user_id", sa.UUID(), nullable=False),
        sa.Column("opened_by_role", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.ForeignKeyConstraint(["opened_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tickets_organization_id"), "tickets", ["organization_id"], unique=False)
    op.create_index(op.f("ix_tickets_opened_by_user_id"), "tickets", ["opened_by_user_id"], unique=False)
    op.create_index(op.f("ix_tickets_status"), "tickets", ["status"], unique=False)

    op.create_table(
        "ticket_messages",
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("author_user_id", sa.UUID(), nullable=False),
        sa.Column("author_role", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ticket_messages_ticket_id"), "ticket_messages", ["ticket_id"], unique=False)

    conn = op.get_bind()
    permissions_table = sa.table(
        "permissions", sa.column("id", sa.UUID()), sa.column("code", sa.String()), sa.column("description", sa.String())
    )
    role_permissions_table = sa.table(
        "role_permissions", sa.column("role_id", sa.UUID()), sa.column("permission_id", sa.UUID())
    )
    roles_table = sa.table("roles", sa.column("id", sa.UUID()), sa.column("code", sa.String()))

    permission_ids: dict[str, uuid.UUID] = {}
    for code in ("tickets.create", "tickets.respond"):
        new_id = uuid.uuid4()
        conn.execute(
            postgresql.insert(permissions_table)
            .values(id=new_id, code=code, description="")
            .on_conflict_do_nothing(index_elements=["code"])
        )
        existing_id = conn.execute(
            sa.select(permissions_table.c.id).where(permissions_table.c.code == code)
        ).scalar_one()
        permission_ids[code] = existing_id

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        for perm_code, allowed_roles in (
            ("tickets.create", TICKETS_CREATE_ROLES),
            ("tickets.respond", TICKETS_RESPOND_ROLES),
        ):
            if role_code in allowed_roles:
                conn.execute(
                    postgresql.insert(role_permissions_table)
                    .values(role_id=role_id, permission_id=permission_ids[perm_code])
                    .on_conflict_do_nothing()
                )


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_messages_ticket_id"), table_name="ticket_messages")
    op.drop_table("ticket_messages")
    op.drop_index(op.f("ix_tickets_status"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_opened_by_user_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_organization_id"), table_name="tickets")
    op.drop_table("tickets")
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('tickets.create', 'tickets.respond'))"))
    conn.execute(sa.text("DELETE FROM permissions WHERE code IN ('tickets.create', 'tickets.respond')"))
