"""Peer-to-peer wallet transfer (POST /wallets/transfer) is now denied by
default for every wallet -- customer or promoter alike -- and must be
enabled individually per promoter by an admin. This session's explicit
request: only two named promoters get it on day one. See
docs/business-rules.md#internal-wallet.

Data step: lazily creates a wallet (if one doesn't exist yet) for the two
named users and sets can_transfer=true on it -- get_or_create_wallet()'s
own address-generation scheme (f"0x" + 40 hex chars), duplicated here rather
than imported, since migrations must not depend on application code that can
change shape later (same reasoning as every other data-seeding migration in
this codebase, e.g. 0010's rank figures).

Revision ID: d4b7f291a856
Revises: c9a1e4b6d2f3
Create Date: 2026-09-05 00:00:00.000000
"""

import secrets
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4b7f291a856"
down_revision: Union[str, None] = "c9a1e4b6d2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# user_id values confirmed live on this server on 2026-09-05 (AgentProfile
# "Alessandro Pantano" / "Marco Web") -- see the migration docstring above.
TRANSFER_ENABLED_USER_IDS = [
    "1901dc57-6a35-47a2-aebd-19614d760b89",  # Alessandro Pantano
    "574c826e-4b83-431b-b60f-0b256530ceb5",  # Marco Web
]


def upgrade() -> None:
    op.add_column(
        "wallets",
        sa.Column("can_transfer", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    conn = op.get_bind()
    for user_id in TRANSFER_ENABLED_USER_IDS:
        result = conn.execute(
            sa.text("SELECT id FROM wallets WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).first()
        if result is not None:
            conn.execute(
                sa.text("UPDATE wallets SET can_transfer = true WHERE id = :id"),
                {"id": result[0]},
            )
            continue

        org_row = conn.execute(
            sa.text("SELECT organization_id FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        ).first()
        if org_row is None:
            # User not present on this environment (e.g. a fresh dev DB) --
            # nothing to enable, not an error.
            continue
        conn.execute(
            sa.text(
                "INSERT INTO wallets (id, created_at, organization_id, user_id, address, "
                "balance_cents, currency, can_transfer) "
                "VALUES (:id, now(), :organization_id, :user_id, :address, 0, 'EUR', true)"
            ),
            {
                "id": str(uuid.uuid4()),
                "organization_id": org_row[0],
                "user_id": user_id,
                "address": f"0x{secrets.token_hex(20)}",
            },
        )


def downgrade() -> None:
    op.drop_column("wallets", "can_transfer")
