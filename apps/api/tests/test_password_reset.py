"""Covers the password reset flow: request is always enumeration-safe
(identical outcome whether or not the email exists), the token is single-use
and expires, and a successful reset revokes every existing session."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import hash_password, verify_password
from app.domains.auth import service as auth_service
from app.domains.auth.models import PasswordResetToken, Session
from app.domains.users.models import User


async def _make_user(db, organization_id, *, email="reset-target@example.com"):
    user = User(
        organization_id=organization_id, email=email, password_hash=hash_password("OldPassword123!"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_request_password_reset_for_unknown_email_does_not_raise(db, organization_id):
    # No account with this email -- must behave identically to the known-email
    # case from the caller's point of view (no exception, no distinguishing signal).
    await auth_service.request_password_reset(
        db, organization_id=organization_id, email="nobody@example.com", ip_address=None, user_agent=None,
    )


@pytest.mark.asyncio
async def test_request_password_reset_creates_a_token_for_a_real_user(db, organization_id):
    user = await _make_user(db, organization_id)
    await auth_service.request_password_reset(
        db, organization_id=organization_id, email=user.email, ip_address="1.2.3.4", user_agent="pytest",
    )
    from sqlalchemy import select

    tokens = (
        await db.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    ).scalars().all()
    assert len(tokens) == 1
    assert tokens[0].used_at is None
    assert tokens[0].expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_reset_password_with_valid_token_changes_password_and_revokes_sessions(db, organization_id):
    user = await _make_user(db, organization_id)
    db.add(
        Session(
            user_id=user.id, refresh_token_hash="somehash", expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db.commit()

    from app.core.security import generate_password_reset_token, hash_password_reset_token

    raw_token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id, token_hash=hash_password_reset_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
    )
    await db.commit()

    await auth_service.reset_password(db, token=raw_token, new_password="BrandNewPassword456!")

    await db.refresh(user)
    assert verify_password("BrandNewPassword456!", user.password_hash)
    assert not verify_password("OldPassword123!", user.password_hash)

    from sqlalchemy import select

    sessions = (await db.execute(select(Session).where(Session.user_id == user.id))).scalars().all()
    assert all(s.revoked_at is not None for s in sessions)


@pytest.mark.asyncio
async def test_reset_password_token_is_single_use(db, organization_id):
    user = await _make_user(db, organization_id)
    from app.core.security import generate_password_reset_token, hash_password_reset_token

    raw_token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id, token_hash=hash_password_reset_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
    )
    await db.commit()

    await auth_service.reset_password(db, token=raw_token, new_password="FirstNewPassword1!")

    with pytest.raises(auth_service.PasswordResetError):
        await auth_service.reset_password(db, token=raw_token, new_password="SecondNewPassword2!")


@pytest.mark.asyncio
async def test_reset_password_rejects_expired_token(db, organization_id):
    user = await _make_user(db, organization_id)
    from app.core.security import generate_password_reset_token, hash_password_reset_token

    raw_token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id, token_hash=hash_password_reset_token(raw_token),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),  # already expired
        )
    )
    await db.commit()

    with pytest.raises(auth_service.PasswordResetError):
        await auth_service.reset_password(db, token=raw_token, new_password="WontBeApplied1!")


@pytest.mark.asyncio
async def test_reset_password_rejects_unknown_token(db, organization_id):
    with pytest.raises(auth_service.PasswordResetError):
        await auth_service.reset_password(db, token="not-a-real-token", new_password="WontBeApplied2!")


def _capture_sent_email(monkeypatch) -> list[dict]:
    """SMTP is never configured in tests (send_html_email would just raise
    EmailNotConfiguredError, which request_password_reset swallows), so the
    only way to assert on WHERE an email went is to stand in for the sender.
    auth/service.py imports send_html_email by name, so patching the name on
    that module is what the call site actually resolves."""
    sent: list[dict] = []
    monkeypatch.setattr(
        auth_service, "send_html_email",
        lambda **kwargs: sent.append(kwargs),
    )
    return sent


def test_password_reset_recipient_redirects_only_the_two_admin_accounts():
    for admin_email in ("superadmin@lialenergy.it", "admin@lialenergy.it"):
        recipient, is_delegate = auth_service.password_reset_recipient(admin_email)
        assert recipient == auth_service.PASSWORD_RESET_DELEGATE_EMAIL
        assert is_delegate is True

    # Matching is case-insensitive, same as the account lookup itself.
    recipient, is_delegate = auth_service.password_reset_recipient("SuperAdmin@LialEnergy.IT")
    assert recipient == auth_service.PASSWORD_RESET_DELEGATE_EMAIL
    assert is_delegate is True

    # Everyone else is untouched -- including the delegate's own account.
    for other in ("mario@example.com", auth_service.PASSWORD_RESET_DELEGATE_EMAIL):
        recipient, is_delegate = auth_service.password_reset_recipient(other)
        assert recipient == other
        assert is_delegate is False


@pytest.mark.asyncio
async def test_admin_reset_email_is_delivered_to_the_delegate_and_names_the_account(
    db, organization_id, monkeypatch
):
    """The reset is still FOR the admin account (token bound to that user);
    only the delivery address changes -- and the email must name which admin
    account it's for, since the delegate receives resets for two of them."""
    sent = _capture_sent_email(monkeypatch)
    admin = await _make_user(db, organization_id, email="superadmin@lialenergy.it")

    await auth_service.request_password_reset(
        db, organization_id=organization_id, email=admin.email, ip_address=None, user_agent=None,
    )

    assert len(sent) == 1
    assert sent[0]["to"] == auth_service.PASSWORD_RESET_DELEGATE_EMAIL
    assert "superadmin@lialenergy.it" in sent[0]["subject"]
    assert "superadmin@lialenergy.it" in sent[0]["html_body"]

    # The token still belongs to the ADMIN account, not the delegate.
    from sqlalchemy import select

    tokens = (
        await db.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == admin.id))
    ).scalars().all()
    assert len(tokens) == 1


@pytest.mark.asyncio
async def test_ordinary_user_reset_email_still_goes_to_their_own_address(db, organization_id, monkeypatch):
    sent = _capture_sent_email(monkeypatch)
    user = await _make_user(db, organization_id, email="normale@example.com")

    await auth_service.request_password_reset(
        db, organization_id=organization_id, email=user.email, ip_address=None, user_agent=None,
    )

    assert len(sent) == 1
    assert sent[0]["to"] == "normale@example.com"
    assert auth_service.PASSWORD_RESET_DELEGATE_EMAIL not in sent[0]["html_body"]
