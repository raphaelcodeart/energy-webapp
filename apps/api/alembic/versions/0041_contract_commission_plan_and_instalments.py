"""Anteprima provvigioni accettata, e le rate del contratto.

Two tables, no column added to an existing one.

contract_commission_plans -- the commission preview an administrator accepted
before a contract could activate, stored verbatim so it can be reopened as a
log. One per contract.

contract_instalments -- one row per payment the customer owes (1, 3 or 12).
Commissions are now released one instalment at a time: each paid row on an
active contract emits exactly one outbox event, and the engine pays 1/N of
each beneficiary's commission for it. The two UNIQUE constraints are what stop
a Stripe confirmation and a manual confirmation from paying the same month
twice.

Revision ID: b3e8f1a6c257
Revises: a7d2e94c3b10
Create Date: 2026-09-16 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3e8f1a6c257"
down_revision: Union[str, None] = "a7d2e94c3b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contract_commission_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("accepted_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payment_plan", sa.String(length=16), nullable=True),
        sa.Column("total_commission_cents", sa.BigInteger(), nullable=False),
        sa.Column("preview", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("contract_id", name="uq_contract_commission_plans_contract_id"),
    )
    op.create_index("ix_contract_commission_plans_organization_id", "contract_commission_plans", ["organization_id"])

    op.create_table(
        "contract_instalments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("instalments_total", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_source", sa.String(length=16), nullable=True),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("stripe_invoice_id", sa.String(length=255), nullable=True),
        sa.Column("commission_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("commission_released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "commission_calculation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("commission_calculations.id"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("contract_id", "number", name="uq_contract_instalments_contract_number"),
        sa.UniqueConstraint("stripe_invoice_id", name="uq_contract_instalments_stripe_invoice_id"),
    )
    op.create_index("ix_contract_instalments_organization_id", "contract_instalments", ["organization_id"])
    op.create_index("ix_contract_instalments_contract_id", "contract_instalments", ["contract_id"])


def downgrade() -> None:
    op.drop_table("contract_instalments")
    op.drop_table("contract_commission_plans")
