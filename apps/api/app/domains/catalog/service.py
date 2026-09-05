import uuid

from sqlalchemy import delete, func, select, update
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
from app.domains.contracts.models import Contract


class ProductDeletionError(Exception):
    """Raised when a product can't be deleted -- see delete_product()."""


def _clamp_credit_discount(category: str, requested: int) -> int:
    """An INTERNAL product (Lial's own supply) is never discountable in wallet
    credits, no matter what the caller asks for -- this is the single place
    that invariant is enforced, so it can never drift out of sync between
    create/add-version/update-version call sites."""
    return requested if category != "INTERNAL" else 0


async def list_products(db: AsyncSession, *, organization_id: uuid.UUID) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.organization_id == organization_id)
        .order_by(Product.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_products_with_current_version(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[tuple[Product, ProductVersion | None]]:
    """Each product paired with its most recent version (by valid_from) -- the
    catalog grid (admin) and the marketplace (customer) both render name/photo/
    price from this without a per-product detail round-trip."""
    products = await list_products(db, organization_id=organization_id)
    if not products:
        return []

    product_ids = [p.id for p in products]
    versions_stmt = (
        select(ProductVersion)
        .where(ProductVersion.product_id.in_(product_ids))
        .order_by(ProductVersion.product_id, ProductVersion.valid_from.desc())
    )
    versions = (await db.execute(versions_stmt)).scalars().all()

    latest_by_product: dict[uuid.UUID, ProductVersion] = {}
    for version in versions:
        if version.product_id not in latest_by_product:
            latest_by_product[version.product_id] = version

    return [(product, latest_by_product.get(product.id)) for product in products]


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
        product_type=payload.product_type,
        energy_type=payload.energy_type,
        customer_type=payload.customer_type,
        category=payload.category,
        status="ACTIVE",
    )
    db.add(product)
    await db.flush()

    version = ProductVersion(
        product_id=product.id,
        version_label=payload.version_label,
        name=payload.name,
        description=payload.description,
        image_url=payload.image_url,
        base_price_cents=payload.base_price_cents,
        initial_fee_cents=payload.initial_fee_cents,
        recurring_fee_cents=payload.recurring_fee_cents,
        billing_period=payload.billing_period,
        tax_configuration={"vat_percentage": payload.vat_percentage} if payload.vat_percentage is not None else {},
        contract_duration_months=payload.contract_duration_months,
        commission_tokens=payload.commission_tokens,
        credit_discount_percentage=_clamp_credit_discount(payload.category, payload.credit_discount_percentage),
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
        image_url=payload.image_url,
        base_price_cents=payload.base_price_cents,
        initial_fee_cents=payload.initial_fee_cents,
        recurring_fee_cents=payload.recurring_fee_cents,
        billing_period=payload.billing_period,
        tax_configuration={"vat_percentage": payload.vat_percentage} if payload.vat_percentage is not None else {},
        contract_duration_months=payload.contract_duration_months,
        commission_tokens=payload.commission_tokens,
        credit_discount_percentage=_clamp_credit_discount(product.category, payload.credit_discount_percentage),
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
    if payload.image_url is not None:
        version.image_url = payload.image_url
    if payload.base_price_cents is not None:
        version.base_price_cents = payload.base_price_cents
    if payload.initial_fee_cents is not None:
        version.initial_fee_cents = payload.initial_fee_cents
    if payload.recurring_fee_cents is not None:
        version.recurring_fee_cents = payload.recurring_fee_cents
    if payload.vat_percentage is not None:
        version.tax_configuration = {**(version.tax_configuration or {}), "vat_percentage": payload.vat_percentage}
    if payload.contract_duration_months is not None:
        version.contract_duration_months = payload.contract_duration_months
    if payload.commission_tokens is not None:
        version.commission_tokens = payload.commission_tokens
    if payload.credit_discount_percentage is not None:
        version.credit_discount_percentage = _clamp_credit_discount(product.category, payload.credit_discount_percentage)
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


async def delete_product(
    db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID, actor_user_id: uuid.UUID
) -> bool | None:
    """Hard-deletes a product and every one of its versions. Returns None if the
    product doesn't exist in this org (-> router 404), raises
    ProductDeletionError if any version has ever been sold (-> router 400) --
    a contract's product_version_id must keep pointing at real pricing/token
    data forever, so a product with sales history can only be status=RETIRED
    via update_product(), never deleted."""
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != organization_id:
        return None

    version_ids_stmt = select(ProductVersion.id).where(ProductVersion.product_id == product_id)
    version_ids = list((await db.execute(version_ids_stmt)).scalars().all())

    if version_ids:
        contract_count = (
            await db.execute(select(func.count()).select_from(Contract).where(Contract.product_version_id.in_(version_ids)))
        ).scalar_one()
        if contract_count > 0:
            raise ProductDeletionError(
                "Impossibile eliminare: questo prodotto ha contratti associati. Puoi solo disattivarlo."
            )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.deleted", entity_type="product", entity_id=str(product_id),
        previous_value={"code": product.code, "status": product.status},
    )
    await db.execute(delete(ProductVersion).where(ProductVersion.product_id == product_id))
    await db.delete(product)
    await db.commit()
    return True


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
    if payload.product_type is not None:
        product.product_type = payload.product_type
    if payload.energy_type is not None:
        product.energy_type = payload.energy_type
    if payload.category is not None:
        product.category = payload.category
        if payload.category == "INTERNAL":
            # Switching back to INTERNAL must not leave a stale nonzero
            # discount sitting on any version -- see _clamp_credit_discount.
            await db.execute(
                update(ProductVersion)
                .where(ProductVersion.product_id == product_id)
                .values(credit_discount_percentage=0)
            )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="product.updated", entity_type="product", entity_id=str(product_id),
        previous_value=previous, new_value={"status": product.status},
    )
    await db.commit()
    await db.refresh(product)
    return product
