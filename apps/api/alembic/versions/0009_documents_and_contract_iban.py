"""add documents table, contracts.iban column, seed documents.upload/
documents.review permissions and grant them to existing roles

Revision ID: 8c4e7b2a9d15
Revises: 5e8a3c1f7b92
Create Date: 2026-07-27 10:00:00.000000
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8c4e7b2a9d15"
down_revision: Union[str, None] = "5e8a3c1f7b92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors app/domains/rbac/models.py DEFAULT_ROLE_PERMISSIONS -- see migration
# 0006 (tickets) for the same pattern applied to a different pair of codes.
DOCUMENTS_UPLOAD_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN", "BACK_OFFICE_OPERATOR", "CUSTOMER"}
DOCUMENTS_REVIEW_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN", "BACK_OFFICE_OPERATOR"}


def upgrade() -> None:
    op.add_column("contracts", sa.Column("iban", sa.String(length=34), nullable=True))

    op.create_table(
        "documents",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("contract_id", sa.UUID(), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.UUID(), nullable=False),
        sa.Column("uploaded_by_role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reviewed_by_user_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(length=1000), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_organization_id"), "documents", ["organization_id"], unique=False)
    op.create_index(op.f("ix_documents_contract_id"), "documents", ["contract_id"], unique=False)
    op.create_index(op.f("ix_documents_status"), "documents", ["status"], unique=False)
    op.create_unique_constraint("uq_documents_storage_key", "documents", ["storage_key"])

    conn = op.get_bind()
    permissions_table = sa.table(
        "permissions", sa.column("id", sa.UUID()), sa.column("code", sa.String()), sa.column("description", sa.String())
    )
    role_permissions_table = sa.table(
        "role_permissions", sa.column("role_id", sa.UUID()), sa.column("permission_id", sa.UUID())
    )
    roles_table = sa.table("roles", sa.column("id", sa.UUID()), sa.column("code", sa.String()))

    permission_ids: dict[str, uuid.UUID] = {}
    for code in ("documents.upload", "documents.review"):
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
            ("documents.upload", DOCUMENTS_UPLOAD_ROLES),
            ("documents.review", DOCUMENTS_REVIEW_ROLES),
        ):
            if role_code in allowed_roles:
                conn.execute(
                    postgresql.insert(role_permissions_table)
                    .values(role_id=role_id, permission_id=permission_ids[perm_code])
                    .on_conflict_do_nothing()
                )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('documents.upload', 'documents.review'))"))
    conn.execute(sa.text("DELETE FROM permissions WHERE code IN ('documents.upload', 'documents.review')"))

    op.drop_constraint("uq_documents_storage_key", "documents", type_="unique")
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_contract_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_organization_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_column("contracts", "iban")
