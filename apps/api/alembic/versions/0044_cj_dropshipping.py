"""Shop Lial Partner: integrazione CJ Dropshipping.

Four tables of their own, next to (and independent from) the AliExpress
imported-products plugin -- see app/domains/cj_dropshipping/models.py:

- cj_settings: the CJ account (API key, rotated tokens) and pricing rules;
- cj_products / cj_variants: the CJ products chosen for sale, with the
  variants, CJ cost in USD and the customer price in EUR;
- cj_orders: a customer's purchase, its delivery address, frozen amounts and
  its life on CJ until delivery (CJ order id, status, tracking).

Plus wallet_transactions.reference_cj_order_id, so the LialCash spent on a
Shop Lial Partner order points at it like the other two order tables.

Revision ID: e6b2c4d8f193
Revises: d5a1b3c9e472
Create Date: 2026-09-17 11:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6b2c4d8f193"
down_revision: Union[str, None] = "d5a1b3c9e472"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def _ts() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "cj_settings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("api_key", sa.String(255), nullable=True),
        sa.Column("access_token", sa.String(500), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_token", sa.String(500), nullable=True),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_id", sa.String(64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sandbox", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("usd_eur_rate", sa.Numeric(10, 6), nullable=False, server_default="0.92"),
        sa.Column("markup_percentage", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("markup_fixed_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_rounding", sa.String(8), nullable=False, server_default="90"),
        sa.Column("shipping_mode", sa.String(16), nullable=False, server_default="CUSTOMER_PAYS"),
        sa.Column("default_credit_percentage", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("destination_country", sa.String(2), nullable=False, server_default="IT"),
        sa.Column("auto_forward", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_balance_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("last_balance_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        _ts(),
        sa.UniqueConstraint("organization_id", name="uq_cj_settings_organization_id"),
    )

    op.create_table(
        "cj_products",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("cj_pid", sa.String(64), nullable=False),
        sa.Column("cj_sku", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(500), nullable=True),
        sa.Column("description", sa.String(8000), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("images", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("category_name", sa.String(255), nullable=True),
        sa.Column("origin_country", sa.String(2), nullable=False, server_default="CN"),
        sa.Column("shipping_estimate_usd", sa.Numeric(10, 2), nullable=True),
        sa.Column("shipping_days", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("credit_discount_percentage", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("markup_percentage", sa.Integer(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_error", sa.String(500), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        _ts(),
        sa.UniqueConstraint("organization_id", "cj_pid", name="uq_cj_products_organization_id"),
    )
    op.create_index("ix_cj_products_organization_id", "cj_products", ["organization_id"])
    op.create_index("ix_cj_products_status", "cj_products", ["status"])

    op.create_table(
        "cj_variants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("product_id", UUID, sa.ForeignKey("cj_products.id"), nullable=False),
        sa.Column("cj_vid", sa.String(64), nullable=False),
        sa.Column("cj_sku", sa.String(128), nullable=True),
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("weight_g", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("price_override_cents", sa.BigInteger(), nullable=True),
        sa.Column("inventory", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("available_on_cj", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        _ts(),
        sa.UniqueConstraint("product_id", "cj_vid", name="uq_cj_variants_product_id"),
    )
    op.create_index("ix_cj_variants_product_id", "cj_variants", ["product_id"])

    op.create_table(
        "cj_orders",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("customer_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("cj_product_id", UUID, sa.ForeignKey("cj_products.id"), nullable=False),
        sa.Column("cj_variant_id", UUID, sa.ForeignKey("cj_variants.id"), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("shipping_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("credit_applied_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("credit_debit_transaction_id", UUID, sa.ForeignKey("wallet_transactions.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="AWAITING_PAYMENT"),
        sa.Column("payment_method", sa.String(16), nullable=False, server_default="BANK_TRANSFER"),
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("payment_proof_storage_key", sa.String(500), nullable=True),
        sa.Column("payment_proof_original_filename", sa.String(255), nullable=True),
        sa.Column("payment_proof_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(500), nullable=True),
        sa.Column("recipient_name", sa.String(128), nullable=False),
        sa.Column("recipient_phone", sa.String(32), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=False),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(128), nullable=False),
        sa.Column("province", sa.String(64), nullable=False),
        sa.Column("postal_code", sa.String(16), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="IT"),
        sa.Column("logistic_name", sa.String(64), nullable=False),
        sa.Column("origin_country", sa.String(2), nullable=False, server_default="CN"),
        sa.Column("shipping_days", sa.String(32), nullable=True),
        sa.Column("unit_cost_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("shipping_cost_usd", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("usd_eur_rate", sa.Numeric(10, 6), nullable=False),
        sa.Column("fulfillment_status", sa.String(16), nullable=False, server_default="NOT_SENT"),
        sa.Column("sandbox", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cj_order_id", sa.String(64), nullable=True),
        sa.Column("cj_order_status", sa.String(32), nullable=True),
        sa.Column("cj_amount_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("forwarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forwarded_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("forward_error", sa.String(500), nullable=True),
        sa.Column("tracking_number", sa.String(128), nullable=True),
        sa.Column("tracking_provider", sa.String(64), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cj_sync_at", sa.DateTime(timezone=True), nullable=True),
        _ts(),
        sa.UniqueConstraint("stripe_checkout_session_id", name="uq_cj_orders_stripe_checkout_session_id"),
        sa.CheckConstraint("credit_applied_cents >= 0", name="ck_cj_orders_credit_applied_non_negative"),
        sa.CheckConstraint("credit_applied_cents <= amount_cents", name="ck_cj_orders_credit_applied_not_over_amount"),
        sa.CheckConstraint("quantity > 0", name="ck_cj_orders_quantity_positive"),
    )
    op.create_index("ix_cj_orders_organization_id", "cj_orders", ["organization_id"])
    op.create_index("ix_cj_orders_customer_user_id", "cj_orders", ["customer_user_id"])
    op.create_index("ix_cj_orders_status", "cj_orders", ["status"])
    op.create_index("ix_cj_orders_fulfillment_status", "cj_orders", ["fulfillment_status"])
    op.create_index("ix_cj_orders_cj_order_id", "cj_orders", ["cj_order_id"])

    op.add_column("wallet_transactions", sa.Column("reference_cj_order_id", UUID, nullable=True))
    op.create_foreign_key(
        "fk_wallet_transactions_reference_cj_order_id_cj_orders", "wallet_transactions", "cj_orders",
        ["reference_cj_order_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_wallet_transactions_reference_cj_order_id_cj_orders", "wallet_transactions", type_="foreignkey")
    op.drop_column("wallet_transactions", "reference_cj_order_id")
    op.drop_table("cj_orders")
    op.drop_table("cj_variants")
    op.drop_table("cj_products")
    op.drop_table("cj_settings")
