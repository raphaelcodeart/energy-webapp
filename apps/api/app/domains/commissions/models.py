import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class Rank(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "ranks"
    __table_args__ = (UniqueConstraint("organization_id", "code", "rule_version", name="uq_ranks_org_code_version"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(128))
    level: Mapped[int] = mapped_column(Integer)
    personal_token_cents: Mapped[int] = mapped_column(BigInteger)
    energy_share_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    personal_volume_threshold_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    group_volume_threshold_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    evaluation_window_months: Mapped[int] = mapped_column(Integer, default=3)
    single_branch_cap_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=33)
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    rule_version: Mapped[str] = mapped_column(String(32))


class AgentRankHistory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "agent_rank_history"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_profiles.id"), index=True)
    rank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ranks.id"))
    effective_from: Mapped[datetime] = mapped_column()
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)
    calculation_source: Mapped[str] = mapped_column(String(32), default="MANUAL")
    rule_version_id: Mapped[str] = mapped_column(String(32))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class CommissionPlanVersion(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "commission_plan_versions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    version_label: Mapped[str] = mapped_column(String(32))
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class CommissionRuleVersion(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "commission_rule_versions"

    commission_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_plan_versions.id"), index=True
    )
    rule_type: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)


class CommissionCalculation(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "commission_calculations"
    __table_args__ = (
        # DB-level backstop for the (contract_id, trigger_event_id) idempotency
        # check in run_calculation_for_contract(): that check is SELECT-then-INSERT
        # at the application level, which has a race window if the same event is
        # ever dispatched concurrently (e.g. overlapping Celery beat runs). See
        # docs/paid-contract-commission-audit.md, Problem #3.
        UniqueConstraint(
            "contract_id", "trigger_event_id", name="uq_commission_calculations_contract_trigger"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id"), index=True)
    network_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_snapshots.id")
    )
    commission_plan_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_plan_versions.id"), nullable=True
    )
    trigger_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    input_snapshot: Mapped[dict] = mapped_column(JSONB)
    output_snapshot: Mapped[dict] = mapped_column(JSONB)
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED")


class CommissionCalculationStep(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "commission_calculation_steps"

    calculation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_calculations.id"), index=True
    )
    step_order: Mapped[int] = mapped_column(Integer)
    beneficiary_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_profiles.id"))
    rank_at_calculation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    base_amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    already_distributed_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    entrepreneurial_difference_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    personal_bonus_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    gross_amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    movement_type: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(String(1000))


class CommissionMovement(UUIDPKMixin, TimestampMixin, Base):
    """Append-only ledger. Consolidated (status != PENDING) rows must never be
    UPDATEd for amount/status=ACCRUED-or-later -- corrections are new rows linked via
    commission_adjustments/offsets/reversals. See docs/commission-engine-specification.md."""

    __tablename__ = "commission_movements"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_commission_movements_idempotency_key"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_profiles.id"), index=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id"), index=True)
    origin_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    calculation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_calculations.id")
    )
    movement_type: Mapped[str] = mapped_column(String(32))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    status: Mapped[str] = mapped_column(String(32), default="ACCRUED")
    effective_date: Mapped[date] = mapped_column()
    scheduled_date: Mapped[date | None] = mapped_column(nullable=True)
    paid_date: Mapped[date | None] = mapped_column(nullable=True)
    rule_version_id: Mapped[str] = mapped_column(String(32))
    network_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_snapshots.id")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))


class CommissionReversal(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "commission_reversals"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    original_movement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_movements.id")
    )
    new_movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("commission_movements.id"))
    reason: Mapped[str] = mapped_column(String(500))
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class CommissionAdjustment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "commission_adjustments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    original_movement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_movements.id")
    )
    new_movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("commission_movements.id"))
    reason: Mapped[str] = mapped_column(String(500))
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class CommissionOffset(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "commission_offsets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    debit_movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("commission_movements.id"))
    credit_movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("commission_movements.id"))
    reason: Mapped[str] = mapped_column(String(500))
