"""Pratica: l'indirizzo si chiede una volta, i POD si contano e basta.

Business rule (Session 53), from the business: the activation asks every
holder detail once at the start -- including the supply address -- together
with "quanti POD hai?". The points are then created already, and for each one
the customer only picks the contract to activate. The POD/PDR code is not
asked at all.

- contract_requests: street, city, province, postal_code -- the address every
  point of the pratica starts from (a point can still be moved to another).
- supply_points.energy_type becomes nullable: a point created by the count is
  neither luce nor gas until its package is chosen, and the package is what
  decides it. Nothing past DRAFT lacks a package (ck_contracts_product_
  required), so nothing sent lacks an energy type.

Revision ID: d5a1b3c9e472
Revises: c4f9a2b7d318
Create Date: 2026-09-16 19:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5a1b3c9e472"
down_revision: Union[str, None] = "c4f9a2b7d318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contract_requests", sa.Column("street", sa.String(length=255), nullable=True))
    op.add_column("contract_requests", sa.Column("city", sa.String(length=128), nullable=True))
    op.add_column("contract_requests", sa.Column("province", sa.String(length=8), nullable=True))
    op.add_column("contract_requests", sa.Column("postal_code", sa.String(length=16), nullable=True))
    # The pratiche that already exist take the address of their first point.
    op.execute(
        """
        UPDATE contract_requests r
        SET street = a.street, city = a.city, province = a.province, postal_code = a.postal_code
        FROM contracts c
        JOIN supply_points sp ON sp.id = c.supply_point_id
        JOIN addresses a ON a.id = sp.supply_address_id
        WHERE c.contract_request_id = r.id
        """
    )
    op.alter_column("supply_points", "energy_type", nullable=True)


def downgrade() -> None:
    op.execute("UPDATE supply_points SET energy_type = 'ELECTRICITY' WHERE energy_type IS NULL")
    op.alter_column("supply_points", "energy_type", nullable=False)
    op.drop_column("contract_requests", "postal_code")
    op.drop_column("contract_requests", "province")
    op.drop_column("contract_requests", "city")
    op.drop_column("contract_requests", "street")
