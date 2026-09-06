"""Mandatory-verification/profile-completion account gates (Session 27):
email verification (new registrations only -- see the 0026 migration's
grandfather backfill for existing accounts), mandatory fiscal-code/residence
profile completion (applies retroactively to everyone), and the
collaboration-agreement + OTP gate on 'lavora con noi'. SMTP is never
configured in this test environment, so every send_*_email call here falls
through to its EmailNotConfiguredError/best-effort-log path -- these tests
only cover the DB-side state machine, not actual delivery."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import hash_otp_code, hash_password
from app.domains.auth import service as auth_service
from app.domains.auth.models import EmailVerificationToken, OtpCode
from app.domains.network import service as network_service
from app.domains.rbac.models import Role, UserRole
from app.domains.users import service as users_service
from app.domains.users.models import User
from app.domains.users.schemas import ProfileUpdate


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


async def _make_user(db, organization_id, *, role_code: str = "CUSTOMER") -> User:
    user = User(
        organization_id=organization_id, email=f"gate-{uuid.uuid4().hex[:8]}@example.demo",
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
async def test_is_profile_complete_requires_all_five_fields(db, organization_id):
    user = await _make_user(db, organization_id)
    assert users_service.is_profile_complete(user) is False

    await users_service.update_profile(
        db, user_id=user.id,
        payload=ProfileUpdate(
            fiscal_code="RSSMRA80A01H501U", residence_street="Via Roma 1", residence_city="Roma",
            residence_province="rm", residence_postal_code="00100",
        ),
    )
    await db.refresh(user)
    assert users_service.is_profile_complete(user) is True
    # province/fiscal_code are normalized to uppercase on write.
    assert user.residence_province == "RM"
    assert user.fiscal_code == "RSSMRA80A01H501U"


@pytest.mark.asyncio
async def test_send_and_verify_email_round_trip(db, organization_id):
    user = await _make_user(db, organization_id)
    assert user.email_verified_at is None

    await auth_service.send_verification_email(db, user=user)
    from sqlalchemy import select

    token_row = (
        await db.execute(select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))
    ).scalar_one()
    assert token_row.used_at is None

    # verify_email() only ever sees the raw token via the emailed link, never
    # the hash -- reconstruct it the same way a real caller couldn't, so
    # instead drive it through the DB row's hash is not possible (hash isn't
    # reversible); this covers the failure path plus a manually-issued token.
    with pytest.raises(auth_service.EmailVerificationError):
        await auth_service.verify_email(db, token="not-a-real-token")

    # Directly exercise the success path with a token we mint ourselves,
    # bypassing the (untestable-without-capturing-the-email) real one.
    from app.core.security import generate_email_verification_token, hash_email_verification_token

    real_token = generate_email_verification_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id, token_hash=hash_email_verification_token(real_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db.commit()

    verified_user = await auth_service.verify_email(db, token=real_token)
    assert verified_user.email_verified_at is not None

    with pytest.raises(auth_service.EmailVerificationError):
        await auth_service.verify_email(db, token=real_token)  # single-use


@pytest.mark.asyncio
async def test_verify_email_rejects_expired_token(db, organization_id):
    from app.core.security import generate_email_verification_token, hash_email_verification_token

    user = await _make_user(db, organization_id)
    token = generate_email_verification_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id, token_hash=hash_email_verification_token(token),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    await db.commit()

    with pytest.raises(auth_service.EmailVerificationError):
        await auth_service.verify_email(db, token=token)


@pytest.mark.asyncio
async def test_resend_verification_is_a_noop_once_verified(db, organization_id):
    from sqlalchemy import func, select

    user = await _make_user(db, organization_id)
    user.email_verified_at = datetime.now(UTC)
    await db.commit()

    await auth_service.resend_verification_email(db, user=user)

    count = (
        await db.execute(select(func.count()).select_from(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))
    ).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_verify_otp_consumes_the_code_exactly_once(db, organization_id):
    user = await _make_user(db, organization_id)
    db.add(
        OtpCode(
            user_id=user.id, purpose="TEST_PURPOSE", code_hash=hash_otp_code("654321"),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    await db.commit()

    assert await auth_service.verify_otp(db, user_id=user.id, purpose="TEST_PURPOSE", code="000000") is False
    assert await auth_service.verify_otp(db, user_id=user.id, purpose="TEST_PURPOSE", code="654321") is True
    # Second attempt with the same (now-used) code must fail.
    assert await auth_service.verify_otp(db, user_id=user.id, purpose="TEST_PURPOSE", code="654321") is False


@pytest.mark.asyncio
async def test_verify_otp_rejects_expired_code(db, organization_id):
    user = await _make_user(db, organization_id)
    db.add(
        OtpCode(
            user_id=user.id, purpose="TEST_PURPOSE", code_hash=hash_otp_code("111111"),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    await db.commit()

    assert await auth_service.verify_otp(db, user_id=user.id, purpose="TEST_PURPOSE", code="111111") is False


@pytest.mark.asyncio
async def test_apply_as_promoter_rejects_missing_contract_acceptance(db, organization_id):
    await _get_or_create_role(db, organization_id, role_code="PROMOTER")
    await db.commit()
    user = await _make_user(db, organization_id, role_code="CUSTOMER")

    with pytest.raises(network_service.ContractNotAcceptedError):
        await network_service.apply_as_promoter(
            db, organization_id=organization_id, user_id=user.id, first_name="Test", last_name="Promoter",
            accept_contract=False, otp_code="000000",
        )


@pytest.mark.asyncio
async def test_apply_as_promoter_rejects_invalid_otp(db, organization_id):
    await _get_or_create_role(db, organization_id, role_code="PROMOTER")
    await db.commit()
    user = await _make_user(db, organization_id, role_code="CUSTOMER")

    with pytest.raises(network_service.InvalidOtpError):
        await network_service.apply_as_promoter(
            db, organization_id=organization_id, user_id=user.id, first_name="Test", last_name="Promoter",
            accept_contract=True, otp_code="999999",
        )


@pytest.mark.asyncio
async def test_apply_as_promoter_records_collaboration_acceptance(db, organization_id):
    await _get_or_create_role(db, organization_id, role_code="PROMOTER")
    await db.commit()
    user = await _make_user(db, organization_id, role_code="CUSTOMER")
    db.add(
        OtpCode(
            user_id=user.id, purpose=auth_service.PROMOTER_APPLICATION_OTP_PURPOSE,
            code_hash=hash_otp_code("246810"), expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    await db.commit()

    agent = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=user.id, first_name="Test", last_name="Promoter",
        accept_contract=True, otp_code="246810",
    )

    assert agent.status == "ACTIVE"
    assert agent.collaboration_accepted_at is not None
    assert agent.collaboration_otp_verified_at is not None
    assert agent.collaboration_contract_version == network_service.COLLABORATION_CONTRACT_VERSION
