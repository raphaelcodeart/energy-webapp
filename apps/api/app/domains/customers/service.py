import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.customers.models import Address, Company, Customer, CustomerProfile, SupplyPoint
from app.domains.customers.schemas import CustomerCreate, CustomerUpdate, SupplyPointCreate

PRIVATE_LIKE_KINDS = {"PRIVATE", "SOLE_PROPRIETOR"}
COMPANY_LIKE_KINDS = {"COMPANY", "CONDOMINIUM"}


class CustomerValidationError(Exception):
    pass


def display_name_for(kind: str, profile: CustomerProfile | None, company: Company | None) -> str:
    if kind in COMPANY_LIKE_KINDS and company is not None:
        return company.company_name
    if profile is not None:
        return f"{profile.first_name} {profile.last_name}".strip()
    return "—"


async def list_customers(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    stmt = select(Customer).where(Customer.organization_id == organization_id).order_by(Customer.created_at.desc())
    customers = (await db.execute(stmt)).scalars().all()
    if not customers:
        return []

    ids = [c.id for c in customers]
    profiles = {
        p.customer_id: p
        for p in (await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(ids)))).scalars()
    }
    companies = {
        c.customer_id: c
        for c in (await db.execute(select(Company).where(Company.customer_id.in_(ids)))).scalars()
    }

    return [
        {
            "id": c.id,
            "organization_id": c.organization_id,
            "kind": c.kind,
            "fiscal_code": c.fiscal_code,
            "vat_number": c.vat_number,
            "email": c.email,
            "phone": c.phone,
            "display_name": display_name_for(c.kind, profiles.get(c.id), companies.get(c.id)),
        }
        for c in customers
    ]


async def get_customer_detail(db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID) -> dict | None:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        return None

    profile = await db.get(CustomerProfile, customer_id)
    company = await db.get(Company, customer_id)
    addresses = (
        await db.execute(select(Address).where(Address.customer_id == customer_id))
    ).scalars().all()
    supply_points = (
        await db.execute(select(SupplyPoint).where(SupplyPoint.customer_id == customer_id))
    ).scalars().all()

    return {
        "id": customer.id,
        "organization_id": customer.organization_id,
        "kind": customer.kind,
        "fiscal_code": customer.fiscal_code,
        "vat_number": customer.vat_number,
        "email": customer.email,
        "phone": customer.phone,
        "display_name": display_name_for(customer.kind, profile, company),
        "addresses": list(addresses),
        "supply_points": list(supply_points),
    }


async def create_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: CustomerCreate, actor_user_id: uuid.UUID
) -> Customer:
    if payload.kind in PRIVATE_LIKE_KINDS and not (payload.first_name and payload.last_name):
        raise CustomerValidationError("first_name and last_name are required for this customer kind")
    if payload.kind in COMPANY_LIKE_KINDS and not payload.company_name:
        raise CustomerValidationError("company_name is required for this customer kind")

    customer = Customer(
        organization_id=organization_id,
        kind=payload.kind,
        email=payload.email,
        phone=payload.phone,
        fiscal_code=payload.fiscal_code,
        vat_number=payload.vat_number,
    )
    db.add(customer)
    await db.flush()

    if payload.kind in PRIVATE_LIKE_KINDS:
        db.add(CustomerProfile(customer_id=customer.id, first_name=payload.first_name, last_name=payload.last_name))
    else:
        db.add(
            Company(
                customer_id=customer.id,
                company_name=payload.company_name,
                legal_form=payload.legal_form,
                sdi_code=payload.sdi_code,
            )
        )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="customer.created", entity_type="customer", entity_id=str(customer.id),
        new_value={"kind": payload.kind, "email": payload.email},
    )
    await db.commit()
    await db.refresh(customer)
    return customer


async def update_customer(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    actor_user_id: uuid.UUID,
) -> Customer | None:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        return None

    previous = {"email": customer.email, "phone": customer.phone}
    if payload.email is not None:
        customer.email = payload.email
    if payload.phone is not None:
        customer.phone = payload.phone
    if payload.fiscal_code is not None:
        customer.fiscal_code = payload.fiscal_code
    if payload.vat_number is not None:
        customer.vat_number = payload.vat_number

    if payload.first_name is not None or payload.last_name is not None:
        profile = await db.get(CustomerProfile, customer_id)
        if profile is not None:
            if payload.first_name is not None:
                profile.first_name = payload.first_name
            if payload.last_name is not None:
                profile.last_name = payload.last_name

    if payload.company_name is not None:
        company = await db.get(Company, customer_id)
        if company is not None:
            company.company_name = payload.company_name

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="customer.updated", entity_type="customer", entity_id=str(customer.id),
        previous_value=previous, new_value={"email": customer.email, "phone": customer.phone},
    )
    await db.commit()
    await db.refresh(customer)
    return customer


async def add_supply_point(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    payload: SupplyPointCreate,
    actor_user_id: uuid.UUID,
) -> SupplyPoint | None:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        return None

    address = Address(
        organization_id=organization_id,
        customer_id=customer_id,
        kind="SUPPLY",
        street=payload.street,
        city=payload.city,
        province=payload.province,
        postal_code=payload.postal_code,
        country=payload.country,
    )
    db.add(address)
    await db.flush()

    supply_point = SupplyPoint(
        organization_id=organization_id,
        customer_id=customer_id,
        energy_type=payload.energy_type,
        pod_code=payload.pod_code,
        pdr_code=payload.pdr_code,
        meter_number=payload.meter_number,
        supply_address_id=address.id,
    )
    db.add(supply_point)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="customer.supply_point_added", entity_type="customer", entity_id=str(customer_id),
        new_value={"energy_type": payload.energy_type},
    )
    await db.commit()
    await db.refresh(supply_point)
    return supply_point
