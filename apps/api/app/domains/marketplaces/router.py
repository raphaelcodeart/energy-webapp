"""/marketplaces -- the rules shared by the imported-product shops (Session 68)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.domains.marketplaces import rules

router = APIRouter(prefix="/marketplaces", tags=["marketplaces"])


class MarketplaceConfigRead(BaseModel):
    labels: dict[str, str]
    card_surcharge_percentage: int
    default_credit_percentage: int
    max_credit_percentage: int


class MarketplaceConfigUpdate(BaseModel):
    labels: dict[str, str] | None = None
    card_surcharge_percentage: int | None = Field(default=None, ge=0, le=rules.MAX_CARD_SURCHARGE_PERCENTAGE)


@router.get("/config", response_model=MarketplaceConfigRead)
async def get_marketplace_config(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceConfigRead:
    """Every logged-in user: the Shop needs the names of the tabs and the
    card surcharge to show both prices."""
    return MarketplaceConfigRead(**await rules.get_config(db, organization_id=current_user.organization_id))


@router.patch("/config", response_model=MarketplaceConfigRead)
async def update_marketplace_config(
    payload: MarketplaceConfigUpdate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceConfigRead:
    return MarketplaceConfigRead(
        **await rules.update_config(
            db, organization_id=current_user.organization_id, labels=payload.labels,
            card_surcharge_percentage=payload.card_surcharge_percentage,
        )
    )
