"""La pratica di attivazione: più punti di fornitura, un pagamento solo.

Business rule (Session 52): a customer with ten POD signs ten contracts --
ten independent contracts, each with its own package, approval, instalments
and commissions -- but fills in the holder data and the shared documents
once, and pays once. The pratica (`contract_requests`) is the container that
makes that possible; it owns nothing a contract already owns.

- contract_requests: holder data, lifecycle of the pratica itself
  (DRAFT while being filled in, SUBMITTED once sent, CANCELLED).
- contract_request_checkouts: one row per Stripe Checkout Session opened for
  a pratica, with exactly which contracts and amounts it covers -- so a
  session that completes is honoured even if the customer opened a newer
  one in another tab, and a contract paid twice is detected, not missed.
- contracts.contract_request_id: every contract belongs to a pratica.
  Existing contracts are backfilled one pratica each, reusing the contract's
  own id as the pratica's id, so the mapping is readable in the data.
- contracts.product_version_id becomes nullable, but only while the contract
  is a DRAFT (or was cancelled as one): the package is chosen per point after
  the documents, and a CHECK constraint keeps "no package" from ever getting
  past DRAFT.
- contracts.stripe_subscription_item_id: which line of the pratica's single
  subscription is this contract's -- how each monthly invoice line reaches
  the right contract.
- contracts.billing_stopped_at: an administrator stopped charging this one
  contract (removed its line from the subscription).
- contract_instalments: the invoice id is no longer unique by itself -- one
  monthly invoice now pays N contracts -- only per contract.
- documents: a document belongs to a contract OR to a pratica (identity,
  fiscal code, visura: uploaded once for all the points), never both.

Revision ID: c4f9a2b7d318
Revises: b3e8f1a6c257
Create Date: 2026-09-16 18:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4f9a2b7d318"
down_revision: Union[str, None] = "b3e8f1a6c257"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contract_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("holder_first_name", sa.String(length=128), nullable=True),
        sa.Column("holder_last_name", sa.String(length=128), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("pec", sa.String(length=320), nullable=True),
        sa.Column("iban", sa.String(length=34), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_role", sa.String(length=32), nullable=True),
        sa.Column(
            "activated_by_promoter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_profiles.id"), nullable=True
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_contract_requests_organization_id", "contract_requests", ["organization_id"])
    op.create_index("ix_contract_requests_customer_id", "contract_requests", ["customer_id"])
    op.create_index("ix_contract_requests_status", "contract_requests", ["status"])

    op.create_table(
        "contract_request_checkouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "contract_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_requests.id"), nullable=False
        ),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=False),
        sa.Column("payment_plan", sa.String(length=16), nullable=False),
        sa.Column("lines", postgresql.JSONB(), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("instalment_cents", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("outcome", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("stripe_checkout_session_id", name="uq_contract_request_checkouts_stripe_checkout_session_id"),
    )
    op.create_index(
        "ix_contract_request_checkouts_organization_id", "contract_request_checkouts", ["organization_id"]
    )
    op.create_index(
        "ix_contract_request_checkouts_contract_request_id", "contract_request_checkouts", ["contract_request_id"]
    )

    op.add_column("contracts", sa.Column("contract_request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("contracts", sa.Column("stripe_subscription_item_id", sa.String(length=255), nullable=True))
    op.add_column("contracts", sa.Column("billing_stopped_at", sa.DateTime(timezone=True), nullable=True))

    # One pratica per existing contract, same id, same holder data. A DRAFT
    # contract becomes a DRAFT pratica (still being filled in); anything else
    # has already been sent.
    op.execute(
        """
        INSERT INTO contract_requests (
            id, organization_id, customer_id, status,
            holder_first_name, holder_last_name, email, pec, iban,
            created_by_user_id, created_by_role, activated_by_promoter_id,
            submitted_at, created_at, updated_at
        )
        SELECT
            c.id, c.organization_id, c.customer_id,
            CASE WHEN c.status = 'DRAFT' THEN 'DRAFT' ELSE 'SUBMITTED' END,
            c.holder_first_name, c.holder_last_name, c.email, c.pec, c.iban,
            c.created_by_user_id, c.created_by_role, c.activated_by_promoter_id,
            CASE WHEN c.status = 'DRAFT' THEN NULL ELSE c.created_at END,
            c.created_at, c.updated_at
        FROM contracts c
        """
    )
    op.execute("UPDATE contracts SET contract_request_id = id")
    op.alter_column("contracts", "contract_request_id", nullable=False)
    op.create_foreign_key(
        "fk_contracts_contract_request_id_contract_requests", "contracts", "contract_requests",
        ["contract_request_id"], ["id"],
    )
    op.create_index("ix_contracts_contract_request_id", "contracts", ["contract_request_id"])
    op.create_unique_constraint(
        "uq_contracts_stripe_subscription_item_id", "contracts", ["stripe_subscription_item_id"]
    )

    op.alter_column("contracts", "product_version_id", nullable=True)
    op.execute(
        "ALTER TABLE contracts ADD CONSTRAINT ck_contracts_product_required "
        "CHECK (product_version_id IS NOT NULL OR status IN ('DRAFT', 'CANCELLED'))"
    )

    op.drop_constraint("uq_contract_instalments_stripe_invoice_id", "contract_instalments", type_="unique")
    op.create_unique_constraint(
        "uq_contract_instalments_contract_id", "contract_instalments", ["contract_id", "stripe_invoice_id"]
    )

    op.add_column("documents", sa.Column("contract_request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_documents_contract_request_id_contract_requests", "documents", "contract_requests",
        ["contract_request_id"], ["id"],
    )
    op.create_index("ix_documents_contract_request_id", "documents", ["contract_request_id"])
    op.alter_column("documents", "contract_id", nullable=True)
    op.execute(
        "ALTER TABLE documents ADD CONSTRAINT ck_documents_one_owner "
        "CHECK (num_nonnulls(contract_id, contract_request_id) = 1)"
    )


def downgrade() -> None:
    # Only reversible while no pratica has more than one contract and no
    # document or contract relies on the new nullability -- which is exactly
    # what the checks below refuse to discard silently.
    op.execute("ALTER TABLE documents DROP CONSTRAINT ck_documents_one_owner")
    op.execute("DELETE FROM documents WHERE contract_id IS NULL")
    op.alter_column("documents", "contract_id", nullable=False)
    op.drop_index("ix_documents_contract_request_id", table_name="documents")
    op.drop_constraint("fk_documents_contract_request_id_contract_requests", "documents", type_="foreignkey")
    op.drop_column("documents", "contract_request_id")

    op.drop_constraint("uq_contract_instalments_contract_id", "contract_instalments", type_="unique")
    op.create_unique_constraint(
        "uq_contract_instalments_stripe_invoice_id", "contract_instalments", ["stripe_invoice_id"]
    )

    op.execute("ALTER TABLE contracts DROP CONSTRAINT ck_contracts_product_required")
    op.alter_column("contracts", "product_version_id", nullable=False)
    op.drop_constraint("uq_contracts_stripe_subscription_item_id", "contracts", type_="unique")
    op.drop_index("ix_contracts_contract_request_id", table_name="contracts")
    op.drop_constraint("fk_contracts_contract_request_id_contract_requests", "contracts", type_="foreignkey")
    op.drop_column("contracts", "billing_stopped_at")
    op.drop_column("contracts", "stripe_subscription_item_id")
    op.drop_column("contracts", "contract_request_id")

    op.drop_index("ix_contract_request_checkouts_contract_request_id", table_name="contract_request_checkouts")
    op.drop_index("ix_contract_request_checkouts_organization_id", table_name="contract_request_checkouts")
    op.drop_table("contract_request_checkouts")
    op.drop_index("ix_contract_requests_status", table_name="contract_requests")
    op.drop_index("ix_contract_requests_customer_id", table_name="contract_requests")
    op.drop_index("ix_contract_requests_organization_id", table_name="contract_requests")
    op.drop_table("contract_requests")
