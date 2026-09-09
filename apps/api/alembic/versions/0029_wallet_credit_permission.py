"""Seeds `wallet.credit` -- SUPER_ADMIN ONLY, deliberately stricter than
`wallet.manage` (SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN, still used for
everything else on the wallet admin surface: viewing balances/transactions,
toggling transfer permission, reversing a transaction, and the invoice-
redemption verify/reject/confirm-payment queue). Gates only POST
/wallets/admin/topup -- the "Ricarica" button in admin-wallets-panel.tsx that
lets an admin mint arbitrary wallet credit ("Ricarica/Cashback") with no
external money trail behind it, unlike an invoice redemption's confirmed bank
transfer. The user's own framing: whoever can load cashback onto a wallet by
hand is a smaller circle than whoever can manage wallets. Permission seeding
follows 0024_stripe_payment_settings.py's pattern (itself following
0018_wallets.py's).

Revision ID: d74478f46f4c
Revises: 1edc633ff504
Create Date: 2026-09-09 00:05:00.000000
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d74478f46f4c"
down_revision: Union[str, None] = "1edc633ff504"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WALLET_CREDIT_ROLES = {"SUPER_ADMIN"}


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
        .values(id=new_id, code="wallet.credit", description="")
        .on_conflict_do_nothing(index_elements=["code"])
    )
    permission_id = conn.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == "wallet.credit")
    ).scalar_one()

    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code in WALLET_CREDIT_ROLES:
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
            "(SELECT id FROM permissions WHERE code = 'wallet.credit')"
        )
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = 'wallet.credit'"))
