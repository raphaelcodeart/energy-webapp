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
