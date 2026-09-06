"""Admin "congela utente" (freeze/unfreeze), added Session 28 -- blocks login
immediately (both for a not-yet-logged-in attempt and an already-open
session, via revoke_all_sessions) without touching any of the account's
other data. "Elimina utente" (hard delete/anonymize) was explicitly deferred
by the user -- not implemented yet, see docs/business-rules.md."""

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.auth import service as auth_service
from app.domains.auth.models import Session
from app.domains.users import service as users_service
from app.domains.users.models import User


async def _make_user(db, organization_id, *, email: str, password: str = "correct-horse-battery-staple") -> User:
    user = User(organization_id=organization_id, email=email, password_hash=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_freeze_sets_status_and_blocks_login(db, organization_id):
    admin = await _make_user(db, organization_id, email="admin-freeze@example.demo")
    target = await _make_user(db, organization_id, email="target-freeze@example.demo")

    frozen = await users_service.freeze_user(
        db, organization_id=organization_id, user_id=target.id, actor_user_id=admin.id
    )
    assert frozen is not None
    assert frozen.status == "FROZEN"

    with pytest.raises(auth_service.AccountLockedError):
        await auth_service.authenticate(
            db, organization_id=organization_id, email="target-freeze@example.demo",
            password="correct-horse-battery-staple", ip_address="127.0.0.1", user_agent="pytest",
        )


@pytest.mark.asyncio
async def test_freeze_revokes_existing_sessions_immediately(db, organization_id):
    admin = await _make_user(db, organization_id, email="admin-freeze2@example.demo")
    target = await _make_user(db, organization_id, email="target-freeze2@example.demo")

    _, refresh_token = await auth_service.authenticate(
        db, organization_id=organization_id, email="target-freeze2@example.demo",
        password="correct-horse-battery-staple", ip_address="127.0.0.1", user_agent="pytest",
    )

    await users_service.freeze_user(
        db, organization_id=organization_id, user_id=target.id, actor_user_id=admin.id
    )

    session = (
        await db.execute(select(Session).where(Session.user_id == target.id))
    ).scalar_one()
    assert session.revoked_at is not None

    with pytest.raises(auth_service.AuthenticationError):
        await auth_service.rotate_refresh_token(
            db, organization_id=organization_id, refresh_token=refresh_token
        )


@pytest.mark.asyncio
async def test_unfreeze_restores_login(db, organization_id):
    admin = await _make_user(db, organization_id, email="admin-freeze3@example.demo")
    target = await _make_user(db, organization_id, email="target-freeze3@example.demo")

    await users_service.freeze_user(db, organization_id=organization_id, user_id=target.id, actor_user_id=admin.id)
    await users_service.unfreeze_user(db, organization_id=organization_id, user_id=target.id, actor_user_id=admin.id)

    access_token, refresh_token = await auth_service.authenticate(
        db, organization_id=organization_id, email="target-freeze3@example.demo",
        password="correct-horse-battery-staple", ip_address="127.0.0.1", user_agent="pytest",
    )
    assert access_token and refresh_token


@pytest.mark.asyncio
async def test_cannot_freeze_own_account(db, organization_id):
    admin = await _make_user(db, organization_id, email="admin-freeze4@example.demo")

    with pytest.raises(users_service.UserLifecycleError):
        await users_service.freeze_user(
            db, organization_id=organization_id, user_id=admin.id, actor_user_id=admin.id
        )


@pytest.mark.asyncio
async def test_freeze_returns_none_for_user_in_another_organization(db, organization_id):
    from app.domains.organizations.models import Organization

    other_org = Organization(name="Other Org", status="ACTIVE")
    db.add(other_org)
    await db.commit()
    await db.refresh(other_org)

    admin = await _make_user(db, organization_id, email="admin-freeze5@example.demo")
    outsider = await _make_user(db, other_org.id, email="outsider@example.demo")

    result = await users_service.freeze_user(
        db, organization_id=organization_id, user_id=outsider.id, actor_user_id=admin.id
    )
    assert result is None
