"""Documenti allegati aggiuntivi: la descrizione scritta da chi carica.

Until now a contract could only hold documents of four fixed types, each one
named by its type. Real activations keep needing one more thing -- the back
of an ID, a delega, a lease, a visura for a customer who turned out to be a
business -- and there was nowhere to put it.

The new OTHER type is that place, and this column is what makes it usable:
without a label from the uploader, an admin's review queue would be a list of
rows that all read "Documento aggiuntivo". Nullable, and null for every
existing row and every slot document -- a document of a known type is already
named by its type, and is never allowed to carry a label of its own.

Revision ID: f1c3d85b204e
Revises: e5b2c74a91d8
Create Date: 2026-09-14 17:05:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1c3d85b204e"
down_revision: Union[str, None] = "e5b2c74a91d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("description", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "description")
