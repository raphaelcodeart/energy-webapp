"""Marketplace rules shared by the imported-product shops (Sessions 67-68).

- Paying by card costs more than by bank transfer: the percentage is an
  organization setting (organizations.settings.marketplace_card_surcharge_percentage,
  default 5 in code), the amount is frozen on each order:
  cj_orders.card_surcharge_cents and imported_product_orders.card_surcharge_cents
  (0 for bank transfer and for every order placed before this revision).
- LialCash never covers 100% of an imported product: new products start at
  30%, the administrator may raise it up to 99%. The one CJ product at 100%
  goes back to 30%, and the database refuses anything above 99.

Revision ID: d2a7b9c3e648
Revises: c1f6a8b2d537
Create Date: 2026-09-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2a7b9c3e648"
down_revision: Union[str, None] = "c1f6a8b2d537"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cj_orders", sa.Column("card_surcharge_cents", sa.BigInteger(), nullable=False, server_default="0")
    )
    op.add_column(
        "imported_product_orders",
        sa.Column("card_surcharge_cents", sa.BigInteger(), nullable=False, server_default="0"),
    )

    op.execute("UPDATE cj_products SET credit_discount_percentage = 30 WHERE credit_discount_percentage > 99")
    op.execute("UPDATE imported_products SET credit_discount_percentage = 30 WHERE credit_discount_percentage > 99")
    op.execute("UPDATE cj_settings SET default_credit_percentage = 30")
    op.alter_column("cj_settings", "default_credit_percentage", server_default="30")
    op.execute("ALTER TABLE cj_products ADD CONSTRAINT ck_cj_products_credit_below_100 CHECK (credit_discount_percentage BETWEEN 0 AND 99)")
    op.execute("ALTER TABLE imported_products ADD CONSTRAINT ck_imported_products_credit_below_100 CHECK (credit_discount_percentage BETWEEN 0 AND 99)")
    op.execute("ALTER TABLE cj_settings ADD CONSTRAINT ck_cj_settings_default_credit_below_100 CHECK (default_credit_percentage BETWEEN 0 AND 99)")


def downgrade() -> None:
    op.execute("ALTER TABLE cj_settings DROP CONSTRAINT ck_cj_settings_default_credit_below_100")
    op.execute("ALTER TABLE imported_products DROP CONSTRAINT ck_imported_products_credit_below_100")
    op.execute("ALTER TABLE cj_products DROP CONSTRAINT ck_cj_products_credit_below_100")
    op.alter_column("cj_settings", "default_credit_percentage", server_default=None)
    op.drop_column("imported_product_orders", "card_surcharge_cents")
    op.drop_column("cj_orders", "card_surcharge_cents")
