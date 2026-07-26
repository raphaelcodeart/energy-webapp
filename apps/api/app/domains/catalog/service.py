import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.audit import service as audit_service
from app.domains.catalog.models import Product, ProductVersion
from app.domains.catalog.schemas import (
    ProductCreate,
    ProductUpdate,
    ProductVersionCreate,
    ProductVersionUpdate,
)


async def list_products(db: AsyncSession, *, organization_id: uuid.UUID) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.organization_id == organization_id)
        .order_by(Product.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_product_with_versions(
    db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID
) -> tuple[Product, list[ProductVersion]] | None:
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != organization_id:
        return None
    stmt = (
        select(ProductVersion)
        .where(ProductVersion.product_id == product_id)
        .order_by(ProductVersion.valid_from.desc())
    )
    versions = (await db.execute(stmt)).scalars().all()
    return product, list(versions)


async def create_product(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: ProductCreate, actor_user_id: uuid.UUID
) -> Product:
    """Creates a Product together with its first ProductVersion, in one
    transaction -- a product with no versions can never be attached to a
    contract, so the two are never created separately."""
    product = Product(
        organization_id=organization_id,
        code=payload.code,
        energy_type=payload.energy_type,
        customer_type=payload.customer_type,
        status="ACTIVE",
    )
    db.add(product)
    await db.flush()

    version = ProductVersion(
        product_id=product.id,
        version_label=payload.version_label,
        name=payload.name,
        description=payload.description,
        base_price_cents=payload.base_price_cents,
        initial_fee_cents=payload.initial_fee_cents,
        recurring_fee_cents=payload.recurring_fee_cents,
        billing_period=payload.billing_period,
        valid_from=utcnow(),
        status="ACTIVE",
    )
    db.add(version)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.created", entity_type="product", entity_id=str(product.id),
        new_value={"code": payload.code, "name": payload.name},
    )
    await db.commit()
    await db.refresh(product)
    return product


async def add_product_version(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ProductVersionCreate,
    actor_user_id: uuid.UUID,
) -> ProductVersion | None:
    """A new version never mutates or removes the previous one -- existing
    contracts keep pointing at the product_version_id they were created with
    (see docs/business-rules.md), so old versions stay exactly as they were."""
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != organization_id:
        return None

    version = ProductVersion(
        product_id=product_id,
        version_label=payload.version_label,
        name=payload.name,
        description=payload.description,
        base_price_cents=payload.base_price_cents,
        initial_fee_cents=payload.initial_fee_cents,
        recurring_fee_cents=payload.recurring_fee_cents,
        billing_period=payload.billing_period,
        valid_from=utcnow(),
        status="ACTIVE",
    )
    db.add(version)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.version_added", entity_type="product", entity_id=str(product_id),
        new_value={"version_label": payload.version_label},
    )
    await db.commit()
    await db.refresh(version)
    return version


async def update_product_version(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: ProductVersionUpdate,
    actor_user_id: uuid.UUID,
) -> ProductVersion | None:
    """Updates pricing/status on an EXISTING, not-yet-superseded version. This is
    for fixing a mistake before anyone has contracted on it -- if a version is
    already in use by live contracts, prefer add_product_version() instead so
    those contracts' pricing never silently changes underneath them."""
    version = await db.get(ProductVersion, version_id)
    if version is None:
        return None
    product = await db.get(Product, version.product_id)
    if product is None or product.organization_id != organization_id:
        return None

    previous = {"status": version.status, "base_price_cents": version.base_price_cents}
    if payload.name is not None:
        version.name = payload.name
    if payload.description is not None:
        version.description = payload.description
    if payload.base_price_cents is not None:
        version.base_price_cents = payload.base_price_cents
    if payload.initial_fee_cents is not None:
        version.initial_fee_cents = payload.initial_fee_cents
    if payload.recurring_fee_cents is not None:
        version.recurring_fee_cents = payload.recurring_fee_cents
    if payload.status is not None:
        version.status = payload.status

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.version_updated", entity_type="product_version", entity_id=str(version_id),
        previous_value=previous,
        new_value={"status": version.status, "base_price_cents": version.base_price_cents},
    )
    await db.commit()
    await db.refresh(version)
    return version


async def update_product(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ProductUpdate,
    actor_user_id: uuid.UUID,
) -> Product | None:
    """Product-level status (e.g. discontinuing it entirely, ACTIVE -> RETIRED).
    Never touches pricing -- that's per-version, see update_product_version()."""
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != organization_id:
        return None

    previous = {"status": product.status}
    if payload.status is not None:
        product.status = payload.status

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.updated", entity_type="product", entity_id=str(product_id),
        previous_value=previous, new_value={"status": product.status},
    )
    await db.commit()
    await db.refresh(product)
    return product
