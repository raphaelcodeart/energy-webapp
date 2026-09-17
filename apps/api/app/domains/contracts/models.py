import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

#: DRAFT -- being filled in (points, documents, packages), nothing sent yet.
#: SUBMITTED -- sent: its contracts are in the ordinary review flow.
#: CANCELLED -- abandoned by the customer while still a draft.
CONTRACT_REQUEST_STATUSES = frozenset({"DRAFT", "SUBMITTED", "CANCELLED"})


class ContractRequest(UUIDPKMixin, TimestampMixin, Base):
    """La pratica di attivazione (Session 52): one customer, N supply points,
    N contracts, filled in and paid together.

    Deliberately thin. Each contract keeps everything it owned before --
    package, frozen price, status, documents of its own, approval,
    instalments, commissions -- and the pratica owns only what is genuinely
    common: who the holder is, the documents that are the same for every
    point, and the single checkout that pays them all. A contract rejected,
    suspended or cancelled inside a pratica affects no other contract in it.

    The holder fields are copied onto every contract at creation and on
    every edit while the pratica is a draft: the many existing readers of
    `contracts.email`/`iban`/... keep working untouched, and a contract never
    has to look upward to know who it belongs to.
    """

    __tablename__ = "contract_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    holder_first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    holder_last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    pec: Mapped[str | None] = mapped_column(String(320), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    #: The supply address every point of the pratica starts from, asked once
    #: with the holder data (Session 53). A point moved elsewhere keeps its
    #: own address on its supply point.
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    province: Mapped[str | None] = mapped_column(String(8), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    #: CUSTOMER / PROMOTER / ADMIN -- same meaning as on contracts.
    created_by_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Set when a promoter is filling the pratica in for their customer --
    #: also what lets that promoter keep working on it.
    activated_by_promoter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # --- Session 65: paying the pratica by bank transfer -------------------------
    #: The customer chose "bonifico" (single payment, with the one-go discount):
    #: the amount frozen at that moment, confirmed later by an administrator.
    bank_transfer_requested_at: Mapped[datetime | None] = mapped_column(nullable=True)
    bank_transfer_total_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bank_transfer_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    bank_transfer_confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    payment_proof_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_proof_original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_proof_uploaded_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ContractRequestCheckout(UUIDPKMixin, TimestampMixin, Base):
    """One Stripe Checkout Session opened to pay a pratica.

    `lines` freezes exactly what the session charges: one entry per contract,
    `{"contract_id", "gross_cents", "instalment_cents"}`. The webhook pays
    those contracts and no others, whatever has changed in the pratica since
    -- a contract rejected while the customer sat on the Stripe page is still
    recorded as paid (the money moved) and staff are told to refund it.

    One row per session rather than one "current session" column on the
    pratica: a customer who opens the payment in two tabs and completes the
    older one has still paid, and that payment must be found, not dropped
    because a newer session overwrote the reference to it.
    """

    __tablename__ = "contract_request_checkouts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    contract_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contract_requests.id"), index=True
    )
    stripe_checkout_session_id: Mapped[str] = mapped_column(String(255), unique=True)
    payment_plan: Mapped[str] = mapped_column(String(16))
    lines: Mapped[list] = mapped_column(JSONB, default=list)
    #: Sum over the lines of what the plan collects in total, and per month.
    total_cents: Mapped[int] = mapped_column(BigInteger)
    instalment_cents: Mapped[int] = mapped_column(BigInteger)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: What the webhook did with it, in words -- for whoever investigates.
    outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Contract(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "contracts"
    __table_args__ = (
        # The package is chosen per point after the documents (Session 52), so
        # a contract may exist without one -- but only while it is a draft.
        CheckConstraint(
            "product_version_id IS NOT NULL OR status IN ('DRAFT', 'CANCELLED')", name="product_required"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    #: The pratica this contract was filled in and paid with. Every contract
    #: has one: a contract created on its own gets a pratica of one.
    contract_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contract_requests.id"), index=True
    )
    supply_point_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("supply_points.id"))
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_versions.id"), nullable=True
    )
    contract_attribution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contract_attributions.id"), nullable=True
    )
    network_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_snapshots.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    # Free-text context set at creation by whoever originated the deal (the
    # inviting promoter or the admin creating it directly) -- e.g. "cliente
    # arrivato dalla promozione Luce Green, preferisce essere ricontattato la
    # sera". Distinct from ContractStatusHistory.notes, which is per-transition.
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Bank account for this specific subscription's direct-debit payments --
    # collected when the contract is requested (a customer may have different
    # payment details per contract), never inferred from the customer's other
    # contracts. Nullable: an admin creating a contract on the customer's
    # behalf may not have it on hand yet.
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    # Contact email for this specific contract/pratica -- deliberately independent
    # of the customer's account login email (a customer may want a contract
    # followed at a different address, e.g. a family member's or the
    # supply point's own). Nullable for compatibility with contracts created
    # before this field existed.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # The contract holder as typed into the activation wizard (pre-filled
    # from the account, freely editable) plus an optional PEC. Per contract
    # for the same reason as email/iban above. Null on contracts created
    # before migration 0040 and on staff-created ones.
    holder_first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    holder_last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pec: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Set (and reset, on every renewal) by transition_contract() whenever the
    # contract enters ACTIVE or RENEWED. expires_at is computed from the
    # product version's contract_duration_months at that same moment -- never
    # recomputed retroactively if the product version's duration changes later,
    # matching the "frozen at the moment it happens" pattern used everywhere
    # else in this codebase (network snapshots, commission calculations).
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)

    # --- Who built this contract ------------------------------------------
    #
    # Until now this was only recoverable indirectly, from the actor on the
    # first ContractStatusHistory row. That works for an audit query but not
    # for the thing the business actually needs to see at a glance on the
    # admin screen: did the customer sign this up themselves, or did a
    # promoter sit with them and fill it in on their behalf?
    #
    # ContractStatusHistory and audit_log remain the full technical trail
    # (who created, who changed status, who uploaded which document, when) --
    # these three columns are the denormalized answer to the one question
    # that gets asked constantly, not a replacement for either.
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    #: CUSTOMER / PROMOTER / ADMIN, snapshotted from the creator's roles at
    #: creation time (support/service.py::actor_role_for) -- a person's roles
    #: can change later, what they were acting as here cannot.
    created_by_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Set ONLY when a promoter completed the contract in place of the
    #: customer (the CRM path). Null when the customer did it themselves or
    #: when staff created it -- so "Contratto attivato dal promoter X" is
    #: shown exactly when it is true, never as a side effect of who happens
    #: to earn the commission.
    activated_by_promoter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), nullable=True
    )
    #: The promoter who ORIGINALLY brought this customer in, resolved from
    #: CustomerAttribution at creation and then frozen. Deliberately distinct
    #: from ContractAttribution.producer_agent_id (who gets the recursive
    #: commission): a different promoter assisting the customer never takes
    #: over the first-referrer bonus. See commissions/services/run_calculation.py.
    first_referrer_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), nullable=True
    )

    # --- Economics, frozen at creation ------------------------------------
    #
    # Snapshot, not a live join to the product version: an admin editing a
    # product's price or VAT rate tomorrow must never restate what somebody
    # already agreed to pay. Computed exclusively server-side by
    # catalog/pricing.py::compute_contract_price -- no amount on this row
    # ever originates from a browser.
    #: The customer's kind (PRIVATE/SOLE_PROPRIETOR/COMPANY/CONDOMINIUM) as
    #: it was when the contract was created -- it is what decided whether VAT
    #: applies at all, so it has to be frozen alongside the amounts.
    customer_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    net_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: Percentage points (e.g. 22.00), not a fraction. 0.00 for a private
    #: customer, whatever the product's rate happens to be.
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    vat_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gross_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # --- Payment -----------------------------------------------------------
    #
    # A contract has never been paid through this app before (every contract
    # in production sits at DRAFT/DOCUMENTS_PENDING/UNDER_REVIEW), so none of
    # this restates existing behaviour -- it is the payment step that did not
    # exist. Stripe is the only source of truth that any of it was paid: the
    # success URL is never treated as proof, only the verified webhook is.
    #: How the customer chose to pay:
    #:   FULL       -- one-off payment of the whole amount
    #:   MONTHLY_12 -- twelve monthly instalments (a real Stripe
    #:                 subscription, never twelve hand-made payments)
    #:   FINANCING  -- "Finanziaria Stripe": the amount is financed and the
    #:                 customer repays the financing provider, not us.
    #: Nothing writes this column yet -- the contract payment step is not
    #: built (see docs/server-migration-guide.md §9). The values are fixed
    #: here so the column has one agreed vocabulary before anything starts
    #: relying on it.
    payment_plan: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Session 64: the discount taken off a single payment, frozen when the
    #: customer chose it (0 for instalments, bank transfers and older contracts).
    payment_discount_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: CARD / BANK_TRANSFER.
    payment_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Shared by every contract of a pratica paid in instalments: one
    #: subscription, one line (`stripe_subscription_item_id`) per contract.
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    #: An administrator removed this contract's line from the subscription:
    #: the card is no longer charged for it, the other contracts carry on.
    billing_stopped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: Guard making the LialCash credit for this contract exactly-once even
    #: if the webhook is replayed, on top of the wallet ledger's own unique
    #: idempotency key -- same belt-and-braces pattern as orders.
    cashback_credited_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # --- Proof of what was accepted ---------------------------------------
    #
    # An admin replacing a product's contract PDF later must not change what
    # this customer accepted, so the version accepted is stored here rather
    # than read back through the product.
    terms_accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    terms_accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    terms_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    terms_accepted_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    terms_accepted_user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ContractStatusHistory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "contract_status_history"

    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64))


