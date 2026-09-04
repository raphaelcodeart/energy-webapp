import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import EmailNotConfiguredError, send_email
from app.core.security import (
    create_access_token,
    generate_password_reset_token,
    generate_refresh_token,
    hash_password,
    hash_password_reset_token,
    hash_refresh_token,
    verify_password,
)
from app.domains.audit import service as audit_service
from app.domains.auth.models import PasswordResetToken, Session
from app.domains.auth.schemas import RegisterRequest
from app.domains.organizations.models import Organization
from app.domains.rbac.service import get_roles_for_user
from app.domains.users.models import User

settings = get_settings()
logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5  # placeholder policy, see docs/open-questions.md #7
LOCKOUT_WINDOW_MINUTES = 15

GENERIC_AUTH_ERROR = "Invalid email or password"


class AuthenticationError(Exception):
    pass


class AccountLockedError(Exception):
    pass


async def authenticate(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    email: str,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    """Returns (access_token, refresh_token). Raises AuthenticationError /
    AccountLockedError with an identical message shape for unknown-email and
    wrong-password cases, to avoid account enumeration."""
    stmt = select(User).where(User.organization_id == organization_id, User.email == email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None:
        # Still do a hash-verify against a dummy hash to keep response timing similar
        # regardless of whether the account exists (mitigates timing-based enumeration).
        verify_password(password, "$argon2id$v=19$m=65536,t=3,p=4$" + "0" * 22 + "$" + "0" * 43)
        # audit_log.organization_id is a real FK -- a bogus/stale organization_id
        # (e.g. a client still pointing at a demo org that got re-seeded with a new
        # id) must not crash the audit write with an unhandled IntegrityError; skip
        # it rather than fail the whole login attempt over a logging side effect.
        if await db.get(Organization, organization_id) is not None:
            await audit_service.record(
                db, organization_id=organization_id, actor_user_id=None,
                action="login.failed", entity_type="user", entity_id=email,
                reason="unknown_email", ip_address=ip_address, user_agent=user_agent,
            )
            await db.commit()
        raise AuthenticationError(GENERIC_AUTH_ERROR)

    if user.locked_until and user.locked_until > datetime.now(UTC):
        raise AccountLockedError("Account temporarily locked, try again later")

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=LOCKOUT_WINDOW_MINUTES)
            user.failed_login_attempts = 0
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=user.id,
            action="login.failed", entity_type="user", entity_id=str(user.id),
            reason="wrong_password", ip_address=ip_address, user_agent=user_agent,
        )
        await db.commit()
        raise AuthenticationError(GENERIC_AUTH_ERROR)

    user.failed_login_attempts = 0
    user.locked_until = None

    roles = await get_roles_for_user(db, user_id=user.id, organization_id=organization_id)
    access_token = create_access_token(
        subject=str(user.id), organization_id=str(organization_id), roles=roles
    )
    refresh_token = generate_refresh_token()
    session = Session(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user.id,
        action="login.success", entity_type="user", entity_id=str(user.id),
        ip_address=ip_address, user_agent=user_agent,
    )
    await db.commit()
    return access_token, refresh_token


