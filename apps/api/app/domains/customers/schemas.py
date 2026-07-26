import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    kind: str
    fiscal_code: str | None
    vat_number: str | None
    email: str
    phone: str | None
    pec: str | None
    display_name: str


class CustomerCreate(BaseModel):
    kind: str  # PRIVATE / SOLE_PROPRIETOR / COMPANY / CONDOMINIUM
    email: EmailStr
    phone: str | None = None
    pec: str | None = None
    fiscal_code: str | None = None
    vat_number: str | None = None
    # Required for PRIVATE / SOLE_PROPRIETOR:
    first_name: str | None = None
    last_name: str | None = None
    # Required for COMPANY / CONDOMINIUM:
    company_name: str | None = None
    legal_form: str | None = None
    sdi_code: str | None = None

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        allowed = {"PRIVATE", "SOLE_PROPRIETOR", "COMPANY", "CONDOMINIUM"}
        if v not in allowed:
            raise ValueError(f"kind must be one of {sorted(allowed)}")
        return v


class CustomerUpdate(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None
    pec: str | None = None
    fiscal_code: str | None = None
    vat_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None


class AddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    street: str
    city: str
    province: str
    postal_code: str
    country: str


class SupplyPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str | None
    energy_type: str
    pod_code: str | None
    pdr_code: str | None
    meter_number: str | None
    supply_address_id: uuid.UUID


class SupplyPointCreate(BaseModel):
    label: str | None = None  # auto-computed from energy_type + address if omitted
    energy_type: str  # ELECTRICITY / GAS
    pod_code: str | None = None
    pdr_code: str | None = None
    meter_number: str | None = None
    street: str
    city: str
    province: str
    postal_code: str
    country: str = "IT"


class SupplyPointUpdate(BaseModel):
    label: str | None = None


class CustomerDetailRead(CustomerRead):
    addresses: list[AddressRead] = []
    supply_points: list[SupplyPointRead] = []