class ContractEvent(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "contract_events"

    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class ContractAttribution(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "contract_attributions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    producer_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id")
    )
    attributed_promoter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id")
    )


class ContractCommissionPlan(UUIDPKMixin, TimestampMixin, Base):
    """The commission preview an administrator accepted before this contract
    could activate -- kept verbatim, as the log they can reopen later.

    Business rule (Session 50): approving a contract is the act that sets
    commissions going, so the administrator must see who is paid what, and
    how it is spread over the customer's instalments, before it happens.
    `preview` is exactly what was on their screen; the ledger rows that
    actually get written later (commission_movements) may differ if the
    network changed between approval and payment, and the log shows both
    side by side rather than pretending they are the same thing.
    """

    __tablename__ = "contract_commission_plans"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id"), unique=True
    )
    accepted_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    accepted_at: Mapped[datetime] = mapped_column()
    #: The payment plan known at acceptance -- null when the customer had not
    #: paid yet, in which case the preview listed every possible split.
    payment_plan: Mapped[str | None] = mapped_column(String(16), nullable=True)
    total_commission_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    preview: Mapped[dict] = mapped_column(JSONB, default=dict)
    checksum: Mapped[str] = mapped_column(String(64))


class ContractInstalment(UUIDPKMixin, TimestampMixin, Base):
    """One payment the customer owes on a contract: 1 row for a single
    payment, 3 or 12 for an instalment plan.

    It is what releases commissions a slice at a time: each row, once PAID
    on an ACTIVE contract, emits exactly one ContractInstalmentPaid outbox
    event (commission_event_id, set once) and the engine pays 1/N of every
    beneficiary's commission for it. The UNIQUE (contract_id, number) and
    the UNIQUE (contract_id, stripe_invoice_id) are what make "Stripe confirmed it" and
    "an administrator confirmed it" unable to pay the same month twice.
    """

    __tablename__ = "contract_instalments"
    __table_args__ = (
        UniqueConstraint("contract_id", "number", name="uq_contract_instalments_contract_number"),
        # Per contract, not globally: one monthly invoice of a pratica pays
        # every contract in it (Session 52).
        UniqueConstraint("contract_id", "stripe_invoice_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    instalments_total: Mapped[int] = mapped_column(Integer)
    #: Expected date, from the first payment plus (number - 1) months.
    due_date: Mapped[date] = mapped_column(Date)
    #: What the customer pays for this instalment.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    #: SCHEDULED / PAID / FAILED
    status: Mapped[str] = mapped_column(String(16), default="SCHEDULED")
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    #: STRIPE_CHECKOUT / STRIPE_INVOICE / ADMIN
    payment_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commission_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    commission_released_at: Mapped[datetime | None] = mapped_column(nullable=True)
    commission_calculation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_calculations.id"), nullable=True
    )
