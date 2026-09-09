"""Adds `contracts.email` -- a contact email for the specific contract/pratica,
deliberately independent of the customer's account login email (see
contracts/models.py::Contract.email). Nullable and no backfill: existing
contracts simply have no email on file until an admin sets one directly in the
DB or the customer resubmits, same "safe to leave empty" posture as
contracts.iban when it was introduced.

Revision ID: 1edc633ff504
Revises: a4d719fe6b82
Create Date: 2026-09-09 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "1edc633ff504"
down_revision: Union[str, None] = "a4d719fe6b82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("email", sa.String(length=320), nullable=True))


def downgrade() -> None:
    op.drop_column("contracts", "email")