async def rotate_refresh_token(
    db: AsyncSession, *, organization_id: uuid.UUID, refresh_token: str
) -> tuple[str, str]:
    """Validates and rotates a refresh token: the old session is revoked and a new
    one issued in the same call, so a stolen-and-reused old token is detectable
    (it will already be revoked) and cannot be replayed indefinitely."""
    token_hash = hash_refresh_token(refresh_token)
    stmt = select(Session).where(Session.refresh_token_hash == token_hash)
    session = (await db.execute(stmt)).scalar_one_or_none()

    if session is None or session.revoked_at is not None:
        raise AuthenticationError("Invalid refresh token")
    if session.expires_at < datetime.now(UTC):
        raise AuthenticationError("Refresh token expired")

    user = await db.get(User, session.user_id)
    if user is None or user.organization_id != organization_id:
        raise AuthenticationError("Invalid refresh token")

    session.revoked_at = datetime.now(UTC)

    roles = await get_roles_for_user(db, user_id=user.id, organization_id=organization_id)
    new_access_token = create_access_token(
        subject=str(user.id), organization_id=str(organization_id), roles=roles
    )
    new_refresh_token = generate_refresh_token()
    new_session = Session(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(new_refresh_token),
        user_agent=session.user_agent,
        ip_address=session.ip_address,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(new_session)
    await db.commit()
    return new_access_token, new_refresh_token


async def revoke_session(db: AsyncSession, *, refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    await db.execute(
        update(Session)
        .where(Session.refresh_token_hash == token_hash, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


async def revoke_all_sessions(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


class RegistrationError(Exception):
    pass


PRIVATE_LIKE_KINDS = {"PRIVATE", "SOLE_PROPRIETOR"}
COMPANY_LIKE_KINDS = {"COMPANY", "CONDOMINIUM"}


async def register_with_referral(db: AsyncSession, *, organization_id: uuid.UUID, payload: RegisterRequest) -> User:
    """Self-service signup, gated on a valid referral code -- registration is
    invite-only by design (docs/business-rules.md): every new customer must be
    attributed to the promoter who referred them, no exceptions. Validates the
    referral code FIRST, before creating anything, so an invalid/expired code
    never leaves a half-created account behind. Everything else -- user, role
    grant, customer, profile/company, attribution -- is one transaction, one
    commit, so a customer can never exist without their required promoter
    attribution."""
    from app.domains.customers.models import Company, Customer, CustomerProfile
    from app.domains.rbac.models import Role, UserRole
    from app.domains.referral import service as referral_service
    from app.domains.referral.models import CustomerAttribution

    if payload.kind in PRIVATE_LIKE_KINDS and not (payload.first_name and payload.last_name):
        raise RegistrationError("first_name and last_name are required for this customer kind")
    if payload.kind in COMPANY_LIKE_KINDS and not payload.company_name:
        raise RegistrationError("company_name is required for this customer kind")

    promoter_code = await referral_service.get_active_promoter_code(
        db, organization_id=organization_id, code=payload.referral_code
    )
    if promoter_code is None:
        raise RegistrationError("Invalid or expired referral code -- registration is invite-only")

    existing = (
        await db.execute(
            select(User).where(User.organization_id == organization_id, User.email == payload.email)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise RegistrationError("An account with this email already exists")

    role = (
        await db.execute(
            select(Role).where(
                (Role.organization_id == organization_id) | (Role.organization_id.is_(None)),
                Role.code == "CUSTOMER",
            )
        )
    ).scalars().first()
    if role is None:
        raise RegistrationError("Customer role is not configured for this organization")

    user = User(
        organization_id=organization_id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        status="ACTIVE",
    )
    db.add(user)
    await db.flush()

    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))

    customer = Customer(
        organization_id=organization_id,
        user_id=user.id,
        kind=payload.kind,
        email=payload.email,
        phone=payload.phone,
    )
    db.add(customer)
    await db.flush()

    if payload.kind in PRIVATE_LIKE_KINDS:
        db.add(CustomerProfile(customer_id=customer.id, first_name=payload.first_name, last_name=payload.last_name))
    else:
        db.add(Company(customer_id=customer.id, company_name=payload.company_name))

    db.add(
        CustomerAttribution(
            organization_id=organization_id,
            customer_id=customer.id,
            promoter_code_id=promoter_code.id,
            referral_session_id=None,
            attributed_at=datetime.now(UTC),
        )
    )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user.id,
        action="auth.self_registered", entity_type="customer", entity_id=str(customer.id),
        new_value={"email": payload.email, "referral_code": payload.referral_code},
    )
    await db.commit()
    await db.refresh(user)
    return user


PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 60


class PasswordResetError(Exception):
    pass


async def request_password_reset(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    email: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Always returns normally, whether or not the email belongs to a real
    account -- same enumeration-safety principle as authenticate(): a caller
    must never be able to use this endpoint to discover which emails have
    accounts."""
    stmt = select(User).where(User.organization_id == organization_id, User.email == email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=None,
            action="password_reset.requested", entity_type="user", entity_id=email,
            reason="unknown_email", ip_address=ip_address, user_agent=user_agent,
        )
        await db.commit()
        return

    token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
    )

    reset_link = f"{settings.public_app_base_url}/reset-password?token={token}"
    body = (
        "Hai richiesto di reimpostare la password del tuo account Lial Energy.\n\n"
        f"Apri questo link entro {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minuti per scegliere una nuova password:\n"
        f"{reset_link}\n\n"
        "Se non hai richiesto tu questa operazione, ignora questa email."
    )
    try:
        send_email(to=email, subject="Reimposta la tua password - Lial Energy", body=body)
        delivery = "sent"
    except EmailNotConfiguredError:
        # No SMTP configured yet. The token/link is deliberately NOT written
        # anywhere a web-UI role (even audit.read) could read it -- that would
        # let any admin-tier account take over any user's account by reading
        # their reset link. It goes to the process log only, which requires
        # server shell access (`docker compose logs api`), a much higher trust
        # bar. See docs/business-rules.md §Password reset.
        logger.warning("Password reset for %s (SMTP not configured) -- link: %s", email, reset_link)
        delivery = "logged_only"

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user.id,
        action="password_reset.requested", entity_type="user", entity_id=str(user.id),
        new_value={"delivery": delivery},
        ip_address=ip_address, user_agent=user_agent,
    )
    await db.commit()


async def reset_password(db: AsyncSession, *, token: str, new_password: str) -> None:
    token_hash = hash_password_reset_token(token)
    stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    reset_token = (await db.execute(stmt)).scalar_one_or_none()

    if reset_token is None or reset_token.used_at is not None:
        raise PasswordResetError("Invalid or already-used reset link")
    if reset_token.expires_at < datetime.now(UTC):
        raise PasswordResetError("This reset link has expired")

    user = await db.get(User, reset_token.user_id)
    if user is None:
        raise PasswordResetError("Invalid or already-used reset link")

    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    reset_token.used_at = datetime.now(UTC)

    # A password reset is exactly the moment to kill every existing session --
    # if the reset was needed because the old password leaked, whoever has it
    # (and any session opened with it) must be logged out now.
    await db.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )

    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id,
        action="password_reset.completed", entity_type="user", entity_id=str(user.id),
    )
    await db.commit()
