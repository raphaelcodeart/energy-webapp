"""Contract economics, attribution and payment foundations.

Three things a Lial Energy contract could not express before, all added as
nullable columns so every one of the 18 contracts currently in production
keeps working untouched:

1. WHO built it. Until now the creator was only recoverable indirectly, from
   the actor on the first `contract_status_history` row. `created_by_user_id`
   / `created_by_role` / `activated_by_promoter_id` make the one question the
   business actually asks -- "did the customer sign this themselves, or did a
   promoter fill it in for them?" -- answerable at a glance.
   `first_referrer_agent_id` freezes the promoter who originally brought the
   customer in, which is deliberately NOT the same person as
   `contract_attributions.producer_agent_id` (who earns the recursive
   commission): a promoter assisting someone else's customer must never take
   over the first-referrer bonus.

2. WHAT it costs. VAT existed only as a number two React components
   multiplied the price by for display; no server code ever computed it.
   `net_amount_cents` / `vat_rate` / `vat_amount_cents` / `gross_amount_cents`
   snapshot the breakdown computed by `catalog/pricing.py` at creation, so an
   admin changing a product's rate tomorrow can never restate a contract
   somebody already signed. `customer_kind` is frozen alongside them because
   it is what decides whether VAT applies at all.

3. HOW it gets paid. No contract has ever been paid through this app (every
   row in production is DRAFT / DOCUMENTS_PENDING / UNDER_REVIEW), so none of
   the Stripe columns restate existing behaviour -- they are the payment step
   that did not exist. `terms_accepted_*` keeps proof of which version of the
   contract text was accepted, by whom, from where.

On `product_versions`: `contract_cashback_percentage` is the INTERNAL
counterpart of `cashback_enabled` -- automatic LialCash on a Lial Energy
service, with no 5% surcharge, the partner-invoice rule being explicitly NOT
applicable to our own services. `first_referrer_bonus_enabled` /
`first_referrer_bonus_cents` make the extra bonus a value an admin sets per
product instead of a price comparison in a controller. All three default to
off, so every existing product behaves exactly as it does today until
somebody opts it in.

On `products.customer_type`: the column existed but nothing ever read it, and
its vocabulary (PMI, ENERGY_INTENSIVE, SOLE_PROPRIETOR) did not line up with
`customers.kind` (COMPANY, ...), so the two could never be compared. It now
holds the binary business answer, PRIVATE / BUSINESS / BOTH. Existing rows
are migrated to BOTH -- not to their literal old value -- precisely because
that is the behaviour-preserving choice: today no product is filtered by
buyer type at all, so every product must stay visible to everyone until an
admin narrows it deliberately.

Revision ID: b4e2f81c05a9
Revises: a1c7e920f4b6
Create Date: 2026-09-13 23:40:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4e2f81c05a9"
down_revision: Union[str, None] = "a1c7e920f4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- contracts: who built it -------------------------------------------
    op.add_column("contracts", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contracts", sa.Column("created_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("contracts", sa.Column("created_by_role", sa.String(length=32), nullable=True))
    op.add_column(
        "contracts", sa.Column("activated_by_promoter_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "contracts", sa.Column("first_referrer_agent_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_contracts_created_by_user_id_users", "contracts", "users", ["created_by_user_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_contracts_activated_by_promoter_id_agent_profiles",
        "contracts", "agent_profiles", ["activated_by_promoter_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_contracts_first_referrer_agent_id_agent_profiles",
        "contracts", "agent_profiles", ["first_referrer_agent_id"], ["id"],
    )

    # --- contracts: frozen economics ---------------------------------------
    op.add_column("contracts", sa.Column("customer_kind", sa.String(length=32), nullable=True))
    op.add_column("contracts", sa.Column("net_amount_cents", sa.BigInteger(), nullable=True))
    op.add_column("contracts", sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column("contracts", sa.Column("vat_amount_cents", sa.BigInteger(), nullable=True))
    op.add_column("contracts", sa.Column("gross_amount_cents", sa.BigInteger(), nullable=True))

    # --- contracts: payment -------------------------------------------------
    op.add_column("contracts", sa.Column("payment_plan", sa.String(length=16), nullable=True))
    op.add_column("contracts", sa.Column("payment_method", sa.String(length=16), nullable=True))
    op.add_column("contracts", sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True))
    op.add_column("contracts", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
    op.add_column("contracts", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True))
    op.add_column("contracts", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contracts", sa.Column("cashback_credited_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(
        "uq_contracts_stripe_checkout_session_id", "contracts", ["stripe_checkout_session_id"]
    )

    # --- contracts: proof of acceptance -------------------------------------
    op.add_column("contracts", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "contracts", sa.Column("terms_accepted_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("contracts", sa.Column("terms_version", sa.String(length=32), nullable=True))
    op.add_column("contracts", sa.Column("terms_accepted_ip", sa.String(length=45), nullable=True))
    op.add_column("contracts", sa.Column("terms_accepted_user_agent", sa.String(length=500), nullable=True))
    op.create_foreign_key(
        "fk_contracts_terms_accepted_by_user_id_users", "contracts", "users", ["terms_accepted_by_user_id"], ["id"]
    )

    # --- product_versions: contract cashback + first-referrer bonus ---------
    op.add_column(
        "product_versions",
        sa.Column("contract_cashback_percentage", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "product_versions",
        sa.Column("first_referrer_bonus_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "product_versions",
        sa.Column("first_referrer_bonus_cents", sa.BigInteger(), nullable=False, server_default="0"),
    )

    # --- products.customer_type: PRIVATE / BUSINESS / BOTH ------------------
    # Everything becomes BOTH: nothing filters on this column today, so BOTH
    # is the only value that leaves the catalog looking identical after the
    # migration. Narrowing a product to privati or aziende is an admin
    # decision, taken deliberately, product by product.
    op.execute("UPDATE products SET customer_type = 'BOTH'")


def downgrade() -> None:
    op.drop_column("product_versions", "first_referrer_bonus_cents")
    op.drop_column("product_versions", "first_referrer_bonus_enabled")
    op.drop_column("product_versions", "contract_cashback_percentage")

    op.drop_constraint("fk_contracts_terms_accepted_by_user_id_users", "contracts", type_="foreignkey")
    op.drop_column("contracts", "terms_accepted_user_agent")
    op.drop_column("contracts", "terms_accepted_ip")
    op.drop_column("contracts", "terms_version")
    op.drop_column("contracts", "terms_accepted_by_user_id")
    op.drop_column("contracts", "terms_accepted_at")

    op.drop_constraint("uq_contracts_stripe_checkout_session_id", "contracts", type_="unique")
    op.drop_column("contracts", "cashback_credited_at")
    op.drop_column("contracts", "paid_at")
    op.drop_column("contracts", "stripe_subscription_id")
    op.drop_column("contracts", "stripe_customer_id")
    op.drop_column("contracts", "stripe_checkout_session_id")
    op.drop_column("contracts", "payment_method")
    op.drop_column("contracts", "payment_plan")

    op.drop_column("contracts", "gross_amount_cents")
    op.drop_column("contracts", "vat_amount_cents")
    op.drop_column("contracts", "vat_rate")
    op.drop_column("contracts", "net_amount_cents")
    op.drop_column("contracts", "customer_kind")

    op.drop_constraint("fk_contracts_first_referrer_agent_id_agent_profiles", "contracts", type_="foreignkey")
    op.drop_constraint("fk_contracts_activated_by_promoter_id_agent_profiles", "contracts", type_="foreignkey")
    op.drop_constraint("fk_contracts_created_by_user_id_users", "contracts", type_="foreignkey")
    op.drop_column("contracts", "first_referrer_agent_id")
    op.drop_column("contracts", "activated_by_promoter_id")
    op.drop_column("contracts", "created_by_role")
    op.drop_column("contracts", "created_by_user_id")
    op.drop_column("contracts", "updated_at")
