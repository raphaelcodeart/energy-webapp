import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.support import service as support_service
from app.domains.support.schemas import (
    TicketCreate,
    TicketDetailRead,
    TicketMessageCreate,
    TicketMessageRead,
    TicketRead,
    TicketStatusUpdate,
)

router = APIRouter(prefix="/support/tickets", tags=["support"])


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    current_user: CurrentUser = Depends(require_permission("tickets.create")),
    db: AsyncSession = Depends(get_db),
) -> TicketRead:
    actor_role = support_service.actor_role_for(current_user.roles)
    ticket = await support_service.create_ticket(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        actor_role=actor_role, payload=payload,
    )
    rows = await support_service.list_my_tickets(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    row = next(r for r in rows if r["id"] == ticket.id)
    return TicketRead(**row)


@router.get("/mine", response_model=list[TicketRead])
async def list_my_tickets(
    current_user: CurrentUser = Depends(require_permission("tickets.create")),
    db: AsyncSession = Depends(get_db),
) -> list[TicketRead]:
    rows = await support_service.list_my_tickets(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    return [TicketRead(**row) for row in rows]


@router.get("", response_model=list[TicketRead])
async def list_all_tickets(
    current_user: CurrentUser = Depends(require_permission("tickets.respond")),
    db: AsyncSession = Depends(get_db),
) -> list[TicketRead]:
    rows = await support_service.list_tickets(db, organization_id=current_user.organization_id)
    return [TicketRead(**row) for row in rows]


@router.get("/{ticket_id}", response_model=TicketDetailRead)
async def get_ticket(
    ticket_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("tickets.create")),
    db: AsyncSession = Depends(get_db),
) -> TicketDetailRead:
    row = await support_service.get_ticket_detail(
        db, organization_id=current_user.organization_id, ticket_id=ticket_id,
        requester_user_id=current_user.user_id, requester_is_staff=False,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return TicketDetailRead(**row)


@router.get("/{ticket_id}/staff", response_model=TicketDetailRead)
async def get_ticket_as_staff(
    ticket_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("tickets.respond")),
    db: AsyncSession = Depends(get_db),
) -> TicketDetailRead:
    row = await support_service.get_ticket_detail(
        db, organization_id=current_user.organization_id, ticket_id=ticket_id,
        requester_user_id=current_user.user_id, requester_is_staff=True,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return TicketDetailRead(**row)


@router.post("/{ticket_id}/messages", response_model=TicketRead)
async def add_message(
    ticket_id: uuid.UUID,
    payload: TicketMessageCreate,
    current_user: CurrentUser = Depends(require_permission("tickets.create")),
    db: AsyncSession = Depends(get_db),
) -> TicketRead:
    actor_role = support_service.actor_role_for(current_user.roles)
    ticket = await support_service.add_message(
        db, organization_id=current_user.organization_id, ticket_id=ticket_id,
        actor_user_id=current_user.user_id, actor_role=actor_role, requester_is_staff=False, payload=payload,
    )
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    rows = await support_service.list_my_tickets(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    row = next(r for r in rows if r["id"] == ticket.id)
    return TicketRead(**row)


@router.post("/{ticket_id}/staff-messages", response_model=TicketRead)
async def add_staff_message(
    ticket_id: uuid.UUID,
    payload: TicketMessageCreate,
    current_user: CurrentUser = Depends(require_permission("tickets.respond")),
    db: AsyncSession = Depends(get_db),
) -> TicketRead:
    ticket = await support_service.add_message(
        db, organization_id=current_user.organization_id, ticket_id=ticket_id,
        actor_user_id=current_user.user_id, actor_role=support_service.ADMIN_REPLY_ROLE,
        requester_is_staff=True, payload=payload,
    )
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    rows = await support_service.list_tickets(db, organization_id=current_user.organization_id)
    row = next(r for r in rows if r["id"] == ticket.id)
    return TicketRead(**row)


@router.patch("/{ticket_id}/status", response_model=TicketRead)
async def update_ticket_status(
    ticket_id: uuid.UUID,
    payload: TicketStatusUpdate,
    current_user: CurrentUser = Depends(require_permission("tickets.respond")),
    db: AsyncSession = Depends(get_db),
) -> TicketRead:
    ticket = await support_service.update_status(
        db, organization_id=current_user.organization_id, ticket_id=ticket_id,
        actor_user_id=current_user.user_id, payload=payload,
    )
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    rows = await support_service.list_tickets(db, organization_id=current_user.organization_id)
    row = next(r for r in rows if r["id"] == ticket.id)
    return TicketRead(**row)
