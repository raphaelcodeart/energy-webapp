"""documentation/news feed: admin-authored posts (title, body, optional image/
pdf/video link) published to CUSTOMER, PROMOTER, or BOTH -- lets the admin
hand out training material to promoters and useful material to customers from
the dashboard, like a small social feed. Grants the new documentation.manage
permission to SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN -- routine content
publishing, same tier as products.manage, not restricted like network.approve.

Revision ID: f2a8c4e17d59
Revises: e7f3a1c9b246
Create Date: 2026-08-27 09:00:00.000000
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a8c4e17d59"
down_revision: Union[str, None] = "e7f3a1c9b246"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOCUMENTATION_MANAGE_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN"}


def upgrade() -> None:
    op.create_table(
        "documentation_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("audience", sa.String(length=16), nullable=False, server_default="BOTH"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PUBLISHED"),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("pdf_url", sa.String(length=500), nullable=True),
        sa.Column("pdf_filename", sa.String(length=255), nullable=True),
        sa.Column("video_url", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_documentation_posts_organization_id", "documentation_posts", ["organization_id"])
    op.create_index("ix_documentation_posts_status", "documentation_posts", ["status"])

    conn = op.get_bind()
    permissions_table = sa.table("permissions", sa.column("id", sa.UUID()), sa.column("code", sa.String()), sa.column("description", sa.String()))
    role_permissions_table = sa.table("role_permissions", sa.column("role_id", sa.UUID()), sa.column("permission_id", sa.UUID()))
    roles_table = sa.table("roles", sa.column("id", sa.UUID()), sa.column("code", sa.String()))

    new_id = uuid.uuid4()
    conn.execute(
        postgresql.insert(permissions_table)
        .values(id=new_id, code="documentation.manage", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "documentation.manage")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in DOCUMENTATION_MANAGE_ROLES:
            conn.execute(
                postgresql.insert(role_permissions_table)
                .values(role_id=role_id, permission_id=permission_id)
                .on_conflict_do_nothing()
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'documentation.manage')"))
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'documentation.manage'"))
    op.drop_index("ix_documentation_posts_status", table_name="documentation_posts")
    op.drop_index("ix_documentation_posts_organization_id", table_name="documentation_posts")
    op.drop_table("documentation_posts")
