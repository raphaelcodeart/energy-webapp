import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.referral.models import (
    CustomerAttribution,
    PromoterCode,
    ReferralEvent,
    ReferralSession,
)

settings = get_settings()

# Attribution window: how long a referral session stays valid for attributing a
# later registration/purchase to the promoter who generated the click.
ATTRIBUTION_WINDOW_DAYS = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_active_promoter_code(
    db: AsyncSession, *, organization_id: uuid.UUID, code: str
) -> PromoterCode | None:
    now = utcnow()
    stmt = select(PromoterCode).where(
        PromoterCode.organization_id == organization_id,
        PromoterCode.code == code,
        PromoterCode.status == "ACTIVE",
        PromoterCode.valid_from <= now,
    )
    code_row = (await db.execute(stmt)).scalar_one_or_none()
    if code_row is None:
        return None
    if code_row.valid_to is not None and code_row.valid_to < now:
        return None
    return code_row


async def record_referral_click(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    promoter_code: PromoterCode,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[ReferralSession, str]:
    """Records the click, opens a referral session, and returns the raw (unhashed)
    cookie token to set on the visitor's browser -- only the hash is persisted."""
    now = utcnow()
    db.add(
        ReferralEvent(
            organization_id=organization_id,
            promoter_code_id=promoter_code.id,
            ip_address=ip_address,
            user_agent=user_agent,
            occurred_at=now,
        )
    )
    raw_token = secrets.token_urlsafe(32)
    session = ReferralSession(
        organization_id=organization_id,
        promoter_code_id=promoter_code.id,
        cookie_token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(days=ATTRIBUTION_WINDOW_DAYS),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session, raw_token


async def resolve_referral_session(
    db: AsyncSession, *, organization_id: uuid.UUID, cookie_token: str
) -> ReferralSession | None:
    stmt = select(ReferralSession).where(
        ReferralSession.organization_id == organization_id,
        ReferralSession.cookie_token_hash == _hash_token(cookie_token),
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None or session.expires_at < utcnow():
        return None
    return session


async def attribute_customer(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    promoter_code_id: uuid.UUID,
    referral_session_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None = None,
) -> CustomerAttribution:
    attribution = CustomerAttribution(
        organization_id=organization_id,
        customer_id=customer_id,
        promoter_code_id=promoter_code_id,
        referral_session_id=referral_session_id,
        attributed_at=utcnow(),
    )
    db.add(attribution)
    await audit_service.record(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="referral.customer_attributed",
        entity_type="customer",
        entity_id=str(customer_id),
        new_value={"promoter_code_id": str(promoter_code_id)},
    )
    await db.commit()
    await db.refresh(attribution)
    return attribution
