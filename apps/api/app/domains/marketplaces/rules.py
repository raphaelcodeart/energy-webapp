"""Rules shared by the three shops of imported products (Session 68):

- Marketplace 1 -- AliExpress (`imported_products`, "Acquisti" by hand);
- Marketplace 2 -- CJ Dropshipping (`cj_dropshipping`);
- Marketplace 3 -- Shopify (`shopify_dropshipping`).

Each keeps its own tables and its own supplier logic; what the customer is
promised is the same everywhere, and lives here:

- **Card costs more.** The prices shown are the bank-transfer ones; paying
  the euro part by card adds `card_surcharge_percentage` (default 5%),
  computed by the server on the residual after LialCash and frozen on the
  order. See docs/business-rules.md#marketplace for the legal note.
- **LialCash only partly.** These products never earn cashback, they only
  let the customer spend it, and never for the whole price: a new product
  starts at DEFAULT_CREDIT_PERCENTAGE, the administrator may raise it up to
  MAX_CREDIT_PERCENTAGE.
- **Names in the Shop** are settings, "Marketplace 1/2/3" by default.

Organization-level settings, in `organizations.settings` (JSONB):
`marketplace_card_surcharge_percentage`, `marketplace_labels`.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.organizations.models import Organization

DEFAULT_CARD_SURCHARGE_PERCENTAGE = 5
MAX_CARD_SURCHARGE_PERCENTAGE = 30
#: LialCash usable on a newly imported product, percent of its price.
DEFAULT_CREDIT_PERCENTAGE = 30
#: Never 100: an imported product is never bought entirely with LialCash.
MAX_CREDIT_PERCENTAGE = 99

ALIEXPRESS = "aliexpress"
CJ = "cj"
SHOPIFY = "shopify"
MARKETPLACES = (ALIEXPRESS, CJ, SHOPIFY)
DEFAULT_LABELS = {ALIEXPRESS: "Marketplace 1", CJ: "Marketplace 2", SHOPIFY: "Marketplace 3"}


class CreditPercentageError(ValueError):
    pass


def check_credit_percentage(value: int) -> int:
    """Refuses a LialCash share an imported product may not have."""
    if value < 0 or value > MAX_CREDIT_PERCENTAGE:
        raise CreditPercentageError(
            f"Sui prodotti dei Marketplace il LialCash può coprire al massimo il {MAX_CREDIT_PERCENTAGE}% del prezzo."
        )
    return value


def card_surcharge_cents(*, residual_cents: int, percentage: int) -> int:
    """The extra for paying `residual_cents` by card: the percentage of the
    residual, rounded half up to the cent (2,50 EUR at 5% -> 0,13 EUR).
    Nothing on a zero residual or a zero percentage."""
    if residual_cents <= 0 or percentage <= 0:
        return 0
    return (residual_cents * percentage + 50) // 100


async def _settings(db: AsyncSession, organization_id: uuid.UUID) -> dict:
    org = await db.get(Organization, organization_id)
    return dict(org.settings or {}) if org is not None else {}


async def get_card_surcharge_percentage(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    value = (await _settings(db, organization_id)).get("marketplace_card_surcharge_percentage")
    if value is None:
        return DEFAULT_CARD_SURCHARGE_PERCENTAGE
    try:
        return max(0, min(MAX_CARD_SURCHARGE_PERCENTAGE, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_CARD_SURCHARGE_PERCENTAGE


async def get_labels(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, str]:
    stored = (await _settings(db, organization_id)).get("marketplace_labels") or {}
    return {
        key: (str(stored.get(key)).strip() if stored.get(key) and str(stored.get(key)).strip() else DEFAULT_LABELS[key])
        for key in MARKETPLACES
    }


async def get_config(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    return {
        "labels": await get_labels(db, organization_id=organization_id),
        "card_surcharge_percentage": await get_card_surcharge_percentage(db, organization_id=organization_id),
        "default_credit_percentage": DEFAULT_CREDIT_PERCENTAGE,
        "max_credit_percentage": MAX_CREDIT_PERCENTAGE,
    }


async def update_config(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    labels: dict[str, str] | None,
    card_surcharge_percentage: int | None,
) -> dict:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")
    settings = dict(org.settings or {})
    if labels is not None:
        current = dict(settings.get("marketplace_labels") or {})
        for key, value in labels.items():
            if key in MARKETPLACES:
                current[key] = (value or "").strip()[:40] or DEFAULT_LABELS[key]
        settings["marketplace_labels"] = current
    if card_surcharge_percentage is not None:
        settings["marketplace_card_surcharge_percentage"] = max(
            0, min(MAX_CARD_SURCHARGE_PERCENTAGE, int(card_surcharge_percentage))
        )
    # A new dict: in-place mutation of a JSONB column is not tracked.
    org.settings = settings
    await db.commit()
    return await get_config(db, organization_id=organization_id)
