import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.domains.imported_products import service as imported_products_service
from app.domains.imported_products.models import IMPORT_PROVIDER_TYPES
from app.domains.imported_products.schemas import (
    CheckoutSessionRead,
    ImportedOrderCancelRequest,
    ImportedOrderCreditOtpRequest,
    ImportedOrderPaymentMethodUpdate,
    ImportedOrderQuoteRead,
    ImportedOrderRead,
    ImportedOrderSelfCreateRequest,
    ImportedProductAdminRead,
    ImportedProductCreate,
    ImportedProductRead,
    ImportedProductUpdate,
    ImportProviderCreate,
    ImportProviderRead,
    ImportProviderUpdate,
    PaymentProofUrlRead,
)
from app.domains.payments import service as payments_service
from app.domains.wallets import service as wallets_service

router = APIRouter(prefix="/imported-products", tags=["imported-products"])


def _error_to_http(exc: imported_products_service.ImportedProductsError) -> HTTPException:
    if isinstance(exc, (
        imported_products_service.ProductNotEligibleError, imported_products_service.InvalidCreditAmountError,
        imported_products_service.InvalidPaymentMethodError, imported_products_service.PaymentMethodNotAvailableError,
        imported_products_service.InvalidOtpError,
    )):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# --- Admin: providers ("bottone per inserire API KEY del dropshipping") ---

@router.get("/provider-types", response_model=list[str])
async def list_provider_types(
    current_user: CurrentUser = Depends(require_permission("imported_products.manage")),
) -> list[str]:
    return IMPORT_PROVIDER_TYPES


