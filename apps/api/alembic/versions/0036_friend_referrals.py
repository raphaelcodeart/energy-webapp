"""La "rete segnalatori": rete a un livello, staccata da quella commerciale.

Three tables that are deliberately a parallel structure, not an extension of
the commercial network -- the business was explicit that this "non c'entra
nulla con l'attuale rete, è una cosa staccata e separata che ogni cliente ha".

Every person with a login gets a personal invite link and a flat list of who
signed up through it. One level, no hierarchy, **no commissions**. It exists
so somebody who is not a promoter can still see who they brought in, and so
we can count how many of those went on to activate a real contract (one gift
per 5 activated).

Where a new customer lands in the *commercial* tree is untouched by all of
this and still decided entirely by the existing referral/network domains:
a promoter's link puts them in that promoter's tree as always; a plain
customer's link puts them under that customer's OWN promoter. These tables
could be dropped tomorrow without changing a single euro of commission.

No column is added to any existing table, and nothing existing is altered --
this migration only creates.

Revision ID: c8f1a37d62be
Revises: b4e2f81c05a9
Create Date: 2026-09-14 02:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8f1a37d62be"
down_revision: Union[str, None] = "b4e2f81c05a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "friend_referral_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.PrimaryKeyConstraint("id", name="pk_friend_referral_codes"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_friend_referral_codes_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_friend_referral_codes_user_id_users"),
        # One link per person, and a code that can never collide with another
        # -- the code is the only thing a visitor gives us, so its uniqueness
        # is what makes resolution unambiguous.
        sa.UniqueConstraint("user_id", name="uq_friend_referral_codes_user_id"),
        sa.UniqueConstraint("code", name="uq_friend_referral_codes_code"),
    )
    op.create_index(
        "ix_friend_referral_codes_organization_id", "friend_referral_codes", ["organization_id"]
    )

    op.create_table(
        "friend_referrals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("referrer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("referred_customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_used", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_friend_referrals"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_friend_referrals_organization_id_organizations"
        ),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"], name="fk_friend_referrals_referrer_user_id_users"),
        sa.ForeignKeyConstraint(
            ["referred_customer_id"], ["customers.id"], name="fk_friend_referrals_referred_customer_id_customers"
        ),
        # A customer can only ever have been brought in by one person.
        sa.UniqueConstraint("referred_customer_id", name="uq_friend_referrals_referred_customer_id"),
    )
    op.create_index("ix_friend_referrals_organization_id", "friend_referrals", ["organization_id"])
    op.create_index("ix_friend_referrals_referrer_user_id", "friend_referrals", ["referrer_user_id"])

    op.create_table(
        "friend_referral_reward_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("referrer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="REQUESTED"),
        sa.Column("handled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_friend_referral_reward_claims"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_friend_referral_reward_claims_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["referrer_user_id"], ["users.id"], name="fk_friend_referral_reward_claims_referrer_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["handled_by_user_id"], ["users.id"], name="fk_friend_referral_reward_claims_handled_by_user_id_users"
        ),
        # This is what makes "un omaggio ogni 5" exact: milestone 5 can be
        # requested once, ever, whatever the count does afterwards.
        sa.UniqueConstraint("referrer_user_id", "milestone", name="uq_friend_referral_claim_user_milestone"),
    )
    op.create_index(
        "ix_friend_referral_reward_claims_organization_id", "friend_referral_reward_claims", ["organization_id"]
    )
    op.create_index(
        "ix_friend_referral_reward_claims_referrer_user_id", "friend_referral_reward_claims", ["referrer_user_id"]
    )
    op.create_index("ix_friend_referral_reward_claims_status", "friend_referral_reward_claims", ["status"])


def downgrade() -> None:
    op.drop_table("friend_referral_reward_claims")
    op.drop_table("friend_referrals")
    op.drop_table("friend_referral_codes")
