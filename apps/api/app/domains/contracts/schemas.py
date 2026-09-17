import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.domains.customers.schemas import SupplyPointCreate

IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9A-Z]{13,32}$")
# Deliberately simple (not RFC 5322): good enough to catch typos in a form
# field without pulling in a dedicated email-validation dependency, same
# pragmatic bar as IBAN_PATTERN above.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_iban(v: str | None) -> str | None:
    if v is None:
        return v
    cleaned = v.replace(" ", "").upper()
    if not IBAN_PATTERN.match(cleaned):
        raise ValueError("IBAN non valido")
    return cleaned


def _validate_email(v: str | None) -> str | None:
    if v is None:
        return v
    cleaned = v.strip()
    if not EMAIL_PATTERN.match(cleaned):
        raise ValueError("Email non valida")
    return cleaned


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    supply_point_id: uuid.UUID
    #: None only while the contract is a draft point of a pratica whose
    #: package has not been chosen yet.
    product_version_id: uuid.UUID | None = None
    #: The pratica it was filled in and paid with (Session 52).
    contract_request_id: uuid.UUID | None = None
    status: str
    notes: str | None = None
    iban: str | None = None
    email: str | None = None
    holder_first_name: str | None = None
    holder_last_name: str | None = None
    pec: str | None = None
    created_at: datetime
    activated_at: datetime | None = None
    expires_at: datetime | None = None
    # Denormalized display fields -- never the sole source of truth (the FKs
    # above are), but every list view needs a human-readable name, not a raw
    # UUID, so the service populates these instead of every caller doing its
    # own N+1 lookup. None only if the referenced row was hard-deleted.
    product_name: str | None = None
    supply_point_label: str | None = None
    pod_code: str | None = None
    pdr_code: str | None = None
    energy_type: str | None = None

    # --- Who built it ------------------------------------------------------
    #: CUSTOMER / PROMOTER / ADMIN. None on contracts created before this
    #: existed -- the creator is still recoverable from the status history.
    created_by_role: str | None = None
    #: Set only when a promoter completed the contract in place of the
    #: customer, which is exactly when the admin screen should say so.
    activated_by_promoter_id: uuid.UUID | None = None
    activated_by_promoter_name: str | None = None
    #: The promoter who originally brought this customer in -- a different
    #: person from the one above whenever somebody else assisted them.
    first_referrer_agent_id: uuid.UUID | None = None
    first_referrer_name: str | None = None

    # --- Frozen economics --------------------------------------------------
    customer_kind: str | None = None
    net_amount_cents: int | None = None
    #: Percentage points (22.0), not a fraction. 0.0 for a private customer.
    vat_rate: float | None = None
    vat_amount_cents: int | None = None
    gross_amount_cents: int | None = None

    # --- Payment -----------------------------------------------------------
    payment_plan: str | None = None
    #: Session 64: taken off a single payment (0 otherwise).
    payment_discount_cents: int = 0
    payment_method: str | None = None
    paid_at: datetime | None = None
    billing_stopped_at: datetime | None = None
    terms_accepted_at: datetime | None = None
    terms_version: str | None = None


