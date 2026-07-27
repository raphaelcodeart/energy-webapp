"""Covers the support ticket system: a customer or promoter opens a ticket
(with an initial message), staff replies, only the owner or staff can see/
reply to a given ticket -- never another customer's or promoter's ticket."""

import uuid

import pytest

from app.core.security import hash_password
from app.domains.support import service as support_service
from app.domains.support.schemas import TicketCreate, TicketMessageCreate, TicketStatusUpdate
from app.domains.users.models import User


async def _make_user(db, organization_id, *, email_prefix="user"):
    user = User(
        organization_id=organization_id, email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_actor_role_for_prefers_customer_then_promoter_then_admin():
    assert support_service.actor_role_for(["CUSTOMER", "ADMIN"]) == "CUSTOMER"
    assert support_service.actor_role_for(["PROMOTER"]) == "PROMOTER"
    assert support_service.actor_role_for(["ADMIN"]) == "ADMIN"
    assert support_service.actor_role_for([]) == "ADMIN"


@pytest.mark.asyncio
async def test_customer_can_open_ticket_and_read_it_back(db, organization_id):
    customer_user = await _make_user(db, organization_id, email_prefix="cust")

    ticket = await support_service.create_ticket(
        db, organization_id=organization_id, actor_user_id=customer_user.id, actor_role="CUSTOMER",
        payload=TicketCreate(subject="Bolletta non ricevuta", category="FATTURAZIONE", message="Non ho ricevuto la bolletta di giugno."),
    )
    assert ticket.status == "OPEN"

    detail = await support_service.get_ticket_detail(
        db, organization_id=organization_id, ticket_id=ticket.id,
        requester_user_id=customer_user.id, requester_is_staff=False,
    )
    assert detail is not None
    assert len(detail["messages"]) == 1
    assert detail["messages"][0]["body"] == "Non ho ricevuto la bolletta di giugno."
    assert detail["messages"][0]["author_role"] == "CUSTOMER"


@pytest.mark.asyncio
async def test_another_customer_cannot_read_someone_elses_ticket(db, organization_id):
    owner = await _make_user(db, organization_id, email_prefix="owner")
    intruder = await _make_user(db, organization_id, email_prefix="intruder")

    ticket = await support_service.create_ticket(
        db, organization_id=organization_id, actor_user_id=owner.id, actor_role="CUSTOMER",
        payload=TicketCreate(subject="Privato", message="Dettagli riservati."),
    )

    detail = await support_service.get_ticket_detail(
        db, organization_id=organization_id, ticket_id=ticket.id,
        requester_user_id=intruder.id, requester_is_staff=False,
    )
    assert detail is None


@pytest.mark.asyncio
async def test_staff_reply_moves_open_ticket_to_in_progress(db, organization_id):
    customer_user = await _make_user(db, organization_id, email_prefix="cust")
    staff_user = await _make_user(db, organization_id, email_prefix="staff")

    ticket = await support_service.create_ticket(
        db, organization_id=organization_id, actor_user_id=customer_user.id, actor_role="CUSTOMER",
        payload=TicketCreate(subject="Documento mancante", message="Serve la carta d'identità?"),
    )
    assert ticket.status == "OPEN"

    updated = await support_service.add_message(
        db, organization_id=organization_id, ticket_id=ticket.id, actor_user_id=staff_user.id,
        actor_role="ADMIN", requester_is_staff=True, payload=TicketMessageCreate(body="Sì, carica anche il documento d'identità."),
    )
    assert updated is not None
    assert updated.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_customer_cannot_reply_to_someone_elses_ticket(db, organization_id):
    owner = await _make_user(db, organization_id, email_prefix="owner")
    intruder = await _make_user(db, organization_id, email_prefix="intruder")

    ticket = await support_service.create_ticket(
        db, organization_id=organization_id, actor_user_id=owner.id, actor_role="CUSTOMER",
        payload=TicketCreate(subject="Privato", message="Dettagli riservati."),
    )

    result = await support_service.add_message(
        db, organization_id=organization_id, ticket_id=ticket.id, actor_user_id=intruder.id,
        actor_role="CUSTOMER", requester_is_staff=False, payload=TicketMessageCreate(body="Provo a intromettermi"),
    )
    assert result is None


@pytest.mark.asyncio
async def test_staff_can_close_ticket(db, organization_id):
    customer_user = await _make_user(db, organization_id, email_prefix="cust")
    staff_user = await _make_user(db, organization_id, email_prefix="staff")

    ticket = await support_service.create_ticket(
        db, organization_id=organization_id, actor_user_id=customer_user.id, actor_role="CUSTOMER",
        payload=TicketCreate(subject="Risolto", message="Grazie per l'aiuto."),
    )

    updated = await support_service.update_status(
        db, organization_id=organization_id, ticket_id=ticket.id, actor_user_id=staff_user.id,
        payload=TicketStatusUpdate(status="CLOSED"),
    )
    assert updated is not None
    assert updated.status == "CLOSED"


@pytest.mark.asyncio
async def test_promoter_and_customer_ticket_lists_are_separate(db, organization_id):
    customer_user = await _make_user(db, organization_id, email_prefix="cust")
    promoter_user = await _make_user(db, organization_id, email_prefix="promo")

    await support_service.create_ticket(
        db, organization_id=organization_id, actor_user_id=customer_user.id, actor_role="CUSTOMER",
        payload=TicketCreate(subject="Ticket cliente", message="Domanda cliente."),
    )
    await support_service.create_ticket(
        db, organization_id=organization_id, actor_user_id=promoter_user.id, actor_role="PROMOTER",
        payload=TicketCreate(subject="Ticket promoter", message="Domanda promoter."),
    )

    customer_tickets = await support_service.list_my_tickets(db, organization_id=organization_id, user_id=customer_user.id)
    promoter_tickets = await support_service.list_my_tickets(db, organization_id=organization_id, user_id=promoter_user.id)

    assert len(customer_tickets) == 1
    assert customer_tickets[0]["subject"] == "Ticket cliente"
    assert len(promoter_tickets) == 1
    assert promoter_tickets[0]["subject"] == "Ticket promoter"

    all_tickets = await support_service.list_tickets(db, organization_id=organization_id)
    assert len(all_tickets) == 2


@pytest.mark.asyncio
async def test_cannot_delete_a_ticket_that_is_not_resolved(db, organization_id):
    customer_user = await _make_user(db, organization_id, email_prefix="cust")
    staff_user = await _make_user(db, organization_id, email_prefix="staff")

    ticket = await support_service.create_ticket(
        db, organization_id=organization_id, actor_user_id=customer_user.id, actor_role="CUSTOMER",
        payload=TicketCreate(subject="Ancora aperto", message="Non ancora risolto."),
    )
    assert ticket.status == "OPEN"

    with pytest.raises(support_service.TicketDeletionError):
        await support_service.delete_ticket(
            db, organization_id=organization_id, ticket_id=ticket.id, actor_user_id=staff_user.id,
        )

    still_there = await support_service.get_ticket_detail(
        db, organization_id=organization_id, ticket_id=ticket.id,
        requester_user_id=customer_user.id, requester_is_staff=False,
    )
    assert still_there is not None


@pytest.mark.asyncio
async def test_deleting_a_resolved_ticket_removes_it_and_its_messages(db, organization_id):
    customer_user = await _make_user(db, organization_id, email_prefix="cust")
    staff_user = await _make_user(db, organization_id, email_prefix="staff")

    ticket = await support_service.create_ticket(
        db, organization_id=organization_id, actor_user_id=customer_user.id, actor_role="CUSTOMER",
        payload=TicketCreate(subject="Da eliminare", message="Problema risolto, grazie."),
    )
    await support_service.update_status(
        db, organization_id=organization_id, ticket_id=ticket.id, actor_user_id=staff_user.id,
        payload=TicketStatusUpdate(status="RESOLVED"),
    )

    result = await support_service.delete_ticket(
        db, organization_id=organization_id, ticket_id=ticket.id, actor_user_id=staff_user.id,
    )
    assert result is True

    gone = await support_service.get_ticket_detail(
        db, organization_id=organization_id, ticket_id=ticket.id,
        requester_user_id=staff_user.id, requester_is_staff=True,
    )
    assert gone is None


@pytest.mark.asyncio
async def test_deleting_a_ticket_from_another_org_returns_none(db, organization_id):
    customer_user = await _make_user(db, organization_id, email_prefix="cust")
    staff_user = await _make_user(db, organization_id, email_prefix="staff")

    ticket = await support_service.create_ticket(
        db, organization_id=organization_id, actor_user_id=customer_user.id, actor_role="CUSTOMER",
        payload=TicketCreate(subject="Altra org", message="Non dovrebbe essere raggiungibile."),
    )
    await support_service.update_status(
        db, organization_id=organization_id, ticket_id=ticket.id, actor_user_id=staff_user.id,
        payload=TicketStatusUpdate(status="RESOLVED"),
    )

    result = await support_service.delete_ticket(
        db, organization_id=uuid.uuid4(), ticket_id=ticket.id, actor_user_id=staff_user.id,
    )
    assert result is None
