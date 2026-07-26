import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.customers import service as customer_service
from app.domains.customers.schemas import (
    CustomerCreate,
    CustomerDetailRead,
    CustomerRead,
    CustomerUpdate,
    SupplyPointCreate,
    SupplyPointRead,
    SupplyPointUpdate,
)

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerRead])
async def list_customers(
    current_user: CurrentUser = Depends(require_permission("customers.read")),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerRead]:
    rows = await customer_service.list_customers(db, organization_id=current_user.organization_id)
    return [CustomerRead(**row) for row in rows]


@router.get("/{customer_id}", response_model=CustomerDetailRead)
async def get_customer(
    customer_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("customers.read")),
    db: AsyncSession = Depends(get_db),
) -> CustomerDetailRead:
    row = await customer_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer_id
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return CustomerDetailRead(**row)


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    current_user: CurrentUser = Depends(require_permission("customers.create")),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    try:
        customer = await customer_service.create_customer(
            db, organization_id=current_user.organization_id, payload=payload, actor_user_id=current_user.user_id
        )
    except customer_service.CustomerValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    row = await customer_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer.id
    )
    return CustomerRead(**row)


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    customer = await customer_service.update_customer(
        db,
        organization_id=current_user.organization_id,
        customer_id=customer_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    row = await customer_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer_id
    )
    return CustomerRead(**row)


@router.post("/{customer_id}/supply-points", response_model=SupplyPointRead, status_code=status.HTTP_201_CREATED)
async def add_supply_point(
    customer_id: uuid.UUID,
    payload: SupplyPointCreate,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> SupplyPointRead:
    supply_point = await customer_service.add_supply_point(
        db,
        organization_id=current_user.organization_id,
        customer_id=customer_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if supply_point is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return SupplyPointRead.model_validate(supply_point)


@router.patch("/supply-points/{supply_point_id}", response_model=SupplyPointRead)
async def update_supply_point(
    supply_point_id: uuid.UUID,
    payload: SupplyPointUpdate,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> SupplyPointRead:
    supply_point = await customer_service.update_supply_point(
        db,
        organization_id=current_user.organization_id,
        supply_point_id=supply_point_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if supply_point is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supply point not found")
    return SupplyPointRead.model_validate(supply_point)
