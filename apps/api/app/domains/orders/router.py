import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.orders import service as orders_service
from app.domains.orders.schemas import (
    OrderCancelRequest,
    OrderCreateRequest,
    OrderQuoteRead,
    OrderRead,
)
from app.domains.wallets import service as wallets_service

router = APIRouter(prefix="/orders", tags=["orders"])

# Admin-only for now (no self-checkout yet -- see
# docs/cashback-partner-invoices-plan.md), gated at the same sensitivity
# tier as the rest of the wallet-adjacent surface (wallet.manage:
# SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN, deliberately not
# BACK_OFFICE_OPERATOR/SALES_MANAGER) since creating an order can debit a
# customer's wallet.


@router.get("/quote", response_model=OrderQuoteRead)
async def get_order_quote(
    customer_user_id: uuid.UUID,
    product_version_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> OrderQuoteRead:
    """Lets the checkout screen show the credit cap and the customer's
    balance BEFORE an order is created, so the admin can decide how much
    credit to apply with real numbers in front of them."""
    try:
        quote = await orders_service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=customer_user_id,
            product_version_id=product_version_id,
        )
    except orders_service.ProductNotEligibleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return OrderQuoteRead(**quote)


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreateRequest,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    try:
        order = await orders_service.create_order(
            db, organization_id=current_user.organization_id, customer_user_id=payload.customer_user_id,
            product_version_id=payload.product_version_id, credit_applied_cents=payload.credit_applied_cents,
            actor_user_id=current_user.user_id, note=payload.note,
        )
    except orders_service.ProductNotEligibleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except orders_service.InvalidCreditAmountError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except wallets_service.InsufficientBalanceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return OrderRead(**(await orders_service.to_read_dict(db, order)))


@router.get("", response_model=list[OrderRead])
async def list_orders(
    status_filter: str | None = None,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[OrderRead]:
    orders = await orders_service.list_orders(
        db, organization_id=current_user.organization_id, status_filter=status_filter
    )
    return [OrderRead(**d) for d in await orders_service.hydrate(db, orders)]


@router.post("/{order_id}/confirm-payment", response_model=OrderRead)
async def confirm_order_payment(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    try:
        order = await orders_service.confirm_payment(
            db, organization_id=current_user.organization_id, order_id=order_id, actor_user_id=current_user.user_id
        )
    except orders_service.InvalidOrderStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except orders_service.OrderError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return OrderRead(**(await orders_service.to_read_dict(db, order)))


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(
    order_id: uuid.UUID,
    payload: OrderCancelRequest,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    try:
        order = await orders_service.cancel_order(
            db, organization_id=current_user.organization_id, order_id=order_id, reason=payload.reason,
            actor_user_id=current_user.user_id,
        )
    except orders_service.InvalidOrderStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except orders_service.OrderError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return OrderRead(**(await orders_service.to_read_dict(db, order)))
