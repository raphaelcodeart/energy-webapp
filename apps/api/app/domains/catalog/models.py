import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String
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
    # INTERNAL (Lial Energy's own supply -- bollette circolari, never
    # discountable in credits, bank transfer only) / DROPSHIPPING (imported
    # from an external supplier) / PARTNER (added on behalf of a
    # collaborator, e.g. merchandise). Orthogonal to product_type, which
    # describes WHAT the product is, not WHO supplies it or how it may be
    # paid -- see ProductVersion.credit_discount_percentage and
    # docs/cashback-partner-invoices-plan.md. Defaults to the safe/most
    # restrictive category (no credit discount) so an admin must opt a
    # product INTO accepting credits, never the reverse.
    category: Mapped[str] = mapped_column(String(16), default="INTERNAL")


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
    # Contract term length, e.g. 12 for a standard yearly energy contract. Null
    # for product types with no renewal concept (a one-off DIGITAL/PHYSICAL
    # purchase). Drives Contract.expires_at -- see contracts/service.py.
    # No `default=` here deliberately: SQLAlchemy's Python-side column default
    # fires even when the ORM constructor is given an explicit None, which
    # would silently turn "no renewal" (None) into 12 for every DIGITAL/
    # PHYSICAL product. The "12 unless told otherwise" default belongs one
    # layer up, in ProductCreate/ProductVersionCreate (schemas.py), where an
    # omitted field and an explicit null are still distinguishable.
    contract_duration_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_configuration: Mapped[dict] = mapped_column(JSONB, default=dict)
    commission_plan_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_plan_versions.id"), nullable=True
    )
    # {rank_code: personal_token_cents} -- the personal gettone a producer/ancestor
    # earns for THIS specific product, overriding Rank.personal_token_cents (which
    # stays as the org-wide fallback for a rank not listed here). This is what lets
    # e.g. "Luce Energia Circolare" pay a different token per rank than "Luce
    # Standard" -- see commissions/services/run_calculation.py::_build_chain.
    commission_tokens: Mapped[dict] = mapped_column(JSONB, default=dict)
    required_documents: Mapped[dict] = mapped_column(JSONB, default=dict)
    terms_version: Mapped[str] = mapped_column(String(32), default="1.0")
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    # 0-100: how much of THIS version's price the checkout may let a customer
    # pay from their internal wallet credit instead of bank transfer -- the
    # rest is always bank transfer, same as today. Versioned (not on Product)
    # because it's an economic term that can change release to release, same
    # reasoning as commission_tokens above. Enforced at the service layer
    # (catalog/service.py) to stay 0 whenever the parent Product.category is
    # INTERNAL -- see docs/cashback-partner-invoices-plan.md.
    credit_discount_percentage: Mapped[int] = mapped_column(Integer, default=0)
