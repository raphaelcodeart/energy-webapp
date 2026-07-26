import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.storage import UploadValidationError, upload_media
from app.domains.catalog import service as catalog_service
from app.domains.catalog.schemas import (
    ProductCatalogRead,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ProductVersionCreate,
    ProductVersionRead,
    ProductVersionUpdate,
    ProductWithVersionsRead,
)

router = APIRouter(prefix="/products", tags=["catalog"])


@router.get("", response_model=list[ProductCatalogRead])
async def list_products(
    current_user: CurrentUser = Depends(require_permission("products.read")),
    db: AsyncSession = Depends(get_db),
) -> list[ProductCatalogRead]:
    """Returns every product paired with its current version's display fields
    (name/description/photo/price) -- both the admin catalog grid and the
    customer-facing marketplace read from this same endpoint; the customer app
    filters to status == ACTIVE client-side, admins see every status."""
    pairs = await catalog_service.list_products_with_current_version(
        db, organization_id=current_user.organization_id
    )
    return [
        ProductCatalogRead(
            **ProductRead.model_validate(product).model_dump(),
            current_version=ProductVersionRead.from_version(version) if version else None,
        )
        for product, version in pairs
    ]


@router.get("/{product_id}", response_model=ProductWithVersionsRead)
async def get_product(
    product_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("products.read")),
    db: AsyncSession = Depends(get_db),
) -> ProductWithVersionsRead:
    result = await catalog_service.get_product_with_versions(
        db, organization_id=current_user.organization_id, product_id=product_id
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    product, versions = result
    return ProductWithVersionsRead(
        **ProductRead.model_validate(product).model_dump(),
        versions=[ProductVersionRead.from_version(v) for v in versions],
    )


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    product = await catalog_service.update_product(
        db,
        organization_id=current_user.organization_id,
        product_id=product_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return ProductRead.model_validate(product)


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ProductRead:
    product = await catalog_service.create_product(
        db, organization_id=current_user.organization_id, payload=payload, actor_user_id=current_user.user_id
    )
    return ProductRead.model_validate(product)


@router.post(
    "/{product_id}/versions", response_model=ProductVersionRead, status_code=status.HTTP_201_CREATED
)
async def add_product_version(
    product_id: uuid.UUID,
    payload: ProductVersionCreate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ProductVersionRead:
    version = await catalog_service.add_product_version(
        db,
        organization_id=current_user.organization_id,
        product_id=product_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return ProductVersionRead.from_version(version)


@router.patch("/versions/{version_id}", response_model=ProductVersionRead)
async def update_product_version(
    version_id: uuid.UUID,
    payload: ProductVersionUpdate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ProductVersionRead:
    version = await catalog_service.update_product_version(
        db,
        organization_id=current_user.organization_id,
        version_id=version_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product version not found")
    return ProductVersionRead.from_version(version)


@router.post("/versions/{version_id}/photo", response_model=ProductVersionRead)
async def upload_product_version_photo(
    version_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ProductVersionRead:
    file_bytes = await file.read()
    try:
        photo_url = upload_media(
            file_bytes=file_bytes, content_type=file.content_type or "", key_prefix="photos/products"
        )
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    version = await catalog_service.update_product_version(
        db, organization_id=current_user.organization_id, version_id=version_id,
        payload=ProductVersionUpdate(image_url=photo_url), actor_user_id=current_user.user_id,
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product version not found")
    return ProductVersionRead.from_version(version)
