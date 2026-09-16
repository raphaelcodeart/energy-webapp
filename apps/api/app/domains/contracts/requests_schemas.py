import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.domains.contracts.schemas import ContractRead, _validate_email, _validate_iban


class ContractRequestAddress(BaseModel):
    street: str
    city: str
    province: str
    postal_code: str

    @field_validator("street", "city", "province", mode="before")
    @classmethod
    def required_text(cls, v: str | None) -> str:
        cleaned = " ".join((v or "").split())
        if not cleaned:
            raise ValueError("campo obbligatorio")
        return cleaned

    @field_validator("postal_code", mode="before")
    @classmethod
    def validate_postal_code(cls, v: str | None) -> str:
        cleaned = (v or "").strip()
        if len(cleaned) != 5 or not cleaned.isdigit():
            raise ValueError("CAP non valido: sono 5 cifre")
        return cleaned


class ContractRequestHolder(ContractRequestAddress):
    """Everything asked once, at the start of a pratica: the holder and the
    supply address. Name and email required; PEC and IBAN optional -- not
    everyone has a PEC, and an IBAN can be added later."""

    holder_first_name: str
    holder_last_name: str
    email: str
    pec: str | None = None
    iban: str | None = None

    @field_validator("holder_first_name", "holder_last_name", mode="before")
    @classmethod
    def validate_name(cls, v: str | None) -> str:
        cleaned = " ".join((v or "").split())
        if not cleaned:
            raise ValueError("campo obbligatorio")
        return cleaned

    @field_validator("pec", "iban", mode="before")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    @field_validator("pec")
    @classmethod
    def validate_pec(cls, v: str | None) -> str | None:
        return _validate_email(v)

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        return _validate_iban(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        validated = _validate_email(v)
        if validated is None:
            raise ValueError("email obbligatoria")
        return validated


class ContractRequestCreate(ContractRequestHolder):
    #: Set by a promoter opening a pratica for one of their customers; left
    #: out by a customer opening their own.
    customer_id: uuid.UUID | None = None
    #: "Quanti POD hai?"
    points_count: int = 1
    #: The contract the customer started from in the catalog, pre-chosen for
    #: every POD.
    product_version_id: uuid.UUID | None = None


class ContractRequestPointsCount(BaseModel):
    count: int


class ContractRequestProductSet(BaseModel):
    product_version_id: uuid.UUID


class ContractRequestSummaryRead(BaseModel):
    id: uuid.UUID
    code: str
    customer_id: uuid.UUID
    customer_name: str | None = None
    customer_kind: str | None = None
    #: DRAFT / SUBMITTED / CANCELLED
    status: str
    created_at: datetime
    submitted_at: datetime | None = None
    updated_at: datetime | None = None
    created_by_role: str | None = None
    activated_by_promoter_id: uuid.UUID | None = None
    activated_by_promoter_name: str | None = None
    holder_name: str | None = None
    points_total: int = 0
    points_by_status: dict[str, int] = {}
    points_active: int = 0
    points_to_review: int = 0
    points_documents_pending: int = 0
    points_without_package: int = 0
    points_paid: int = 0
    points_payable: int = 0
    #: Sum of the frozen prices of the points still alive (not rejected or
    #: cancelled), VAT included where it applies.
    total_gross_cents: int = 0
    payment_plans: list[str] = []
    instalments_failed: int = 0


class ContractRequestPointRead(ContractRead):
    #: 1-based order of the POD in the pratica: "POD 1", "POD 2"...
    position: int = 0
    meter_number: str | None = None
    street: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    product_id: uuid.UUID | None = None
    documents_missing: int = 0
    documents_rejected: int = 0
    instalments_total: int | None = None
    instalments_paid: int = 0
    instalments_failed: int = 0
    billing_active: bool = False


class ContractRequestCheckoutRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    payment_plan: str
    total_cents: int
    instalment_cents: int
    contracts: int
    completed_at: datetime | None = None
    stripe_checkout_session_id: str
    stripe_subscription_id: str | None = None
    outcome: str | None = None


class ContractRequestDetailRead(ContractRequestSummaryRead):
    street: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    holder_first_name: str | None = None
    holder_last_name: str | None = None
    email: str | None = None
    pec: str | None = None
    iban: str | None = None
    points: list[ContractRequestPointRead] = []
    #: Staff only -- empty for customers and promoters.
    checkouts: list[ContractRequestCheckoutRead] = []


class ContractRequestPaymentLineRead(BaseModel):
    contract_id: uuid.UUID
    label: str
    gross_cents: int


class ContractRequestPaymentOptionRead(BaseModel):
    key: str
    label: str
    description: str
    instalments: int
    #: What the customer is charged each month (or once), all points together.
    instalment_cents: int
    total_cents: int
    rounding_difference_cents: int
    available: bool
    unavailable_reason: str | None = None


class ContractRequestPaymentOptionsRead(BaseModel):
    contract_request_id: uuid.UUID
    card_available: bool
    #: The contracts this payment would cover: sent, priced, not yet paid.
    lines: list[ContractRequestPaymentLineRead]
    total_gross_cents: int
    options: list[ContractRequestPaymentOptionRead]
    points_paid: int
    #: What the customer earns in LialCash across these contracts.
    cashback_total_cents: int
    #: PER_INSTALMENT / UPFRONT -- on an instalment plan, whether that
    #: cashback arrives a slice per instalment or all at the first one.
    cashback_mode: str = "PER_INSTALMENT"


class ContractRequestCheckoutRequest(BaseModel):
    payment_plan: str
