import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

# Fixed catalogue of roles known to the system (also seeded as rows for FK integrity).
SYSTEM_ROLES = [
    "SUPER_ADMIN",
    "ORGANIZATION_ADMIN",
    "ADMIN",
    "BACK_OFFICE_OPERATOR",
    "ACCOUNTING_OPERATOR",
    "SALES_MANAGER",
    "TEAM_LEADER",
    "PROMOTER",
    "CUSTOMER",
    "AUDITOR",
]

# Granular permission codes. Kept as a flat list (not an enum) so new permissions can
# be added by data migration without a code deploy.
PERMISSIONS = [
    "customers.read", "customers.create", "customers.update",
    "contracts.read", "contracts.create", "contracts.submit",
    "contracts.review", "contracts.approve", "contracts.activate",
    "network.read_branch", "network.manage", "network.recruit", "network.approve",
    "commissions.read_own", "commissions.read_branch", "commissions.simulate",
    "commissions.approve", "commission_adjustments.create",
    "payments.manage", "documents.download", "reports.export", "reports.read",
    "audit.read", "settings.manage",
    "products.read", "products.manage",
    "tickets.create", "tickets.respond", "tickets.delete",
    "documents.upload", "documents.review",
]

# Default role -> permission grants for the demo/seed environment. Real deployments
# should manage this via admin UI once settings.manage is exposed; this is the
# bootstrap default, not a hardcoded ceiling.
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": PERMISSIONS,
    "ORGANIZATION_ADMIN": PERMISSIONS,
    "ADMIN": [
        "customers.read", "customers.create", "customers.update",
        "contracts.read", "contracts.create", "contracts.submit",
        "contracts.review", "contracts.approve", "contracts.activate",
        "network.read_branch", "network.manage", "network.recruit",
        "commissions.read_branch", "commissions.simulate", "commissions.approve",
        "commission_adjustments.create", "payments.manage", "documents.download",
        "reports.export", "reports.read", "audit.read", "settings.manage",
        "products.read", "products.manage", "tickets.respond", "tickets.delete",
        "documents.upload", "documents.review",
    ],
    "BACK_OFFICE_OPERATOR": [
        "customers.read", "customers.create", "customers.update",
        "contracts.read", "contracts.create", "contracts.submit", "contracts.review",
        "documents.download", "products.read", "tickets.respond",
        "documents.upload", "documents.review",
    ],
    "ACCOUNTING_OPERATOR": [
        "contracts.read", "payments.manage", "commissions.read_branch",
        "commission_adjustments.create", "reports.export", "reports.read",
    ],
    "SALES_MANAGER": [
        "customers.read", "contracts.read", "contracts.approve",
        "network.read_branch", "network.manage", "network.recruit",
        "commissions.read_branch", "commissions.simulate", "reports.export", "reports.read",
        "products.read", "products.manage",
    ],
    "TEAM_LEADER": [
        "customers.read", "contracts.read", "contracts.create",
        "network.read_branch", "network.recruit",
        "commissions.read_own", "commissions.read_branch", "products.read",
    ],
    "PROMOTER": [
        "customers.read", "customers.create",
        "contracts.read", "contracts.create",
        "network.read_branch", "network.recruit", "commissions.read_own",
        # Read-only preview of their own potential earnings -- never writes to
        # the ledger (see commissions/simulations/simulate.py), so safe to grant.
        "commissions.simulate", "products.read", "tickets.create",
    ],
    "CUSTOMER": [
        "contracts.read", "documents.download", "documents.upload", "products.read", "tickets.create",
    ],
    "AUDITOR": ["audit.read", "reports.export", "reports.read"],
}


class Role(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_roles_org_code"),)

    # organization_id NULL = system-wide role definition available to every org
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))


class Permission(UUIDPKMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True
    )


class UserRole(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", "role_id", name="uq_user_roles"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"))
