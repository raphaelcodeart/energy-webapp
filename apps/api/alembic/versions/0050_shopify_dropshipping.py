"""Marketplace 3: integrazione Shopify dropshipping (Session 68).

Four tables of their own, next to (and independent from) AliExpress and CJ --
see app/domains/shopify_dropshipping/models.py:

- shopify_settings: the Shopify store (domain, Admin API token) and the
  pricing rules;
- shopify_products / shopify_variants: the store products chosen for sale,
  with the store's cost/price and the customer price in EUR;
- shopify_orders: a customer's purchase, its delivery address, frozen amounts
  (card surcharge included) and its life in the store until delivery.

Plus wallet_transactions.reference_shopify_order_id, so the LialCash spent on
a Marketplace 3 order points at it like the other order tables.

Revision ID: f3b8c1d9e274
Revises: d2a7b9c3e648
Create Date: 2026-09-19 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3b8c1d9e274"
down_revision: Union[str, None] = "d2a7b9c3e648"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def _ts() -> sa.Column:
    return sa.Column("created_at", TS, nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "shopify_settings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("shop_domain", sa.String(255), nullable=True),
        sa.Column("access_token", sa.String(255), nullable=True),
        sa.Column("api_version", sa.String(16), nullable=False, server_default="2025-07"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("shop_name", sa.String(255), nullable=True),
        sa.Column("shop_currency", sa.String(3), nullable=True),
        sa.Column("currency_rate", sa.Numeric(10, 6), nullable=False, server_default="1"),
        sa.Column("price_basis", sa.String(8), nullable=False, server_default="COST"),
        sa.Column("markup_percentage", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("markup_fixed_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_rounding", sa.String(8), nullable=False, server_default="90"),
        sa.Column("shipping_mode", sa.String(16), nullable=False, server_default="CUSTOMER_PAYS"),
        sa.Column("shipping_flat_cents", sa.Integer(), nullable=False, server_default="590"),
        sa.Column("shipping_days", sa.String(32), nullable=True, server_default="7-15"),
        sa.Column("default_credit_percentage", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("auto_forward", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_connected_at", TS, nullable=True),
        sa.Column("updated_at", TS, nullable=True),
        _ts(),
        sa.UniqueConstraint("organization_id", name="uq_shopify_settings_organization_id"),
    )

    op.create_table(
        "shopify_products",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("shopify_product_id", sa.String(128), nullable=False),
        sa.Column("handle", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_title", sa.String(500), nullable=True),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("description", sa.String(8000), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("images", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("credit_discount_percentage", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("markup_percentage", sa.Integer(), nullable=True),
        sa.Column("last_synced_at", TS, nullable=True),
        sa.Column("sync_error", sa.String(500), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", TS, nullable=True),
        _ts(),
        sa.UniqueConstraint(
            "organization_id", "shopify_product_id", name="uq_shopify_products_organization_id_shopify_product_id"
        ),
        sa.CheckConstraint(
            "credit_discount_percentage >= 0 AND credit_discount_percentage <= 99",
            name="ck_shopify_products_credit_discount_percentage_below_100",
        ),
    )
    op.create_index("ix_shopify_products_organization_id", "shopify_products", ["organization_id"])
    op.create_index("ix_shopify_products_status", "shopify_products", ["status"])

    op.create_table(
        "shopify_variants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("product_id", UUID, sa.ForeignKey("shopify_products.id"), nullable=False),
        sa.Column("shopify_variant_id", sa.String(128), nullable=False),
        sa.Column("sku", sa.String(128), nullable=True),
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("cost_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("source_price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("price_override_cents", sa.BigInteger(), nullable=True),
        sa.Column("inventory", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("available_in_store", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", TS, nullable=True),
        _ts(),
        sa.UniqueConstraint(
            "product_id", "shopify_variant_id", name="uq_shopify_variants_product_id_shopify_variant_id"
        ),
    )
    op.create_index("ix_shopify_variants_product_id", "shopify_variants", ["product_id"])

    op.create_table(
        "shopify_orders",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("customer_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("shopify_product_id", UUID, sa.ForeignKey("shopify_products.id"), nullable=False),
        sa.Column("shopify_variant_id", UUID, sa.ForeignKey("shopify_variants.id"), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("shipping_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("credit_applied_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("card_surcharge_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("credit_debit_transaction_id", UUID, sa.ForeignKey("wallet_transactions.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="AWAITING_PAYMENT"),
        sa.Column("payment_method", sa.String(16), nullable=False, server_default="BANK_TRANSFER"),
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("payment_proof_storage_key", sa.String(500), nullable=True),
        sa.Column("payment_proof_original_filename", sa.String(255), nullable=True),
        sa.Column("payment_proof_uploaded_at", TS, nullable=True),
        sa.Column("paid_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("paid_at", TS, nullable=True),
        sa.Column("cancelled_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", TS, nullable=True),
        sa.Column("cancellation_reason", sa.String(500), nullable=True),
        sa.Column("recipient_name", sa.String(128), nullable=False),
        sa.Column("recipient_phone", sa.String(32), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=False),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("province", sa.String(64), nullable=False),
        sa.Column("postal_code", sa.String(16), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="IT"),
        sa.Column("shipping_days", sa.String(32), nullable=True),
        sa.Column("unit_cost_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency_rate", sa.Numeric(10, 6), nullable=False, server_default="1"),
        sa.Column("fulfillment_status", sa.String(16), nullable=False, server_default="NOT_SENT"),
        sa.Column("shopify_draft_order_id", sa.String(128), nullable=True),
        sa.Column("shopify_order_id", sa.String(128), nullable=True),
        sa.Column("shopify_order_name", sa.String(64), nullable=True),
        sa.Column("shopify_fulfillment_status", sa.String(32), nullable=True),
        sa.Column("forwarded_at", TS, nullable=True),
        sa.Column("forwarded_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("forward_error", sa.String(500), nullable=True),
        sa.Column("tracking_number", sa.String(128), nullable=True),
        sa.Column("tracking_url", sa.String(1000), nullable=True),
        sa.Column("tracking_company", sa.String(128), nullable=True),
        sa.Column("shipped_at", TS, nullable=True),
        sa.Column("delivered_at", TS, nullable=True),
        sa.Column("last_sync_at", TS, nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", TS, nullable=True),
        sa.Column("next_retry_at", TS, nullable=True),
        sa.Column("last_error_kind", sa.String(24), nullable=True),
        _ts(),
        sa.UniqueConstraint("stripe_checkout_session_id", name="uq_shopify_orders_stripe_checkout_session_id"),
        sa.CheckConstraint("credit_applied_cents >= 0", name="ck_shopify_orders_credit_applied_non_negative"),
        sa.CheckConstraint(
            "credit_applied_cents <= amount_cents", name="ck_shopify_orders_credit_applied_not_over_amount"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_shopify_orders_quantity_positive"),
    )
    op.create_index("ix_shopify_orders_organization_id", "shopify_orders", ["organization_id"])
    op.create_index("ix_shopify_orders_customer_user_id", "shopify_orders", ["customer_user_id"])
    op.create_index("ix_shopify_orders_status", "shopify_orders", ["status"])
    op.create_index("ix_shopify_orders_fulfillment_status", "shopify_orders", ["fulfillment_status"])
    op.create_index("ix_shopify_orders_shopify_order_id", "shopify_orders", ["shopify_order_id"])
    op.create_index("ix_shopify_orders_next_retry_at", "shopify_orders", ["next_retry_at"])

    op.add_column("wallet_transactions", sa.Column("reference_shopify_order_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_wallet_transactions_reference_shopify_order_id_shopi_ef35", "wallet_transactions", "shopify_orders",
        ["reference_shopify_order_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_wallet_transactions_reference_shopify_order_id_shopi_ef35", "wallet_transactions", type_="foreignkey"
    )
    op.drop_column("wallet_transactions", "reference_shopify_order_id")
    op.drop_table("shopify_orders")
    op.drop_table("shopify_variants")
    op.drop_table("shopify_products")
    op.drop_table("shopify_settings")
