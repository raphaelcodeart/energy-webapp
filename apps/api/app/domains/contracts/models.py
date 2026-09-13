import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class Contract(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "contracts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    supply_point_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("supply_points.id"))
    product_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_versions.id")
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
    #: FULL / MONTHLY_12 / KLARNA_3 -- see contracts/payment_plans.py.
    payment_plan: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: CARD / BANK_TRANSFER.
    payment_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
