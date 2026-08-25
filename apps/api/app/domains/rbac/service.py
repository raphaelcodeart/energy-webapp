import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.rbac.models import Permission, Role, RolePermission, UserRole


async def get_permission_codes_for_user(
    db: AsyncSession, *, user_id: uuid.UUID, organization_id: uuid.UUID
) -> set[str]:
    """All permission codes granted to a user within one organization.

    Deliberately takes organization_id as a mandatory argument -- there is no
    "give me all this user's permissions across every org" call, because every
    caller must already know which tenant context it is authorizing for.
    """
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            UserRole.organization_id == organization_id,
        )
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}


async def get_roles_for_user(
    db: AsyncSession, *, user_id: uuid.UUID, organization_id: uuid.UUID
) -> list[str]:
    stmt = (
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, UserRole.organization_id == organization_id)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def assign_role(
    db: AsyncSession, *, user_id: uuid.UUID, organization_id: uuid.UUID, role_code: str
) -> None:
    """Grants role_code to user_id in organization_id, in addition to whatever
    roles they already hold (e.g. a CUSTOMER approved as a promoter keeps
    CUSTOMER and gains PROMOTER too). Idempotent -- a second call is a no-op,
    since UserRole's (user_id, organization_id, role_id) unique constraint
    means calling twice must never raise. Does not commit -- caller commits as
    part of its own transaction, same convention as audit_service.record()."""
    role = (
        await db.execute(
            select(Role).where(
                (Role.organization_id == organization_id) | (Role.organization_id.is_(None)),
                Role.code == role_code,
            )
        )
    ).scalars().first()
    if role is None:
        raise ValueError(f"Role {role_code} is not configured for this organization")

    existing = (
        await db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.organization_id == organization_id,
                UserRole.role_id == role.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(UserRole(user_id=user_id, organization_id=organization_id, role_id=role.id))
