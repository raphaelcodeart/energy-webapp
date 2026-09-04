import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class AgentProfile(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "agent_profiles"
    __table_args__ = (UniqueConstraint("organization_id", "promoter_code", name="uq_agent_promoter_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Denormalized "first last" kept for the many existing read paths
    # (contracts, notifications, branch views, reports, ...) that only ever
    # needed one string to show -- always derived from first_name/last_name
    # by the write paths (network/service.py create_agent/update_agent), never
    # edited independently.
    display_name: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    promoter_code: Mapped[str] = mapped_column(String(32))
    # ACTIVE / SUSPENDED / TERMINATED / PENDING_APPROVAL (added Session 17 --
    # both the admin's "+ Nuovo Promoter" and a promoter's own "recruit" now
    # only ever SUGGEST a new collaborator; a distinct network.approve-gated
    # action (network/router.py) is what actually activates them. A
    # PENDING_APPROVAL agent already exists in the tree (visible as a
    # suggestion) but contracts/service.py::create_contract() already
    # rejects any non-ACTIVE producer, so they simply can't be attributed a
    # sale until approved -- no extra guard needed there.
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    photo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    joined_at: Mapped[datetime] = mapped_column()
    current_rank_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ranks.id"), nullable=True
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # A promoter an admin has explicitly blacklisted (worse than a plain
    # deactivation, see network/router.py deactivate_agent) -- if they ever
    # re-apply via "lavora con noi", apply_as_promoter() sends them through the
    # manual PENDING_APPROVAL/approve flow instead of auto-activating.
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)


class NetworkNode(UUIDPKMixin, TimestampMixin, Base):
    """Current-state pointer: one row per agent, cheap to read/write. The
    authoritative history lives in NetworkEdge/NetworkClosure; this table exists so a
    simple 'who is X's direct parent right now' lookup doesn't need a closure scan."""

    __tablename__ = "network_nodes"
    __table_args__ = (
        # Only one ACTIVE (effective_to IS NULL) node per agent -- history rows for
        # the same agent are expected and must NOT collide with this constraint.
        Index(
            "uq_network_nodes_active_agent",
            "organization_id",
            "agent_id",
            unique=True,
            postgresql_where=text("effective_to IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), index=True
    )
    direct_parent_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    effective_from: Mapped[datetime] = mapped_column()
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)


class NetworkEdge(UUIDPKMixin, TimestampMixin, Base):
    """Append-only history of every parent/child relationship that ever held.
    Closed (effective_to set), never deleted or overwritten."""

    __tablename__ = "network_edges"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    parent_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), index=True
    )
    child_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), index=True
    )
    effective_from: Mapped[datetime] = mapped_column()
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)


class NetworkClosure(Base):
    """The transitive closure of NetworkEdge, maintained transactionally on every
    move. Includes the reflexive row (ancestor_agent_id == descendant_agent_id,
    depth == 0) for every agent. This is the table almost every network read query
    should hit; NetworkEdge/NetworkNode are for writes and point lookups."""

    __tablename__ = "network_closure"
    __table_args__ = (
        Index("ix_network_closure_org_ancestor", "organization_id", "ancestor_agent_id"),
        Index("ix_network_closure_org_descendant", "organization_id", "descendant_agent_id"),
        Index("ix_network_closure_org_ancestor_depth", "organization_id", "ancestor_agent_id", "depth"),
        Index("ix_network_closure_org_descendant_depth", "organization_id", "descendant_agent_id", "depth"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), primary_key=True
    )
    ancestor_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), primary_key=True
    )
    descendant_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), primary_key=True
    )
    effective_from: Mapped[datetime] = mapped_column(primary_key=True)
    depth: Mapped[int] = mapped_column(Integer)
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)


class NetworkAssignmentHistory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "network_assignment_history"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_profiles.id"))
    old_parent_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), nullable=True
    )
    new_parent_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), nullable=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(500))
    effective_at: Mapped[datetime] = mapped_column()


class NetworkSnapshot(UUIDPKMixin, TimestampMixin, Base):
    """An immutable copy of the closure rows relevant to one contract's ancestor
    chain, taken at contract activation. Contracts reference this id (never the
    live closure table) so later moves can't rewrite historical attribution."""

    __tablename__ = "network_snapshots"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(64))


class NetworkSnapshotNode(Base):
    __tablename__ = "network_snapshot_nodes"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_snapshots.id"), primary_key=True
    )
    ancestor_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_profiles.id"), primary_key=True
    )
    depth: Mapped[int] = mapped_column(Integer)
    rank_id_at_snapshot: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ranks.id"), nullable=True
    )
