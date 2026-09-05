"""Phase 0 of the partner-invoice cashback project (see
docs/cashback-partner-invoices-plan.md): the `partners` anagrafica (external
energy suppliers Lial brokers for, e.g. Eviso) and product categorization
(INTERNAL/DROPSHIPPING/PARTNER + a per-version credit-discount percentage).
No money moves yet -- this migration only adds the data these later phases
need. Permission seeding follows 0018_wallets.py's exact pattern.

Revision ID: e2c8a913f047
Revises: d4b7f291a856
Create Date: 2026-09-05 01:00:00.000000
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2c8a913f047"
down_revision: Union[str, None] = "d4b7f291a856"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same roles as products.manage -- managing partners is a natural extension
# of managing the catalog (see docs/cashback-partner-invoices-plan.md).
PARTNERS_MANAGE_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN", "SALES_MANAGER"}


def upgrade() -> None:
    op.create_table(
        "partners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("logo_url", sa.String(length=1000), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("organization_id", "name", name="uq_partners_organization_name"),
    )
    op.create_index("ix_partners_organization_id", "partners", ["organization_id"])

    op.add_column(
        "products",
        sa.Column("category", sa.String(length=16), nullable=False, server_default="INTERNAL"),
    )
    op.add_column(
        "product_versions",
        sa.Column("credit_discount_percentage", sa.Integer(), nullable=False, server_default="0"),
    )

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
        .values(id=new_id, code="partners.manage", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "partners.manage")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in PARTNERS_MANAGE_ROLES:
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
            "(SELECT id FROM permissions WHERE code = 'partners.manage')"
        )
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'partners.manage'"))

    op.drop_column("product_versions", "credit_discount_percentage")
    op.drop_column("products", "category")

    op.drop_index("ix_partners_organization_id", table_name="partners")
    op.drop_table("partners")
