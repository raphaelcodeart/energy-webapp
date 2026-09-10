"""Session 34's "Acquisti LialEnergy" plugin: a parallel, isolated catalog
of externally-sourced products (AliExpress today, other providers later --
see imported_products/models.py::IMPORT_PROVIDER_TYPES) that customers can
partly or fully pay for with wallet LialCash, never mixed into the
catalog.products table by explicit user request. Three new tables
(import_providers, imported_products, imported_product_orders) plus a new
nullable reference_imported_order_id column on wallet_transactions (mirrors
reference_order_id, lets a PURCHASE_DEBIT trace back to an imported-product
order the same way it already traces back to a regular one). Seeds
`imported_products.manage`, granted to SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN
only -- the provider config screen stores an API key, similar sensitivity
tier to Stripe's settings.manage. Permission seeding follows
0029_wallet_credit_permission.py's pattern.

Revision ID: f3a7c9e15b04
Revises: 6c1d4e9f2a58
Create Date: 2026-09-10 00:00:00.000000
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a7c9e15b04"
down_revision: Union[str, None] = "6c1d4e9f2a58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMPORTED_PRODUCTS_MANAGE_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN"}


def upgrade() -> None:
    op.create_table(
        "import_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("api_key", sa.String(length=500), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_import_providers_organization_id", "import_providers", ["organization_id"])

    op.create_table(
        "imported_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_providers.id"), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=1000), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("credit_discount_percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_imported_products_organization_id", "imported_products", ["organization_id"])
    op.create_index("ix_imported_products_provider_id", "imported_products", ["provider_id"])

    op.create_table(
        "imported_product_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("customer_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("imported_product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("imported_products.id"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("credit_applied_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("credit_debit_transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wallet_transactions.id"), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="AWAITING_PAYMENT"),
        sa.Column("payment_method", sa.String(length=16), nullable=False, server_default="BANK_TRANSFER"),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("payment_proof_storage_key", sa.String(length=500), nullable=True),
        sa.Column("payment_proof_original_filename", sa.String(length=255), nullable=True),
        sa.Column("payment_proof_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.UniqueConstraint("stripe_checkout_session_id", name="uq_imported_product_orders_stripe_session"),
        sa.CheckConstraint("credit_applied_cents >= 0", name="ck_imported_orders_credit_applied_non_negative"),
        sa.CheckConstraint("credit_applied_cents <= amount_cents", name="ck_imported_orders_credit_applied_not_over_amount"),
    )
    op.create_index("ix_imported_product_orders_organization_id", "imported_product_orders", ["organization_id"])
    op.create_index("ix_imported_product_orders_customer_user_id", "imported_product_orders", ["customer_user_id"])
    op.create_index("ix_imported_product_orders_status", "imported_product_orders", ["status"])

    op.add_column(
        "wallet_transactions",
        sa.Column(
            "reference_imported_order_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("imported_product_orders.id"), nullable=True,
        ),
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
        .values(id=new_id, code="imported_products.manage", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "imported_products.manage")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in IMPORTED_PRODUCTS_MANAGE_ROLES:
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
            "(SELECT id FROM permissions WHERE code = 'imported_products.manage')"
        )
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'imported_products.manage'"))
    op.drop_column("wallet_transactions", "reference_imported_order_id")
    op.drop_table("imported_product_orders")
    op.drop_table("imported_products")
    op.drop_table("import_providers")
