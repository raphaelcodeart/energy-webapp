"""Intestatario del contratto: nome, cognome e PEC raccolti in attivazione.

The activation wizard only ever asked for an email and the supply point. The
name the pratica is filed under was inferred from the customer's account, and
there was nowhere to put a PEC or -- until someone opened "I miei Contratti"
afterwards -- an IBAN. The business asked for all of it on the form itself.

Per contract, not per customer, for the same reason `contracts.email` and
`contracts.iban` already are: the person a supply is registered to and the
address its paperwork goes to can differ from one contract to the next. The
wizard pre-fills them from the account; nothing here reads them back into the
customer record.

All nullable: every existing contract predates them, and staff-created
contracts do not have to collect them up front.

Revision ID: a7d2e94c3b10
Revises: f1c3d85b204e
Create Date: 2026-09-16 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7d2e94c3b10"
down_revision: Union[str, None] = "f1c3d85b204e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contracts", sa.Column("holder_first_name", sa.String(length=128), nullable=True))
    op.add_column("contracts", sa.Column("holder_last_name", sa.String(length=128), nullable=True))
    op.add_column("contracts", sa.Column("pec", sa.String(length=320), nullable=True))


def downgrade() -> None:
    op.drop_column("contracts", "pec")
    op.drop_column("contracts", "holder_last_name")
    op.drop_column("contracts", "holder_first_name")
