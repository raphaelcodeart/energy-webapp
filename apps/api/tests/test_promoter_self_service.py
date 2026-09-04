"""Self-service "Lavora con noi" (apply_as_promoter) and the update_agent()
guard that keeps PENDING_APPROVAL -> ACTIVE exclusively behind approve_agent().

Covers two real bugs found and fixed in Session 20 (see
docs/implementation-progress.md):
- a SUSPENDED (but not blacklisted) agent could silently undo an admin's
  suspension just by re-applying through "Lavora con noi";
- update_agent() (network.manage-gated) let a plain ADMIN activate their own
  PENDING_APPROVAL suggestion, bypassing the network.approve gate entirely."""

import uuid

import pytest

from app.core.security import hash_password
from app.domains.network import service as network_service
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


async def _ensure_promoter_role(db, organization_id) -> None:
    """apply_as_promoter() grants PROMOTER via rbac_service.assign_role(),
    which requires the role to already be configured for the org (unlike
    _make_user_with_role's CUSTOMER/ADMIN roles, nothing else in this test
    module creates it)."""
    await _get_or_create_role(db, organization_id, role_code="PROMOTER")
    await db.commit()


async def _make_user_with_role(db, organization_id, *, role_code: str):
    user = User(
        organization_id=organization_id, email=f"{role_code.lower()}-{uuid.uuid4().hex[:6]}@example.demo",
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
async def test_apply_as_promoter_auto_activates_a_brand_new_applicant(db, organization_id):
    await _ensure_promoter_role(db, organization_id)
    customer_user = await _make_user_with_role(db, organization_id, role_code="CUSTOMER")

    agent = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=customer_user.id, first_name="Nuovo", last_name="Promoter",
    )

    assert agent.status == "ACTIVE"
    assert agent.user_id == customer_user.id


@pytest.mark.asyncio
async def test_reapplying_while_suspended_requires_manual_approval_not_auto_reactivation(db, organization_id):
    await _ensure_promoter_role(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer_user = await _make_user_with_role(db, organization_id, role_code="CUSTOMER")

    agent = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=customer_user.id, first_name="Sospeso", last_name="Promoter",
    )
    await network_service.update_agent(
        db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
        status_value="SUSPENDED", current_rank_id=None, actor_user_id=admin.id,
    )

    reapplied = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=customer_user.id, first_name="Sospeso", last_name="Promoter",
    )

    assert reapplied.status == "PENDING_APPROVAL"


@pytest.mark.asyncio
async def test_reapplying_while_terminated_and_not_blacklisted_still_auto_reactivates(db, organization_id):
    """Unlike SUSPENDED above, TERMINATED (the dedicated "Disattiva" button)
    is intentionally still self-service-reactivable -- regression guard so the
    SUSPENDED fix above doesn't accidentally widen to also block this."""
    await _ensure_promoter_role(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer_user = await _make_user_with_role(db, organization_id, role_code="CUSTOMER")

    agent = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=customer_user.id, first_name="Cessato", last_name="Promoter",
    )
    await network_service.update_agent(
        db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
        status_value="TERMINATED", current_rank_id=None, actor_user_id=admin.id,
    )

    reapplied = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=customer_user.id, first_name="Cessato", last_name="Promoter",
    )

    assert reapplied.status == "ACTIVE"


@pytest.mark.asyncio
async def test_reapplying_while_blacklisted_requires_manual_approval(db, organization_id):
    await _ensure_promoter_role(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer_user = await _make_user_with_role(db, organization_id, role_code="CUSTOMER")

    agent = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=customer_user.id, first_name="Blacklist", last_name="Promoter",
    )
    await network_service.update_agent(
        db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
        status_value="TERMINATED", current_rank_id=None, actor_user_id=admin.id, is_blacklisted=True,
    )

    reapplied = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=customer_user.id, first_name="Blacklist", last_name="Promoter",
    )

    assert reapplied.status == "PENDING_APPROVAL"


@pytest.mark.asyncio
async def test_update_agent_refuses_to_activate_a_pending_approval_agent(db, organization_id):
    """The bug: PATCH /network/agents/{id} is gated only on network.manage,
    which a plain ADMIN holds. Without this guard, that ADMIN could set
    status=ACTIVE directly and grant themselves the PROMOTER role for their
    own suggested agent, bypassing network.approve (approve_agent()) entirely."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Suggerito", last_name="Promoter",
        promoter_code=f"SUG-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
        actor_user_id=admin.id, status="PENDING_APPROVAL",
    )

    with pytest.raises(network_service.AgentApprovalError):
        await network_service.update_agent(
            db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
            status_value="ACTIVE", current_rank_id=None, actor_user_id=admin.id,
        )


@pytest.mark.asyncio
async def test_update_agent_still_allows_reactivating_a_suspended_agent(db, organization_id):
    """Regression guard: the PENDING_APPROVAL->ACTIVE guard above must not
    block the legitimate "Riattiva" action (SUSPENDED/TERMINATED -> ACTIVE),
    which is meant to stay available under plain network.manage."""
    await _ensure_promoter_role(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer_user = await _make_user_with_role(db, organization_id, role_code="CUSTOMER")
    agent = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=customer_user.id, first_name="Riattiva", last_name="Promoter",
    )
    await network_service.update_agent(
        db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
        status_value="SUSPENDED", current_rank_id=None, actor_user_id=admin.id,
    )

    reactivated = await network_service.update_agent(
        db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
        status_value="ACTIVE", current_rank_id=None, actor_user_id=admin.id,
    )

    assert reactivated.status == "ACTIVE"
