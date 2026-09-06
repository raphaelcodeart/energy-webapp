"""Account-gate infrastructure: mandatory profile completion (fiscal code +
residence, blocking every account, existing or new) and mandatory email
verification (new registrations only -- existing accounts are grandfathered
as already-verified in the data migration below). Also adds the
collaboration-agreement + OTP acceptance fields for the 'lavora con noi'
flow. See app/domains/users/models.py, app/domains/auth/models.py,
app/domains/network/models.py and docs/business-rules.md#account-gates.

Revision ID: f1c8a4d92e63
Revises: d6f3b8a1c574
Create Date: 2026-09-05 08:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1c8a4d92e63"
down_revision: Union[str, None] = "d6f3b8a1c574"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- users: privacy consent + profile-completion gate ------------------
    op.add_column("users", sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("fiscal_code", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("residence_street", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("residence_city", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("residence_province", sa.String(length=2), nullable=True))
    op.add_column("users", sa.Column("residence_postal_code", sa.String(length=10), nullable=True))
    op.add_column(
        "users",
        sa.Column("residence_country", sa.String(length=2), nullable=False, server_default="IT"),
    )

    # Grandfather every account that predates this feature as already
    # email-verified -- the mandatory verification-to-use-the-account rule
    # applies only to NEW registrations from now on (explicit product
    # decision, see docs/business-rules.md#account-gates). Deliberately does
    # NOT touch fiscal_code/residence -- the profile-completion popup DOES
    # apply retroactively to everyone, by design.
    op.execute("UPDATE users SET email_verified_at = COALESCE(email_verified_at, created_at) WHERE email_verified_at IS NULL")

    # -- email verification tokens ------------------------------------------
    op.create_table(
        "email_verification_tokens",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_email_verification_tokens_user_id"), "email_verification_tokens", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_email_verification_tokens_token_hash"), "email_verification_tokens", ["token_hash"], unique=True
    )

    # -- generic OTP codes (today: promoter-application confirmation) ------
    op.create_table(
        "otp_codes",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_otp_codes_user_id"), "otp_codes", ["user_id"], unique=False)
    op.create_index(op.f("ix_otp_codes_purpose"), "otp_codes", ["purpose"], unique=False)
    op.create_index(op.f("ix_otp_codes_code_hash"), "otp_codes", ["code_hash"], unique=False)

    # -- agent_profiles: collaboration-agreement acceptance -----------------
    op.add_column("agent_profiles", sa.Column("collaboration_contract_version", sa.String(length=32), nullable=True))
    op.add_column("agent_profiles", sa.Column("collaboration_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_profiles", sa.Column("collaboration_otp_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_profiles", "collaboration_otp_verified_at")
    op.drop_column("agent_profiles", "collaboration_accepted_at")
    op.drop_column("agent_profiles", "collaboration_contract_version")

    op.drop_index(op.f("ix_otp_codes_code_hash"), table_name="otp_codes")
    op.drop_index(op.f("ix_otp_codes_purpose"), table_name="otp_codes")
    op.drop_index(op.f("ix_otp_codes_user_id"), table_name="otp_codes")
    op.drop_table("otp_codes")

    op.drop_index(op.f("ix_email_verification_tokens_token_hash"), table_name="email_verification_tokens")
    op.drop_index(op.f("ix_email_verification_tokens_user_id"), table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")

    op.drop_column("users", "residence_country")
    op.drop_column("users", "residence_postal_code")
    op.drop_column("users", "residence_province")
    op.drop_column("users", "residence_city")
    op.drop_column("users", "residence_street")
    op.drop_column("users", "fiscal_code")
    op.drop_column("users", "privacy_accepted_at")
