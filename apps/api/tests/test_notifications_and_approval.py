"""New collaborator suggest-then-approve workflow (admin/promoter creation ->
PENDING_APPROVAL -> network.approve-gated approve/reject) and the in-app
notification fan-out that goes with it (new contract, new ticket, promoter
approval requested, commission earned)."""

import uuid

import pytest

from app.core.security import hash_password
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.network import service as network_service
from app.domains.notifications import service as notifications_service
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User


async def _get_or_create_role(db, organization_id, *, role_code: str) -> Role:
    from sqlalchemy import select

    existing = (
        await db.execute(select(Role).where(Role.organization_id == organization_id, Role.code == role_code))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    role = Role(organization_id=organization_id, code=role_code, name=role_code.title())
    db.add(role)
    await db.flush()
    return role


async def _make_user_with_role(db, organization_id, *, role_code: str, email: str | None = None):
    user = User(
        organization_id=organization_id, email=email or f"{role_code.lower()}-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.flush()
    role = await _get_or_create_role(db, organization_id, role_code=role_code)
    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_new_agent_is_pending_approval_not_active(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Suggested", last_name="Agent",
        promoter_code=f"SUG-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
        actor_user_id=admin.id, status="PENDING_APPROVAL",
    )
    assert agent.status == "PENDING_APPROVAL"
    assert agent.approved_by_user_id is None


@pytest.mark.asyncio
async def test_approve_agent_activates_it_and_is_idempotent_against_double_approval(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    super_admin = await _make_user_with_role(db, organization_id, role_code="SUPER_ADMIN")
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Pending", last_name="Agent",
        promoter_code=f"PEND-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
        actor_user_id=admin.id, status="PENDING_APPROVAL",
    )

    approved = await network_service.approve_agent(
        db, organization_id=organization_id, agent_id=agent.id, actor_user_id=super_admin.id
    )
    assert approved.status == "ACTIVE"
    assert approved.approved_by_user_id == super_admin.id
    assert approved.approved_at is not None

    with pytest.raises(network_service.AgentApprovalError):
        await network_service.approve_agent(
            db, organization_id=organization_id, agent_id=agent.id, actor_user_id=super_admin.id
        )


@pytest.mark.asyncio
async def test_reject_agent_terminates_with_reason(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    super_admin = await _make_user_with_role(db, organization_id, role_code="SUPER_ADMIN")
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Rejected", last_name="Agent",
        promoter_code=f"REJ-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
        actor_user_id=admin.id, status="PENDING_APPROVAL",
    )

    rejected = await network_service.reject_agent(
        db, organization_id=organization_id, agent_id=agent.id, actor_user_id=super_admin.id,
        reason="Codice promoter duplicato per errore",
    )
    assert rejected.status == "TERMINATED"
    assert rejected.rejection_reason == "Codice promoter duplicato per errore"


@pytest.mark.asyncio
async def test_notify_roles_fans_out_one_row_per_user_and_excludes_actor(db, organization_id):
    admin1 = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    admin2 = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    promoter = await _make_user_with_role(db, organization_id, role_code="PROMOTER")

    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles={"ADMIN"}, type_="TICKET_CREATED",
        entity_type="ticket", entity_id=uuid.uuid4(), title="Nuovo ticket", exclude_user_id=admin1.id,
    )
    await db.commit()

    admin1_notifications = await notifications_service.list_my_notifications(db, organization_id=organization_id, user_id=admin1.id)
    admin2_notifications = await notifications_service.list_my_notifications(db, organization_id=organization_id, user_id=admin2.id)
    promoter_notifications = await notifications_service.list_my_notifications(db, organization_id=organization_id, user_id=promoter.id)

    assert len(admin1_notifications) == 0  # excluded (the actor who triggered it)
    assert len(admin2_notifications) == 1
    assert len(promoter_notifications) == 0  # wrong role, never notified


@pytest.mark.asyncio
async def test_mark_read_and_mark_all_read(db, organization_id):
    user = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=user.id, type_="TICKET_CREATED",
        entity_type="ticket", entity_id=uuid.uuid4(), title="Ticket 1",
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=user.id, type_="TICKET_CREATED",
        entity_type="ticket", entity_id=uuid.uuid4(), title="Ticket 2",
    )
    await db.commit()

    unread = await notifications_service.list_my_notifications(db, organization_id=organization_id, user_id=user.id, unread_only=True)
    assert len(unread) == 2

    marked = await notifications_service.mark_read(
        db, organization_id=organization_id, user_id=user.id, notification_id=unread[0].id
    )
    assert marked.is_read is True

    still_unread = await notifications_service.list_my_notifications(db, organization_id=organization_id, user_id=user.id, unread_only=True)
    assert len(still_unread) == 1

    count = await notifications_service.mark_all_read(db, organization_id=organization_id, user_id=user.id)
    assert count == 1
    none_unread = await notifications_service.list_my_notifications(db, organization_id=organization_id, user_id=user.id, unread_only=True)
    assert len(none_unread) == 0


@pytest.mark.asyncio
async def test_creating_a_contract_notifies_staff(db, organization_id):
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    back_office = await _make_user_with_role(db, organization_id, role_code="BACK_OFFICE_OPERATOR")
    promoter_user = await _make_user_with_role(db, organization_id, role_code="PROMOTER")

    customer = Customer(organization_id=organization_id, kind="PRIVATE", email=f"notif-{uuid.uuid4().hex[:8]}@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Notifiche 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY", supply_address_id=address.id)
    db.add(supply_point)
    await db.commit()

    product = Product(organization_id=organization_id, code=f"NOTIF-{uuid.uuid4().hex[:6]}", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    from app.core.db import utcnow
    product_version = ProductVersion(product_id=product.id, version_label="1.0", name="Notif test product", base_price_cents=1500, valid_from=utcnow())
    db.add(product_version)
    await db.commit()

    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Notif", last_name="Producer", promoter_code=f"NP-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )

    await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=product_version.id, producer_agent_id=agent.id,
        actor_user_id=admin.id, correlation_id=str(uuid.uuid4()),
    )

    admin_notifications = await notifications_service.list_my_notifications(db, organization_id=organization_id, user_id=admin.id)
    back_office_notifications = await notifications_service.list_my_notifications(db, organization_id=organization_id, user_id=back_office.id)
    promoter_notifications = await notifications_service.list_my_notifications(db, organization_id=organization_id, user_id=promoter_user.id)

    assert len(admin_notifications) == 0  # excluded -- admin was the actor who created it
    assert len(back_office_notifications) == 1
    assert back_office_notifications[0].type == "CONTRACT_CREATED"
    assert len(promoter_notifications) == 0  # not a staff role for this event