@router.get("/providers", response_model=list[ImportProviderRead])
async def list_providers(
    current_user: CurrentUser = Depends(require_permission("imported_products.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[ImportProviderRead]:
    providers = await imported_products_service.list_providers(db, organization_id=current_user.organization_id)
    return [ImportProviderRead(**imported_products_service.to_provider_read_dict(p)) for p in providers]


@router.post("/providers", response_model=ImportProviderRead, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: ImportProviderCreate,
    current_user: CurrentUser = Depends(require_permission("imported_products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ImportProviderRead:
    provider = await imported_products_service.create_provider(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        provider_type=payload.provider_type, name=payload.name, base_url=payload.base_url,
        api_key=payload.api_key, enabled=payload.enabled,
    )
    return ImportProviderRead(**imported_products_service.to_provider_read_dict(provider))


@router.patch("/providers/{provider_id}", response_model=ImportProviderRead)
async def update_provider(
    provider_id: uuid.UUID,
    payload: ImportProviderUpdate,
    current_user: CurrentUser = Depends(require_permission("imported_products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ImportProviderRead:
    provider = await imported_products_service.get_provider(
        db, organization_id=current_user.organization_id, provider_id=provider_id
    )
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    provider = await imported_products_service.update_provider(
        db, provider=provider, name=payload.name, base_url=payload.base_url, api_key=payload.api_key,
        enabled=payload.enabled, fields_set=payload.model_fields_set,
    )
    return ImportProviderRead(**imported_products_service.to_provider_read_dict(provider))


# --- Admin: catalog CRUD ---

@router.get("/products", response_model=list[ImportedProductAdminRead])
async def list_products_admin(
    current_user: CurrentUser = Depends(require_permission("imported_products.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[ImportedProductAdminRead]:
    products = await imported_products_service.list_imported_products(db, organization_id=current_user.organization_id)
    return [ImportedProductAdminRead(**(await imported_products_service.to_admin_product_read_dict(db, p))) for p in products]


@router.post("/products", response_model=ImportedProductAdminRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ImportedProductCreate,
    current_user: CurrentUser = Depends(require_permission("imported_products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ImportedProductAdminRead:
    try:
        product = await imported_products_service.create_imported_product(
            db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
            provider_id=payload.provider_id, external_id=payload.external_id, external_url=payload.external_url,
            name=payload.name, description=payload.description, image_url=payload.image_url,
            price_cents=payload.price_cents, credit_discount_percentage=payload.credit_discount_percentage,
            status=payload.status,
        )
    except imported_products_service.ProviderNotFoundError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ImportedProductAdminRead(**(await imported_products_service.to_admin_product_read_dict(db, product)))


@router.patch("/products/{product_id}", response_model=ImportedProductAdminRead)
async def update_product(
    product_id: uuid.UUID,
    payload: ImportedProductUpdate,
    current_user: CurrentUser = Depends(require_permission("imported_products.manage")),
    db: AsyncSession = Depends(get_db),
) -> ImportedProductAdminRead:
    product = await imported_products_service.get_imported_product(
        db, organization_id=current_user.organization_id, imported_product_id=product_id
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    updates = payload.model_dump(exclude_unset=True)
    product = await imported_products_service.update_imported_product(db, product=product, updates=updates)
    return ImportedProductAdminRead(**(await imported_products_service.to_admin_product_read_dict(db, product)))


# --- Customer-facing catalog ---

@router.get("/products/active", response_model=list[ImportedProductRead])
async def list_products_active(
    current_user: CurrentUser = Depends(require_permission("products.read")),
    db: AsyncSession = Depends(get_db),
) -> list[ImportedProductRead]:
    """Powers the Shop's "Acquisti LialEnergy" subcategory -- active only,
    and deliberately the trimmed customer-facing schema (see
    ImportedProductRead's docstring: no provider/external hints)."""
    products = await imported_products_service.list_imported_products(
        db, organization_id=current_user.organization_id, active_only=True
    )
    return [
        ImportedProductRead(
            id=p.id, name=p.name, description=p.description, image_url=p.image_url,
            price_cents=p.price_cents, credit_discount_percentage=p.credit_discount_percentage,
        )
        for p in products
    ]


# --- Orders: self-checkout ---

@router.get("/orders/quote/mine", response_model=ImportedOrderQuoteRead)
async def get_my_quote(
    imported_product_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportedOrderQuoteRead:
    try:
        quote = await imported_products_service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            imported_product_id=imported_product_id,
        )
    except imported_products_service.ProductNotEligibleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ImportedOrderQuoteRead(**quote)


@router.post(
    "/orders/mine/request-credit-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("imported-order-credit-otp", max_requests=5, window_seconds=300))],
)
async def request_my_credit_otp(
    payload: ImportedOrderCreditOtpRequest,
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    from app.domains.auth import service as auth_service
    from app.domains.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    try:
        quote = await imported_products_service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            imported_product_id=payload.imported_product_id,
        )
    except imported_products_service.ImportedProductsError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    context_line = (
        f"Stai per acquistare <strong>{quote['product_name']}</strong> "
        f"(ordine da {quote['amount_cents'] / 100:.2f} &euro;) e utilizzare "
        f"<strong>{payload.credit_applied_cents / 100:.2f} LialCash</strong> dal tuo wallet "
        "per pagarne una parte. Usa questo codice per confermare l'operazione."
    )
    await auth_service.request_otp(
        db, user=user, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, context_line=context_line,
    )
    return {"ok": True}


@router.post("/orders/mine", response_model=ImportedOrderRead, status_code=status.HTTP_201_CREATED)
async def create_my_order(
    payload: ImportedOrderSelfCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportedOrderRead:
    try:
        order = await imported_products_service.create_order(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            imported_product_id=payload.imported_product_id, credit_applied_cents=payload.credit_applied_cents,
            actor_user_id=current_user.user_id, payment_method=payload.payment_method, note=payload.note,
            otp_code=payload.otp_code,
        )
    except imported_products_service.ImportedProductsError as exc:
        raise _error_to_http(exc) from exc
    except wallets_service.InsufficientBalanceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ImportedOrderRead(**(await imported_products_service.to_read_dict(db, order)))


@router.get("/orders/mine", response_model=list[ImportedOrderRead])
async def list_my_orders(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ImportedOrderRead]:
    orders = await imported_products_service.list_orders_for_customer(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )
    return [ImportedOrderRead(**d) for d in await imported_products_service.hydrate(db, orders)]


@router.post("/orders/mine/{order_id}/checkout-session", response_model=CheckoutSessionRead)
async def create_my_checkout_session(
    order_id: uuid.UUID,
    success_url: str,
    cancel_url: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionRead:
    order = await imported_products_service.get_org_scoped(
        db, organization_id=current_user.organization_id, order_id=order_id
    )
    if order is None or order.customer_user_id != current_user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot pay an order in status {order.status}")
    try:
        checkout_url = await payments_service.create_checkout_session_for_imported_order(
            db, organization_id=current_user.organization_id, order=order,
            success_url=success_url, cancel_url=cancel_url,
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CheckoutSessionRead(checkout_url=checkout_url)


@router.patch("/orders/mine/{order_id}/payment-method", response_model=ImportedOrderRead)
async def change_my_payment_method(
    order_id: uuid.UUID,
    payload: ImportedOrderPaymentMethodUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportedOrderRead:
    order = await imported_products_service.get_owned(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, order_id=order_id
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    try:
        order = await imported_products_service.change_payment_method(
            db, organization_id=current_user.organization_id, order=order,
            new_payment_method=payload.payment_method,
        )
    except (imported_products_service.InvalidOrderStateError, imported_products_service.InvalidPaymentMethodError,
            imported_products_service.PaymentMethodNotAvailableError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ImportedOrderRead(**(await imported_products_service.to_read_dict(db, order)))


@router.post(
    "/orders/mine/{order_id}/payment-proof",
    response_model=ImportedOrderRead,
    dependencies=[Depends(rate_limit("imported-payment-proof-upload", max_requests=20, window_seconds=300))],
)
async def upload_my_payment_proof(
    order_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportedOrderRead:
    order = await imported_products_service.get_owned(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, order_id=order_id
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    file_bytes = await file.read()
    try:
        order = await imported_products_service.upload_payment_proof(
            db, organization_id=current_user.organization_id, order=order,
            file_bytes=file_bytes, content_type=file.content_type or "",
            original_filename=file.filename or "prova-pagamento", actor_user_id=current_user.user_id,
        )
    except imported_products_service.PaymentProofError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ImportedOrderRead(**(await imported_products_service.to_read_dict(db, order)))


@router.get("/orders/mine/{order_id}/payment-proof-url", response_model=PaymentProofUrlRead)
async def get_my_payment_proof_url(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentProofUrlRead:
    order = await imported_products_service.get_owned(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, order_id=order_id
    )
    if order is None or order.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment proof not found")
    return PaymentProofUrlRead(url=imported_products_service.presigned_payment_proof_url(order))


# --- Orders: admin ---

@router.get("/orders", response_model=list[ImportedOrderRead])
async def list_orders(
    status_filter: str | None = None,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[ImportedOrderRead]:
    orders = await imported_products_service.list_orders(
        db, organization_id=current_user.organization_id, status_filter=status_filter
    )
    return [ImportedOrderRead(**d) for d in await imported_products_service.hydrate(db, orders)]


@router.post("/orders/{order_id}/confirm-payment", response_model=ImportedOrderRead)
async def confirm_order_payment(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> ImportedOrderRead:
    try:
        order = await imported_products_service.confirm_payment(
            db, organization_id=current_user.organization_id, order_id=order_id, actor_user_id=current_user.user_id
        )
    except imported_products_service.InvalidOrderStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except imported_products_service.ImportedProductsError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ImportedOrderRead(**(await imported_products_service.to_read_dict(db, order)))


@router.post("/orders/{order_id}/cancel", response_model=ImportedOrderRead)
async def cancel_order(
    order_id: uuid.UUID,
    payload: ImportedOrderCancelRequest,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> ImportedOrderRead:
    try:
        order = await imported_products_service.cancel_order(
            db, organization_id=current_user.organization_id, order_id=order_id, reason=payload.reason,
            actor_user_id=current_user.user_id,
        )
    except imported_products_service.InvalidOrderStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except imported_products_service.ImportedProductsError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ImportedOrderRead(**(await imported_products_service.to_read_dict(db, order)))


@router.get("/orders/{order_id}/payment-proof-url", response_model=PaymentProofUrlRead)
async def get_order_payment_proof_url(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> PaymentProofUrlRead:
    order = await imported_products_service.get_org_scoped(
        db, organization_id=current_user.organization_id, order_id=order_id
    )
    if order is None or order.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment proof not found")
    return PaymentProofUrlRead(url=imported_products_service.presigned_payment_proof_url(order))
