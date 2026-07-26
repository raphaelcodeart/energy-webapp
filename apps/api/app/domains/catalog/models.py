import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class Product(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "products"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(64))
    # ENERGY_CONTRACT / DIGITAL / PHYSICAL / SUBSCRIPTION -- non-energy products
    # (e.g. a digital add-on or a physical accessory sold alongside contracts)
    # leave energy_type null, since it has no meaning for them.
    product_type: Mapped[str] = mapped_column(String(32), default="ENERGY_CONTRACT")
    energy_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ELECTRICITY / GAS / DUAL_FUEL
    customer_type: Mapped[str] = mapped_column(String(32))  # PRIVATE / SOLE_PROPRIETOR / PMI / CONDOMINIUM / ENERGY_INTENSIVE
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class ProductVersion(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "product_versions"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), index=True)
    version_label: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(2000), default="")
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    base_price_cents: Mapped[int] = mapped_column(BigInteger)
    initial_fee_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    recurring_fee_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    billing_period: Mapped[str] = mapped_column(String(16), default="MONTHLY")
    tax_configuration: Mapped[dict] = mapped_column(JSONB, default=dict)
    commission_plan_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_plan_versions.id"), nullable=True
    )
    required_documents: Mapped[dict] = mapped_column(JSONB, default=dict)
    terms_version: Mapped[str] = mapped_column(String(32), default="1.0")
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
