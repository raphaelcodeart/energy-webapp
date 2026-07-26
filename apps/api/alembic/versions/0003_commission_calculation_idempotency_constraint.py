"""add unique constraint on commission_calculations(contract_id, trigger_event_id)

Revision ID: 3f7c1a9b2e6d
Revises: 8a1f2c9e3b4d
Create Date: 2026-07-26 00:00:00.000000

DB-level backstop for the application-level (SELECT-then-INSERT) idempotency
check in run_calculation_for_contract() -- see
docs/paid-contract-commission-audit.md, Problem #3.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f7c1a9b2e6d"
down_revision: Union[str, None] = "8a1f2c9e3b4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_commission_calculations_contract_trigger",
        "commission_calculations",
        ["contract_id", "trigger_event_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_commission_calculations_contract_trigger",
        "commission_calculations",
        type_="unique",
    )
