import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

PRODUCT_TYPES = {"ENERGY_CONTRACT", "DIGITAL", "PHYSICAL", "SUBSCRIPTION"}
# INTERNAL is the safe default: never discountable in wallet credits, bank
# transfer only. DROPSHIPPING/PARTNER may accept a configurable credit
# discount -- see catalog/service.py for the enforcement that INTERNAL always
# stays at 0%.
PRODUCT_CATEGORIES = {"INTERNAL", "DROPSHIPPING", "PARTNER"}


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
    vat_percentage: float | None
    contract_duration_months: int | None
    # {rank_code: personal_token_cents} -- this product's per-rank gettone
    # override. A rank code missing from this dict falls back to that rank's
    # org-wide Rank.personal_token_cents at calculation time.
    commission_tokens: dict[str, int]
    credit_discount_percentage: int
    valid_from: datetime
    valid_to: datetime | None
    status: str

    @classmethod
    def from_version(cls, version) -> "ProductVersionRead":
        """ProductVersion has no vat_percentage column -- it lives inside the
        tax_configuration JSONB blob (already present on the model, previously
        unused). from_attributes=True can't compute that, so every call site
        builds through here instead of model_validate()."""
        tax_configuration = version.tax_configuration or {}
        return cls(
            id=version.id,
            version_label=version.version_label,
            name=version.name,
            description=version.description,
            image_url=version.image_url,
            base_price_cents=version.base_price_cents,
            initial_fee_cents=version.initial_fee_cents,
            recurring_fee_cents=version.recurring_fee_cents,
            billing_period=version.billing_period,
            vat_percentage=tax_configuration.get("vat_percentage"),
            contract_duration_months=version.contract_duration_months,
            commission_tokens=version.commission_tokens or {},
            credit_discount_percentage=version.credit_discount_percentage,
            valid_from=version.valid_from,
            valid_to=version.valid_to,
            status=version.status,
        )


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    code: str
    product_type: str
    energy_type: str | None
    customer_type: str
    status: str
    category: str


class ProductWithVersionsRead(ProductRead):
    versions: list[ProductVersionRead] = []


class ProductCatalogRead(ProductRead):
    """Product + its current (most recent) version, denormalized for list views --
    the admin catalog grid and the customer-facing marketplace both need
    name/description/photo/price without an N+1 detail fetch per product."""

    current_version: ProductVersionRead | None = None


class ProductCreate(BaseModel):
    code: str
    product_type: str = "ENERGY_CONTRACT"  # ENERGY_CONTRACT / DIGITAL / PHYSICAL / SUBSCRIPTION
    energy_type: str | None = None  # ELECTRICITY / GAS / DUAL_FUEL -- only for ENERGY_CONTRACT
    customer_type: str  # PRIVATE / SOLE_PROPRIETOR / PMI / CONDOMINIUM / ENERGY_INTENSIVE
    category: str = "INTERNAL"  # INTERNAL / DROPSHIPPING / PARTNER -- see PRODUCT_CATEGORIES
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
    vat_percentage: float | None = None
    contract_duration_months: int | None = 12
    commission_tokens: dict[str, int] = {}
    # Only meaningful when category != INTERNAL -- catalog/service.py forces
    # this to 0 for INTERNAL regardless of what's sent here.
    credit_discount_percentage: int = Field(default=0, ge=0, le=100)

    @field_validator("product_type")
    @classmethod
    def validate_product_type(cls, v: str) -> str:
        if v not in PRODUCT_TYPES:
            raise ValueError(f"product_type must be one of {sorted(PRODUCT_TYPES)}")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in PRODUCT_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(PRODUCT_CATEGORIES)}")
        return v


class ProductVersionCreate(BaseModel):
    version_label: str
    name: str
    description: str = ""
    image_url: str | None = None
    base_price_cents: int
    initial_fee_cents: int = 0
    recurring_fee_cents: int = 0
    billing_period: str = "MONTHLY"
    vat_percentage: float | None = None
    contract_duration_months: int | None = 12
    commission_tokens: dict[str, int] = {}
    credit_discount_percentage: int = Field(default=0, ge=0, le=100)


class ProductVersionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    image_url: str | None = None
    base_price_cents: int | None = None
    initial_fee_cents: int | None = None
    recurring_fee_cents: int | None = None
    vat_percentage: float | None = None
    contract_duration_months: int | None = None
    commission_tokens: dict[str, int] | None = None
    credit_discount_percentage: int | None = Field(default=None, ge=0, le=100)
    status: str | None = None


class ProductUpdate(BaseModel):
    status: str | None = None
    product_type: str | None = None
    energy_type: str | None = None
    category: str | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in PRODUCT_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(PRODUCT_CATEGORIES)}")
        return v
