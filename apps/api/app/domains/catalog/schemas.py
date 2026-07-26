import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProductVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_label: str
    name: str
    description: str
    image_url: str | None
    base_price_cents: int
    initial_fee_cents: int
    recurring_fee_cents: int
    billing_period: str
    valid_from: datetime
    valid_to: datetime | None
    status: str


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    code: str
    energy_type: str
    customer_type: str
    status: str


class ProductWithVersionsRead(ProductRead):
    versions: list[ProductVersionRead] = []


class ProductCatalogRead(ProductRead):
    """Product + its current (most recent) version, denormalized for list views --
    the admin catalog grid and the customer-facing marketplace both need
    name/description/photo/price without an N+1 detail fetch per product."""

    current_version: ProductVersionRead | None = None


class ProductCreate(BaseModel):
    code: str
    energy_type: str  # ELECTRICITY / GAS / DUAL_FUEL
    customer_type: str  # PRIVATE / SOLE_PROPRIETOR / PMI / CONDOMINIUM / ENERGY_INTENSIVE
    # Initial version, created together with the product -- a product with zero
    # versions can't be sold, so the marketplace form always creates both at once.
    version_label: str = "1.0"
    name: str
    description: str = ""
    image_url: str | None = None
    base_price_cents: int
    initial_fee_cents: int = 0
    recurring_fee_cents: int = 0
    billing_period: str = "MONTHLY"


class ProductVersionCreate(BaseModel):
    version_label: str
    name: str
    description: str = ""
    image_url: str | None = None
    base_price_cents: int
    initial_fee_cents: int = 0
    recurring_fee_cents: int = 0
    billing_period: str = "MONTHLY"


class ProductVersionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    image_url: str | None = None
    base_price_cents: int | None = None
    initial_fee_cents: int | None = None
    recurring_fee_cents: int | None = None
    status: str | None = None


class ProductUpdate(BaseModel):
    status: str | None = None
