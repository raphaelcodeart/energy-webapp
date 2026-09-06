import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_users_org_email"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # ACTIVE / FROZEN (added Session 28 -- an admin-frozen account: login is
    # refused and every existing session revoked immediately, but the row and
    # all its data/history stay exactly as they were, see
    # users/service.py::freeze_user/unfreeze_user and auth/service.py's
    # authenticate() status check).
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    email_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    # Set once, at self-registration, when the (now-mandatory) privacy
    # checkbox is accepted -- see auth/service.py::register_with_referral.
    # NULL for every account that predates this field (accounts created by
    # an admin directly, or self-registered before Session 27) -- there is
    # no retroactive consent to backfill for those, so this column simply
    # stays NULL for them rather than being defaulted to "accepted".
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Profile-completion gate (added Session 27): every account, existing or
    # new, must have all of these filled before using the dashboard -- see
    # users/service.py::is_profile_complete(). Deliberately on User, not
    # Customer/AgentProfile, since a promoter has no Customer row and this
    # is inherently user-level identity data, independent of role.
    fiscal_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    residence_street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    residence_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    residence_province: Mapped[str | None] = mapped_column(String(2), nullable=True)
    residence_postal_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    residence_country: Mapped[str] = mapped_column(String(2), default="IT")
