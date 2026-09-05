import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.organizations.models import Organization
from app.domains.organizations.schemas import OrganizationSettingsUpdate

SETTINGS_KEYS = ("bank_iban", "bank_account_holder")


async def get_settings(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    org = await db.get(Organization, organization_id)
    if org is None:
        return {key: None for key in SETTINGS_KEYS}
    return {key: org.settings.get(key) for key in SETTINGS_KEYS}


async def update_settings(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: OrganizationSettingsUpdate
) -> dict:
    """Merges into the existing settings dict -- never replaces it wholesale,
    so a future unrelated key living in the same JSONB blob is never
    clobbered by an admin only touching the bank fields. Only fields
    actually present in `payload` overwrite (Pydantic's exclude_unset), so a
    PATCH that omits bank_account_holder leaves it exactly as it was."""
    org = await db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")

    updates = payload.model_dump(exclude_unset=True)
    # Mutating the dict in place doesn't get picked up by SQLAlchemy's
    # change-tracking on a JSONB column -- must assign a new dict.
    org.settings = {**org.settings, **updates}
    await db.commit()
    await db.refresh(org)
    return {key: org.settings.get(key) for key in SETTINGS_KEYS}
