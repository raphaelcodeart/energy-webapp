import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user
from app.domains.notifications import service as notifications_service
from app.domains.notifications.schemas import NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/mine", response_model=list[NotificationRead])
async def get_my_notifications(
    unread_only: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationRead]:
    """Self-scoped by construction (recipient_user_id) -- no dedicated
    permission needed, same as /commissions/mine and /network/mine."""
    rows = await notifications_service.list_my_notifications(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, unread_only=unread_only
    )
    return [NotificationRead.model_validate(n) for n in rows]


@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationRead:
    notification = await notifications_service.mark_read(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, notification_id=notification_id
    )
    if notification is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return NotificationRead.model_validate(notification)


@router.post("/mark-all-read")
async def mark_all_notifications_read(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    count = await notifications_service.mark_all_read(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    return {"marked_read": count}
