import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.domains.auth import service as auth_service
from app.domains.users.models import User


async def _make_user(db: AsyncSession, organization_id: uuid.UUID, email: str, password: str) -> User:
    user = User(organization_id=organization_id, email=email, password_hash=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_successful_login_issues_tokens(db, organization_id):
    await _make_user(db, organization_id, "alice@example.com", "correct-horse-battery-staple")

    access_token, refresh_token = await auth_service.authenticate(
        db, organization_id=organization_id, email="alice@example.com",
        password="correct-horse-battery-staple", ip_address="127.0.0.1", user_agent="pytest",
    )
    assert access_token
    assert refresh_token


@pytest.mark.asyncio
async def test_wrong_password_and_unknown_email_give_identical_error_message(db, organization_id):
    await _make_user(db, organization_id, "bob@example.com", "correct-horse-battery-staple")

    with pytest.raises(auth_service.AuthenticationError) as wrong_password_exc:
        await auth_service.authenticate(
            db, organization_id=organization_id, email="bob@example.com",
            password="wrong-password", ip_address="127.0.0.1", user_agent="pytest",
        )

    with pytest.raises(auth_service.AuthenticationError) as unknown_email_exc:
        await auth_service.authenticate(
            db, organization_id=organization_id, email="nobody@example.com",
            password="whatever", ip_address="127.0.0.1", user_agent="pytest",
        )

    # Account enumeration mitigation: both failure modes surface the same message.
    assert str(wrong_password_exc.value) == str(unknown_email_exc.value) == auth_service.GENERIC_AUTH_ERROR


@pytest.mark.asyncio
async def test_account_locks_after_max_failed_attempts(db, organization_id):
    await _make_user(db, organization_id, "carol@example.com", "correct-horse-battery-staple")

    for _ in range(auth_service.MAX_FAILED_ATTEMPTS):
        with pytest.raises(auth_service.AuthenticationError):
            await auth_service.authenticate(
                db, organization_id=organization_id, email="carol@example.com",
                password="wrong", ip_address="127.0.0.1", user_agent="pytest",
            )

    with pytest.raises(auth_service.AccountLockedError):
        await auth_service.authenticate(
            db, organization_id=organization_id, email="carol@example.com",
            password="correct-horse-battery-staple", ip_address="127.0.0.1", user_agent="pytest",
        )


@pytest.mark.asyncio
async def test_refresh_token_rotation_revokes_old_session(db, organization_id):
    await _make_user(db, organization_id, "dave@example.com", "correct-horse-battery-staple")
    _, refresh_token = await auth_service.authenticate(
        db, organization_id=organization_id, email="dave@example.com",
        password="correct-horse-battery-staple", ip_address="127.0.0.1", user_agent="pytest",
    )

    new_access, new_refresh = await auth_service.rotate_refresh_token(
        db, organization_id=organization_id, refresh_token=refresh_token
    )
    assert new_access and new_refresh
    assert new_refresh != refresh_token

    # The old (now-revoked) refresh token must no longer work.
    with pytest.raises(auth_service.AuthenticationError):
        await auth_service.rotate_refresh_token(
            db, organization_id=organization_id, refresh_token=refresh_token
        )
