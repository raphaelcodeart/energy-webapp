"""Contracts: discount for paying in one go, frozen on the contract.

The discount (organization setting, 32% by default) is taken off a contract
paid in a single payment only. The amount chosen at checkout is stored on the
contract, so the instalment row, the LialCash cashback and the commission
preview read what was actually charged even if the setting changes later.
Existing contracts: 0.

Revision ID: b9e5f7a1c426
Revises: a8d4e6f0b315
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b9e5f7a1c426"
down_revision: Union[str, None] = "a8d4e6f0b315"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contracts", sa.Column("payment_discount_cents", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column("contracts", "payment_discount_cents")
