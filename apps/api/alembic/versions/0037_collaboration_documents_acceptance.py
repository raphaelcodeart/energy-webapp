"""Accettazione multi-documento del contratto promoter.

Becoming a promoter used to record one boolean plus a version string: the
person ticked "accetto il contratto". The paper form actually carries more
than one signature -- the contract itself, the separate approval of the
clausole vessatorie required by artt. 1341 e ss. c.c., and the Allegato A/B
(tabella compensi, schema avanzamenti di carriera) -- so one acceptance
cannot represent what is really being signed.

`agent_profiles.collaboration_accepted_documents` is a JSONB map,
{key: {"version": ..., "accepted_at": ...}}, one entry per document defined
in `network/collaboration_documents.py`. A map rather than a column pair per
document on purpose: the set of documents is a business decision that will
change again (the Allegato is still pending its real text), and each change
must not cost a migration.

The two existing columns (`collaboration_contract_version`,
`collaboration_accepted_at`) are left exactly as they are and kept in step
for the main contract, so nothing that already reads them changes behaviour.
Existing rows get `{}` -- deliberately NOT back-filled with a synthetic
acceptance: those promoters accepted the older, shorter text, and inventing
a record saying otherwise would be the one thing an acceptance log must never
do.

Revision ID: d9a04b7e13c5
Revises: c8f1a37d62be
Create Date: 2026-09-14 03:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d9a04b7e13c5"
down_revision: Union[str, None] = "c8f1a37d62be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_profiles",
        sa.Column(
            "collaboration_accepted_documents",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_profiles", "collaboration_accepted_documents")
