import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.partners.models import Partner
from app.domains.partners.schemas import PartnerCreate, PartnerUpdate


class PartnerNameTakenError(Exception):
    pass


async def list_partners(db: AsyncSession, *, organization_id: uuid.UUID, active_only: bool = False) -> list[Partner]:
    stmt = select(Partner).where(Partner.organization_id == organization_id)
    if active_only:
        stmt = stmt.where(Partner.is_active.is_(True))
    stmt = stmt.order_by(Partner.name)
    return list((await db.execute(stmt)).scalars().all())


async def create_partner(db: AsyncSession, *, organization_id: uuid.UUID, payload: PartnerCreate) -> Partner:
    partner = Partner(organization_id=organization_id, name=payload.name, logo_url=payload.logo_url)
    db.add(partner)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise PartnerNameTakenError(f"A partner named '{payload.name}' already exists") from exc
    await db.refresh(partner)
    return partner


async def update_partner(
    db: AsyncSession, *, organization_id: uuid.UUID, partner_id: uuid.UUID, payload: PartnerUpdate
) -> Partner | None:
    partner = await db.get(Partner, partner_id)
    if partner is None or partner.organization_id != organization_id:
        return None
    if payload.name is not None:
        partner.name = payload.name
    if payload.logo_url is not None:
        partner.logo_url = payload.logo_url
    if payload.is_active is not None:
        partner.is_active = payload.is_active
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise PartnerNameTakenError(f"A partner named '{payload.name}' already exists") from exc
    await db.refresh(partner)
    return partner
