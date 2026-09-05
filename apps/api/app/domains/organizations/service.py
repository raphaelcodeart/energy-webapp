import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.organizations.models import Organization
from app.domains.organizations.schemas import OrganizationSettingsUpdate, PaymentSettingsUpdate

SETTINGS_KEYS = ("bank_iban", "bank_account_holder", "bank_transfer_instructions")
PAYMENT_SETTINGS_KEYS = ("stripe_publishable_key", "stripe_secret_key", "stripe_webhook_secret")


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


async def get_stripe_secret_key(db: AsyncSession, *, organization_id: uuid.UUID) -> str | None:
    """Internal use only (checkout-session creation) -- the raw secret,
    never returned by any endpoint. See get_payment_settings() for the
    masked, dashboard-facing view."""
    org = await db.get(Organization, organization_id)
    if org is None:
        return None
    return org.settings.get("stripe_secret_key") or None


async def is_bank_transfer_configured(db: AsyncSession, *, organization_id: uuid.UUID) -> bool:
    """Gates whether "Paga con bonifico" is even offered as an option --
    see orders/service.py::get_available_payment_methods(). An IBAN is the
    one field that actually matters; the holder name and instructions text
    are cosmetic."""
    org = await db.get(Organization, organization_id)
    if org is None:
        return False
    return bool(org.settings.get("bank_iban"))


async def is_stripe_configured(db: AsyncSession, *, organization_id: uuid.UUID) -> bool:
    """Gates whether "Paga con carta" is even offered -- see
    orders/service.py::get_available_payment_methods() and
    payments/service.py. Requires both keys: the secret key creates the
    Checkout Session server-side, the publishable key is what the (not yet
    built) client-side redirect would need -- either missing means Stripe
    isn't usable end-to-end yet."""
    org = await db.get(Organization, organization_id)
    if org is None:
        return False
    return bool(org.settings.get("stripe_secret_key")) and bool(org.settings.get("stripe_publishable_key"))


async def get_stripe_webhook_secret(db: AsyncSession, *, organization_id: uuid.UUID) -> str | None:
    org = await db.get(Organization, organization_id)
    if org is None:
        return None
    return org.settings.get("stripe_webhook_secret") or None


async def get_payment_settings(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    org = await db.get(Organization, organization_id)
    settings = org.settings if org else {}
    secret_key = settings.get("stripe_secret_key") or None
    return {
        "stripe_publishable_key": settings.get("stripe_publishable_key") or None,
        "stripe_secret_key_configured": secret_key is not None,
        "stripe_secret_key_last4": secret_key[-4:] if secret_key else None,
        "stripe_webhook_secret_configured": bool(settings.get("stripe_webhook_secret")),
    }


async def update_payment_settings(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: PaymentSettingsUpdate
) -> dict:
    """Same merge-not-replace discipline as update_settings(). A field
    omitted from the PATCH (as opposed to explicitly sent empty) leaves the
    stored secret untouched -- the dashboard form never has to re-paste an
    unchanged secret key just to update the publishable key next to it."""
    org = await db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")

    updates = payload.model_dump(exclude_unset=True)
    org.settings = {**org.settings, **updates}
    await db.commit()
    await db.refresh(org)
    return await get_payment_settings(db, organization_id=organization_id)
