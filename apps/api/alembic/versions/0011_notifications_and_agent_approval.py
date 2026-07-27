"""add notifications table; add agent_profiles approval columns
(approved_by_user_id, approved_at, rejection_reason) for the new
suggest-then-approve promoter creation workflow; seed + grant the
network.approve permission to SUPER_ADMIN/ORGANIZATION_ADMIN only

Revision ID: b3f8e1c47a06
Revises: a1f6d9c3e872
Create Date: 2026-07-28 09:00:00.000000
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3f8e1c47a06"
down_revision: Union[str, None] = "a1f6d9c3e872"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPROVE_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN"}


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.String(length=1000), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])

    op.add_column("agent_profiles", sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("agent_profiles", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_profiles", sa.Column("rejection_reason", sa.String(length=500), nullable=True))

    conn = op.get_bind()
    permissions_table = sa.table("permissions", sa.column("id", sa.UUID()), sa.column("code", sa.String()), sa.column("description", sa.String()))
    role_permissions_table = sa.table("role_permissions", sa.column("role_id", sa.UUID()), sa.column("permission_id", sa.UUID()))
    roles_table = sa.table("roles", sa.column("id", sa.UUID()), sa.column("code", sa.String()))

    new_id = uuid.uuid4()
    conn.execute(
        postgresql.insert(permissions_table)
        .values(id=new_id, code="network.approve", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "network.approve")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in APPROVE_ROLES:
            conn.execute(
                postgresql.insert(role_permissions_table)
                .values(role_id=role_id, permission_id=permission_id)
                .on_conflict_do_nothing()
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'network.approve')"))
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'network.approve'"))

    op.drop_column("agent_profiles", "rejection_reason")
    op.drop_column("agent_profiles", "approved_at")
    op.drop_column("agent_profiles", "approved_by_user_id")

    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")
    op.drop_index("ix_notifications_organization_id", table_name="notifications")
    op.drop_table("notifications")
