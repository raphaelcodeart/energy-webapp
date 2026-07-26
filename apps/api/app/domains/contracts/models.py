import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
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
    # Set (and reset, on every renewal) by transition_contract() whenever the
    # contract enters ACTIVE or RENEWED. expires_at is computed from the
    # product version's contract_duration_months at that same moment -- never
    # recomputed retroactively if the product version's duration changes later,
    # matching the "frozen at the moment it happens" pattern used everywhere
    # else in this codebase (network snapshots, commission calculations).
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)


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