class ContractCreate(BaseModel):
    customer_id: uuid.UUID
    supply_point_id: uuid.UUID
    product_version_id: uuid.UUID
    producer_agent_id: uuid.UUID
    notes: str | None = None
    iban: str | None = None
    email: str | None = None

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        return _validate_iban(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        return _validate_email(v)


class ContractSelfServiceCreate(BaseModel):
    """'Attiva Contratto' -- POST /contracts/mine. No producer_agent_id (unlike
    the staff-facing ContractCreate): the customer's own referring promoter is
    resolved server-side, see contracts/service.py::create_contract_self_service.
    email is required here (unlike ContractCreate's optional one) -- the
    activation wizard always collects it, pre-filled from the account's own
    email but freely editable, since a contract's contact email need not match
    the login email (see contracts/models.py::Contract.email)."""

    product_version_id: uuid.UUID
    supply_point: SupplyPointCreate
    email: str

    # Intestatario (migration 0040). Name required, PEC and IBAN optional:
    # not everyone has a PEC, and an IBAN can still be added later from
    # "I miei Contratti" -- the wizard asks for it up front, but a contract
    # must never be blocked on a bank detail someone does not have at hand.
    holder_first_name: str
    holder_last_name: str
    pec: str | None = None
    iban: str | None = None

    @field_validator("holder_first_name", "holder_last_name", mode="before")
    @classmethod
    def validate_name(cls, v: str | None) -> str:
        cleaned = (v or "").strip()
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
            raise ValueError("email is required")
        return validated


class ContractForCustomerCreate(BaseModel):
    """POST /contracts/for-customer -- the CRM-style counterpart to
    ContractSelfServiceCreate: a promoter activates a contract for one of
    THEIR OWN customers (see contracts/service.py::
    create_contract_for_recruited_customer). Like ContractSelfServiceCreate,
    no producer_agent_id -- the calling promoter's own agent is resolved
    server-side, never client-supplied."""

    customer_id: uuid.UUID
    product_version_id: uuid.UUID
    supply_point: SupplyPointCreate
    email: str

    # Intestatario (migration 0040). Name required, PEC and IBAN optional:
    # not everyone has a PEC, and an IBAN can still be added later from
    # "I miei Contratti" -- the wizard asks for it up front, but a contract
    # must never be blocked on a bank detail someone does not have at hand.
    holder_first_name: str
    holder_last_name: str
    pec: str | None = None
    iban: str | None = None

    @field_validator("holder_first_name", "holder_last_name", mode="before")
    @classmethod
    def validate_name(cls, v: str | None) -> str:
        cleaned = (v or "").strip()
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
            raise ValueError("email is required")
        return validated


class ContractIbanUpdate(BaseModel):
    iban: str

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: str | None) -> str | None:
        result = _validate_iban(v)
        if result is None:
            raise ValueError("iban is required")
        return result


class ContractTransitionRequest(BaseModel):
    to_status: str
    reason: str | None = None
    notes: str | None = None
    #: The checksum of the commission preview the administrator was shown
    #: and is accepting with this transition (GET /contracts/{id}/
    #: commission-preview). Required on the way to activation when no preview
    #: has been accepted yet -- see contracts/router.py::transition_contract.
    accept_commission_preview_checksum: str | None = None


class ContractStatusHistoryRead(BaseModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    actor_user_id: uuid.UUID
    actor_name: str
    reason: str | None
    notes: str | None
    created_at: datetime


class ContractPaymentOptionRead(BaseModel):
    """One way to pay THIS contract, already priced. Computed server-side
    from the amount frozen on the contract -- the browser never proposes an
    amount, it only picks a key."""

    key: str
    label: str
    description: str
    instalments: int
    instalment_cents: int
    total_cents: int
    #: Difference between this plan's total and the contract's own amount,
    #: caused by rounding an instalment to the cent. Shown to the customer
    #: rather than hidden; 0 for every price currently in the catalog.
    rounding_difference_cents: int
    #: Session 64: taken off a single payment only.
    discount_percentage: int = 0
    discount_cents: int = 0


class ContractPaymentOptionsRead(BaseModel):
    contract_id: uuid.UUID
    #: False when the contract is not at the payment step yet (or is already
    #: paid) -- the dashboard uses this to explain rather than to hide.
    payable: bool
    status: str
    #: True for a contract that IS at the payment step but carries no frozen
    #: amount, i.e. one created before the price snapshot existed. A distinct
    #: flag rather than lumping it in with "not payable": telling somebody
    #: their contract is not awaiting payment when it plainly is would send
    #: them looking for a problem that is on our side, not theirs.
    missing_amount: bool = False
    gross_amount_cents: int | None = None
    card_available: bool = False
    options: list[ContractPaymentOptionRead] = []
    #: Set once Stripe has confirmed the (first) payment -- possibly while
    #: the documents are still waiting for approval.
    paid_at: datetime | None = None
    payment_plan: str | None = None
    #: The product's automatic LialCash percentage, and what it comes to on
    #: the whole contract. On an instalment plan it is credited one
    #: instalment at a time, adding up to this same total.
    cashback_percentage: int = 0
    cashback_total_cents: int = 0


class ContractCheckoutRequest(BaseModel):
    #: FULL / INSTALMENTS_3 / MONTHLY_12 -- see contracts/payment_plans.py.
    payment_plan: str
