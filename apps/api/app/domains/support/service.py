import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.support.models import Ticket, TicketMessage
from app.domains.support.schemas import TicketCreate, TicketMessageCreate, TicketStatusUpdate
from app.domains.users.models import User

ADMIN_REPLY_ROLE = "ADMIN"


class TicketDeletionError(Exception):
    """Raised when a ticket can't be deleted yet -- only status RESOLVED is
    eligible (see update_status: CLOSED is a distinct, later terminal state,
    intentionally not included here)."""


def actor_role_for(roles: list[str]) -> str:
    """Which "hat" is this user opening/replying to a ticket as? A user could
    technically hold multiple roles; a customer or promoter opening a ticket is
    always acting as that role, never as staff -- staff replying is always
    ADMIN regardless of which specific admin-tier role they hold (see
    rbac/models.py SYSTEM_ROLES for the full admin-tier list)."""
    if "CUSTOMER" in roles:
        return "CUSTOMER"
    if "PROMOTER" in roles:
        return "PROMOTER"
    return ADMIN_REPLY_ROLE


async def _display_names_for_users(db: AsyncSession, *, organization_id: uuid.UUID, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Best-effort human-readable name for a ticket's opener/repliers -- tries
    Customer, then AgentProfile (promoter), falls back to the user's email
    (admin staff have neither a Customer nor AgentProfile row)."""
    if not user_ids:
        return {}

    names: dict[uuid.UUID, str] = {}

    customers = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id.in_(user_ids))
        )
    ).scalars().all()
    if customers:
        customer_ids = [c.id for c in customers]
        profiles = {
            p.customer_id: p
            for p in (await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(customer_ids)))).scalars()
        }
        companies = {
            c.customer_id: c
            for c in (await db.execute(select(Company).where(Company.customer_id.in_(customer_ids)))).scalars()
        }
        for c in customers:
            if c.user_id is not None:
                names[c.user_id] = display_name_for(c.kind, profiles.get(c.id), companies.get(c.id))

    remaining = user_ids - names.keys()
    if remaining:
        agents = (
            await db.execute(
                select(AgentProfile).where(
                    AgentProfile.organization_id == organization_id, AgentProfile.user_id.in_(remaining)
                )
            )
        ).scalars().all()
        for a in agents:
            if a.user_id is not None:
                names[a.user_id] = a.display_name

    remaining = user_ids - names.keys()
    if remaining:
        users = (await db.execute(select(User).where(User.id.in_(remaining)))).scalars().all()
        for u in users:
            names[u.id] = u.email

    return names


async def _enrich_tickets(db: AsyncSession, *, organization_id: uuid.UUID, tickets: list[Ticket]) -> list[dict]:
    if not tickets:
        return []
    ticket_ids = [t.id for t in tickets]
    names = await _display_names_for_users(
        db, organization_id=organization_id, user_ids={t.opened_by_user_id for t in tickets}
    )
    stats_stmt = (
        select(TicketMessage.ticket_id, func.count(), func.max(TicketMessage.created_at))
        .where(TicketMessage.ticket_id.in_(ticket_ids))
        .group_by(TicketMessage.ticket_id)
    )
    stats = {row[0]: (row[1], row[2]) for row in (await db.execute(stats_stmt)).all()}

    result = []
    for t in tickets:
        count, last_at = stats.get(t.id, (0, None))
        result.append(
            {
                "id": t.id,
                "organization_id": t.organization_id,
                "opened_by_user_id": t.opened_by_user_id,
                "opened_by_role": t.opened_by_role,
                "opened_by_name": names.get(t.opened_by_user_id),
                "subject": t.subject,
                "category": t.category,
                "status": t.status,
                "contract_id": t.contract_id,
                "created_at": t.created_at,
                "message_count": count,
                "last_message_at": last_at,
            }
        )
    # Most recently active first (last reply, or creation time if nobody has
    # replied yet) -- what the admin/customer/promoter actually cares about,
    # not insertion order.
    result.sort(key=lambda r: r["last_message_at"] or r["created_at"], reverse=True)
    return result


async def create_ticket(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
    payload: TicketCreate,
) -> Ticket:
    ticket = Ticket(
        organization_id=organization_id,
        opened_by_user_id=actor_user_id,
        opened_by_role=actor_role,
        subject=payload.subject,
        category=payload.category,
        status="OPEN",
        contract_id=payload.contract_id,
    )
    db.add(ticket)
    await db.flush()

    db.add(
        TicketMessage(
            ticket_id=ticket.id, author_user_id=actor_user_id, author_role=actor_role, body=payload.message
        )
    )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="ticket.created", entity_type="ticket", entity_id=str(ticket.id),
        new_value={"subject": payload.subject, "category": payload.category},
    )
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="TICKET_CREATED", entity_type="ticket", entity_id=ticket.id,
        title=f"Nuovo ticket: {payload.subject}", body=payload.message[:200],
        exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def list_tickets(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    """Org-wide view -- admin only (gated by the tickets.respond permission at
    the router level, not here)."""
    stmt = select(Ticket).where(Ticket.organization_id == organization_id)
    tickets = (await db.execute(stmt)).scalars().all()
    return await _enrich_tickets(db, organization_id=organization_id, tickets=list(tickets))


async def list_my_tickets(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
    stmt = select(Ticket).where(
        Ticket.organization_id == organization_id, Ticket.opened_by_user_id == user_id
    )
    tickets = (await db.execute(stmt)).scalars().all()
    return await _enrich_tickets(db, organization_id=organization_id, tickets=list(tickets))


async def get_ticket_detail(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ticket_id: uuid.UUID,
    requester_user_id: uuid.UUID | None,
    requester_is_staff: bool,
) -> dict | None:
    """requester_user_id + requester_is_staff implement ownership scoping here
    (ABAC), the same pattern network/service.py uses for branch access: staff
    (tickets.respond) can open any ticket in the org, everyone else only their
    own."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.organization_id != organization_id:
        return None
    if not requester_is_staff and ticket.opened_by_user_id != requester_user_id:
        return None

    rows = await _enrich_tickets(db, organization_id=organization_id, tickets=[ticket])
    detail = rows[0]

    messages = (
        await db.execute(
            select(TicketMessage).where(TicketMessage.ticket_id == ticket_id).order_by(TicketMessage.created_at)
        )
    ).scalars().all()
    names = await _display_names_for_users(
        db, organization_id=organization_id, user_ids={m.author_user_id for m in messages}
    )
    detail["messages"] = [
        {
            "id": m.id,
            "ticket_id": m.ticket_id,
            "author_user_id": m.author_user_id,
            "author_role": m.author_role,
            "author_name": names.get(m.author_user_id),
            "body": m.body,
            "created_at": m.created_at,
        }
        for m in messages
    ]
    return detail


async def add_message(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ticket_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
    requester_is_staff: bool,
    payload: TicketMessageCreate,
) -> Ticket | None:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.organization_id != organization_id:
        return None
    if not requester_is_staff and ticket.opened_by_user_id != actor_user_id:
        return None

    db.add(
        TicketMessage(ticket_id=ticket_id, author_user_id=actor_user_id, author_role=actor_role, body=payload.body)
    )
    # A staff reply on an OPEN ticket implicitly moves it to IN_PROGRESS -- the
    # customer/promoter reading the ticket list needs to see "someone is
    # looking at this" without the admin remembering a separate status click.
    if requester_is_staff and ticket.status == "OPEN":
        ticket.status = "IN_PROGRESS"

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="ticket.message_added", entity_type="ticket", entity_id=str(ticket_id),
        new_value={"author_role": actor_role},
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def delete_ticket(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ticket_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> bool | None:
    """Staff-only (tickets.delete, enforced at the router). Returns None if the
    ticket doesn't exist in this org (-> router 404), raises
    TicketDeletionError if it's not yet RESOLVED (-> router 400). No FK
    ondelete is defined on ticket_messages.ticket_id, so its rows must be
    removed explicitly in the same transaction before the ticket row itself."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.organization_id != organization_id:
        return None
    if ticket.status != "RESOLVED":
        raise TicketDeletionError("Only a resolved ticket can be deleted.")

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="ticket.deleted", entity_type="ticket", entity_id=str(ticket_id),
        previous_value={"subject": ticket.subject, "category": ticket.category, "status": ticket.status},
    )
    await db.execute(delete(TicketMessage).where(TicketMessage.ticket_id == ticket_id))
    await db.delete(ticket)
    await db.commit()
    return True


async def update_status(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ticket_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    payload: TicketStatusUpdate,
) -> Ticket | None:
    """Staff-only (tickets.respond, enforced at the router) -- a customer or
    promoter can describe their problem as solved by saying so in a message,
    but only staff closes the loop formally."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.organization_id != organization_id:
        return None

    previous_status = ticket.status
    ticket.status = payload.status

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="ticket.status_changed", entity_type="ticket", entity_id=str(ticket_id),
        previous_value={"status": previous_status}, new_value={"status": payload.status},
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket
