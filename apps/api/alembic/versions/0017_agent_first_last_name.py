"""Splits agent_profiles.display_name into proper first_name/last_name
columns -- every "Nome e Cognome" form across the app (create promoter,
create root promoter, recruit, edit) was a single combined text field with no
way to know which part was which. display_name is kept as a denormalized
"first last" for the many existing read paths that only need one string.

Backfills the handful of already-existing agents: where the agent's own login
is linked to a customer record (which already has real, separately-typed
first_name/last_name), that structured data is used -- this also fixes a
promoter whose display_name had been set to an email-derived placeholder
instead of their real name. Any agent with no linked customer (e.g. a root
promoter created directly by an admin) falls back to splitting display_name
on its first space.

Revision ID: b8e4f1a2c937
Revises: a3d7f92c1e68
Create Date: 2026-08-27 13:00:00.000000
"""
import sqlalchemy as sa
from alembic import op
from typing import Sequence, Union

revision: str = "b8e4f1a2c937"
down_revision: Union[str, None] = "a3d7f92c1e68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_profiles", sa.Column("first_name", sa.String(length=120), nullable=True))
    op.add_column("agent_profiles", sa.Column("last_name", sa.String(length=120), nullable=True))

    conn = op.get_bind()

    # Agents whose login is linked to a customer record: trust that
    # customer's own (already correctly split) name, and use it to also fix
    # display_name if it had drifted (e.g. an email-derived placeholder).
    conn.execute(
        sa.text(
            """
            UPDATE agent_profiles ap
            SET first_name = trim(cp.first_name),
                last_name = trim(cp.last_name),
                display_name = trim(trim(cp.first_name) || ' ' || trim(cp.last_name))
            FROM customers c
            JOIN customer_profiles cp ON cp.customer_id = c.id
            WHERE c.user_id = ap.user_id
              AND c.organization_id = ap.organization_id
              AND trim(coalesce(cp.first_name, '')) <> ''
            """
        )
    )

    # Everyone else (no linked customer, e.g. a root promoter created
    # directly): best-effort split of the existing display_name on its
    # first space.
    conn.execute(
        sa.text(
            """
            UPDATE agent_profiles
            SET first_name = split_part(display_name, ' ', 1),
                last_name = trim(substring(display_name from position(' ' in display_name) + 1))
            WHERE first_name IS NULL AND position(' ' in display_name) > 0
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE agent_profiles
            SET first_name = display_name, last_name = ''
            WHERE first_name IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("agent_profiles", "last_name")
    op.drop_column("agent_profiles", "first_name")
