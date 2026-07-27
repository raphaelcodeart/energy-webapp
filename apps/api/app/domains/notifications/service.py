"""In-app notifications: fan out to every user holding a given role (staff
events -- new contract, new ticket, promoter approval requests) or to one
specific user (a promoter earning a commission, an approval outcome). See
docs/business-rules.md#notifications for the full design."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.notifications.models import Notification
from app.domains.rbac.models import Role, UserRole

# Roles that should hear about org-wide operational events (new contract to
# review, new support ticket, a promoter waiting on approval). Deliberately
# NOT every admin-tier role -- ACCOUNTING_OPERATOR/AUDITOR don't action any
# of these, so they'd just be noise.
STAFF_NOTIFY_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN", "BACK_OFFICE_OPERATOR"}
# Only the "amministratore principale" tier can approve/reject a suggested
# promoter -- see network/router.py's network.approve gate.
APPROVAL_NOTIFY_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN"}


def _add(db: AsyncSession, *, organization_id, recipient_user_id, type_, entity_type, entity_id, title, body=None):
    db.add(
        Notification(
            organization_id=organization_id, recipient_user_id=recipient_user_id, type=type_,
            entity_type=entity_type, entity_id=str(entity_id), title=title, body=body,
        )
    )


async def notify_user(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, type_: str,
    entity_type: str, entity_id, title: str, body: str | None = None,
) -> None:
    """Does not commit -- caller commits as part of the same transaction as
    whatever event triggered this, same convention as audit_service.record()."""
    _add(db, organization_id=organization_id, recipient_user_id=user_id, type_=type_,
         entity_type=entity_type, entity_id=entity_id, title=title, body=body)


async def notify_roles(
    db: AsyncSession, *, organization_id: uuid.UUID, roles: set[str], type_: str,
    entity_type: str, entity_id, title: str, body: str | None = None, exclude_user_id: uuid.UUID | None = None,
) -> None:
    """One row per distinct user holding any of `roles` in this org -- read/unread
    state must be tracked per person, not per role, or one admin marking a
    notification read would silently clear it for every other admin too."""
    stmt = (
        select(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.organization_id == organization_id, Role.code.in_(roles))
        .distinct()
    )
    user_ids = {row[0] for row in (await db.execute(stmt)).all()}
    if exclude_user_id is not None:
        user_ids.discard(exclude_user_id)
    for user_id in user_ids:
        _add(db, organization_id=organization_id, recipient_user_id=user_id, type_=type_,
             entity_type=entity_type, entity_id=entity_id, title=title, body=body)


async def list_my_notifications(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, unread_only: bool = False, limit: int = 50
) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.organization_id == organization_id, Notification.recipient_user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return list((await db.execute(stmt)).scalars().all())


async def mark_read(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification | None:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.organization_id != organization_id or notification.recipient_user_id != user_id:
        return None
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification


async def mark_all_read(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> int:
    result = await db.execute(
        update(Notification)
        .where(
            Notification.organization_id == organization_id,
            Notification.recipient_user_id == user_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.commit()
    return result.rowcount or 0
