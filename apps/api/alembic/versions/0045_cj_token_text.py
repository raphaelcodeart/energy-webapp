"""Shop Lial Partner: CJ access/refresh tokens as TEXT.

CJ's tokens are JWTs of about 500+ characters (and not bounded by the docs):
the VARCHAR(500) of 0044 refused the first real one.

Revision ID: f7c3d5e9a204
Revises: e6b2c4d8f193
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7c3d5e9a204"
down_revision: Union[str, None] = "e6b2c4d8f193"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("cj_settings", "access_token", type_=sa.Text(), existing_type=sa.String(500), existing_nullable=True)
    op.alter_column("cj_settings", "refresh_token", type_=sa.Text(), existing_type=sa.String(500), existing_nullable=True)


def downgrade() -> None:
    # Tokens do not fit VARCHAR(500): they are dropped and fetched again with the API key.
    op.execute("UPDATE cj_settings SET access_token = NULL, refresh_token = NULL")
    op.alter_column("cj_settings", "access_token", type_=sa.String(500), existing_type=sa.Text(), existing_nullable=True)
    op.alter_column("cj_settings", "refresh_token", type_=sa.String(500), existing_type=sa.Text(), existing_nullable=True)
