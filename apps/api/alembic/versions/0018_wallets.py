"""Internal EUR wallet per user (customer or promoter): crypto-style address,
integer-cents balance with a CHECK >= 0, and an append-only wallet_transactions
ledger (admin top-up/cashback, peer transfer, reversal). Seeds the
wallet.manage permission, granted to SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN
only -- not BACK_OFFICE_OPERATOR. See docs/business-rules.md#internal-wallet.

Revision ID: c9a1e4b6d2f3
Revises: b8e4f1a2c937
Create Date: 2026-09-04 00:00:00.000000
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9a1e4b6d2f3"
down_revision: Union[str, None] = "b8e4f1a2c937"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WALLET_MANAGE_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN"}


def upgrade() -> None:
    op.create_table(
        "wallets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("address", sa.String(length=42), nullable=False),
        sa.Column("balance_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.UniqueConstraint("user_id", name="uq_wallets_user_id"),
        sa.UniqueConstraint("address", name="uq_wallets_address"),
        sa.CheckConstraint("balance_cents >= 0", name="ck_wallets_balance_non_negative"),
    )
    op.create_index("ix_wallets_organization_id", "wallets", ["organization_id"])
    op.create_index("ix_wallets_user_id", "wallets", ["user_id"])
    op.create_index("ix_wallets_address", "wallets", ["address"])

    op.create_table(
        "wallet_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("from_wallet_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wallets.id"), nullable=True),
        sa.Column("to_wallet_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wallets.id"), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column(
            "reference_contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id"), nullable=True
        ),
        sa.Column(
            "reverses_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wallet_transactions.id"),
            nullable=True,
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_wallet_transactions_idempotency_key"),
        sa.CheckConstraint(
            "from_wallet_id IS NOT NULL OR to_wallet_id IS NOT NULL", name="ck_wallet_transactions_has_a_side"
        ),
    )
    op.create_index("ix_wallet_transactions_organization_id", "wallet_transactions", ["organization_id"])
    op.create_index("ix_wallet_transactions_from_wallet_id", "wallet_transactions", ["from_wallet_id"])
    op.create_index("ix_wallet_transactions_to_wallet_id", "wallet_transactions", ["to_wallet_id"])
    op.create_index("ix_wallet_transactions_type", "wallet_transactions", ["type"])

    # Permission seeding -- mirrors 0011_notifications_and_agent_approval.py's
    # network.approve seeding exactly: reflect permissions/role_permissions/roles
    # as bare sa.table() shims, on_conflict_do_nothing() the permission row
    # (idempotent against a re-run), look the id back up by code, then grant it
    # to every role whose code is in WALLET_MANAGE_ROLES.
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
        .values(id=new_id, code="wallet.manage", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "wallet.manage")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in WALLET_MANAGE_ROLES:
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
            "(SELECT id FROM permissions WHERE code = 'wallet.manage')"
        )
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'wallet.manage'"))

    op.drop_index("ix_wallet_transactions_type", table_name="wallet_transactions")
    op.drop_index("ix_wallet_transactions_to_wallet_id", table_name="wallet_transactions")
    op.drop_index("ix_wallet_transactions_from_wallet_id", table_name="wallet_transactions")
    op.drop_index("ix_wallet_transactions_organization_id", table_name="wallet_transactions")
    op.drop_table("wallet_transactions")

    op.drop_index("ix_wallets_address", table_name="wallets")
    op.drop_index("ix_wallets_user_id", table_name="wallets")
    op.drop_index("ix_wallets_organization_id", table_name="wallets")
    op.drop_table("wallets")
