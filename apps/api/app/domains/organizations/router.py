from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.organizations import service as organizations_service
from app.domains.organizations.schemas import (
    OrganizationSettingsRead,
    OrganizationSettingsUpdate,
    PaymentSettingsRead,
    PaymentSettingsUpdate,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/me/settings", response_model=OrganizationSettingsRead)
async def get_my_organization_settings(
    current_user: CurrentUser = Depends(require_permission("organization.manage")),
    db: AsyncSession = Depends(get_db),
) -> OrganizationSettingsRead:
    settings = await organizations_service.get_settings(db, organization_id=current_user.organization_id)
    return OrganizationSettingsRead(**settings)


@router.patch("/me/settings", response_model=OrganizationSettingsRead)
async def update_my_organization_settings(
    payload: OrganizationSettingsUpdate,
    current_user: CurrentUser = Depends(require_permission("organization.manage")),
    db: AsyncSession = Depends(get_db),
) -> OrganizationSettingsRead:
    settings = await organizations_service.update_settings(
        db, organization_id=current_user.organization_id, payload=payload
    )
    return OrganizationSettingsRead(**settings)


@router.get("/me/payment-settings", response_model=PaymentSettingsRead)
async def get_my_payment_settings(
    current_user: CurrentUser = Depends(require_permission("organization.manage_payments")),
    db: AsyncSession = Depends(get_db),
) -> PaymentSettingsRead:
    """Stripe configuration -- deliberately a stricter permission than the
    bank IBAN settings (organization.manage_payments is SUPER_ADMIN only,
    not ORGANIZATION_ADMIN/ADMIN), per the user's explicit request: whoever
    can process card payments for the org is a smaller circle than whoever
    can see/edit where bonifico money goes."""
    settings = await organizations_service.get_payment_settings(db, organization_id=current_user.organization_id)
    return PaymentSettingsRead(**settings)


@router.patch("/me/payment-settings", response_model=PaymentSettingsRead)
async def update_my_payment_settings(
    payload: PaymentSettingsUpdate,
    current_user: CurrentUser = Depends(require_permission("organization.manage_payments")),
    db: AsyncSession = Depends(get_db),
) -> PaymentSettingsRead:
    settings = await organizations_service.update_payment_settings(
        db, organization_id=current_user.organization_id, payload=payload
    )
    return PaymentSettingsRead(**settings)
