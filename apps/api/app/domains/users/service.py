import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.users.models import User
from app.domains.users.schemas import ProfileUpdate

REQUIRED_PROFILE_FIELDS = (
    "fiscal_code",
    "residence_street",
    "residence_city",
    "residence_province",
    "residence_postal_code",
)


def is_profile_complete(user: User) -> bool:
    """Gates the mandatory profile-completion popup (see
    docs/business-rules.md#profile-completion) -- applies to every account,
    existing or new, per an explicit product decision to block until
    complete rather than grandfather this one."""
    return all(getattr(user, field) for field in REQUIRED_PROFILE_FIELDS)


class ProfileUpdateError(Exception):
    pass


async def update_profile(db: AsyncSession, *, user_id: uuid.UUID, payload: ProfileUpdate) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise ProfileUpdateError("User not found")

    user.fiscal_code = payload.fiscal_code
    user.residence_street = payload.residence_street
    user.residence_city = payload.residence_city
    user.residence_province = payload.residence_province.upper()
    user.residence_postal_code = payload.residence_postal_code
    user.residence_country = payload.residence_country.upper()

    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id,
        action="user.profile_completed", entity_type="user", entity_id=str(user.id),
        new_value={"fiscal_code": payload.fiscal_code, "residence_city": payload.residence_city},
    )
    await db.commit()
    await db.refresh(user)
    return user


async def mark_privacy_accepted(db: AsyncSession, *, user: User) -> None:
    """Does not commit -- caller (registration) commits as part of the same
    transaction, same convention as audit_service.record()."""
    user.privacy_accepted_at = datetime.now(UTC)
