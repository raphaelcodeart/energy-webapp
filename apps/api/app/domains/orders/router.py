import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.domains.orders import service as orders_service
from app.domains.orders.schemas import (
    CheckoutSessionRead,
    OrderCancelRequest,
    OrderCreateRequest,
    OrderCreditOtpRequest,
    OrderPaymentMethodUpdate,
    OrderQuoteRead,
    OrderRead,
    OrderSelfCreateRequest,
    PaymentProofUrlRead,
)
from app.domains.payments import service as payments_service
from app.domains.wallets import service as wallets_service

router = APIRouter(prefix="/orders", tags=["orders"])

# Two ways in: an admin creating/managing any order (wallet.manage-gated --
# same sensitivity tier as the rest of the wallet-adjacent surface, since
# this can debit a customer's wallet) and self-checkout (added Session 26,
# "/mine" routes) where a customer only ever touches their own wallet/orders,
# the same authorization principle as POST /wallets/transfer.


def _order_error_to_http(exc: orders_service.OrderError) -> HTTPException:
    if isinstance(exc, (orders_service.ProductNotEligibleError, orders_service.InvalidCreditAmountError,
                         orders_service.InvalidPaymentMethodError, orders_service.PaymentMethodNotAvailableError,
                         orders_service.CashbackNotAvailableError, orders_service.InvalidOtpError)):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


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


@router.get("/quote/mine", response_model=OrderQuoteRead)
async def get_my_order_quote(
    product_version_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderQuoteRead:
    """Self-service version of the quote above -- any authenticated user can
    see their OWN wallet balance and this product's cap/payment-method
    availability, no permission beyond authentication (mirrors
    GET /wallets/me)."""
    try:
        quote = await orders_service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
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
            actor_user_id=current_user.user_id, payment_method=payload.payment_method, note=payload.note,
            cashback_requested=payload.cashback_requested,
            # An admin applying a customer's own credit on their behalf is
            # already a permissioned, audited action -- no OTP (which would
            # go to the CUSTOMER's inbox, not this admin's) is required or
            # even possible to check here. See create_order's docstring.
            require_otp_for_credit_spend=False,
        )
    except orders_service.OrderError as exc:
        raise _order_error_to_http(exc) from exc
    except wallets_service.InsufficientBalanceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return OrderRead(**(await orders_service.to_read_dict(db, order)))


@router.post(
    "/mine/request-credit-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("order-credit-otp", max_requests=5, window_seconds=300))],
)
async def request_my_order_credit_otp(
    payload: OrderCreditOtpRequest,
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """Emails the OTP code POST /orders/mine must be given (via otp_code)
    whenever it spends existing wallet LialCash (credit_applied_cents > 0)
    -- see auth/service.py::request_otp and
    orders/service.py::create_order. Same "prove you still control the
    inbox before this sensitive self-service action goes through" pattern
    as POST /agents/apply/request-otp.

    product_version_id/credit_applied_cents are used only to look up the
    product's real name and price server-side (never a client-supplied
    display string) so the emailed code clearly states what it's
    confirming -- product, order value, LialCash amount -- per the user's
    explicit request that this email never be generic."""
    from app.domains.auth import service as auth_service
    from app.domains.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    try:
        quote = await orders_service.get_quote(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            product_version_id=payload.product_version_id,
        )
    except orders_service.OrderError as exc:
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


@router.post("/mine", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_my_order(
    payload: OrderSelfCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    """Self-checkout: customer_user_id is always the caller's own id, never
    taken from the request body -- same rule as POST /wallets/transfer's
    from_wallet_id. No permission beyond authentication: a customer can only
    ever spend their own wallet credit and create an order in their own
    name. Spending any wallet LialCash here also requires a fresh OTP (see
    POST /mine/request-credit-otp above) -- enforced inside create_order,
    not here, so it can never be bypassed by a caller that skips this
    specific router function."""
    try:
        order = await orders_service.create_order(
            db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id,
            product_version_id=payload.product_version_id, credit_applied_cents=payload.credit_applied_cents,
            actor_user_id=current_user.user_id, payment_method=payload.payment_method, note=payload.note,
            cashback_requested=payload.cashback_requested, otp_code=payload.otp_code,
        )
    except orders_service.OrderError as exc:
        raise _order_error_to_http(exc) from exc
    except wallets_service.InsufficientBalanceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return OrderRead(**(await orders_service.to_read_dict(db, order)))


@router.get("/mine", response_model=list[OrderRead])
async def list_my_orders(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[OrderRead]:
    orders = await orders_service.list_orders_for_customer(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id
    )
    return [OrderRead(**d) for d in await orders_service.hydrate(db, orders)]


@router.post("/mine/{order_id}/checkout-session", response_model=CheckoutSessionRead)
async def create_my_order_checkout_session(
    order_id: uuid.UUID,
    success_url: str,
    cancel_url: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionRead:
    """Only the order's own customer may request a checkout session for it
    -- 404 (not 403) for someone else's order, same information-hiding
    reasoning as the rest of this codebase's ownership checks."""
    order = await orders_service.get_org_scoped(db, organization_id=current_user.organization_id, order_id=order_id)
    if order is None or order.customer_user_id != current_user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot pay an order in status {order.status}")
    try:
        checkout_url = await payments_service.create_checkout_session_for_order(
            db, organization_id=current_user.organization_id, order=order,
            success_url=success_url, cancel_url=cancel_url,
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return CheckoutSessionRead(checkout_url=checkout_url)


@router.patch("/mine/{order_id}/payment-method", response_model=OrderRead)
async def change_my_order_payment_method(
    order_id: uuid.UUID,
    payload: OrderPaymentMethodUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    """"Paga con carta invece" / "Paga con bonifico invece" on an order the
    customer already placed -- only their own, only while still
    AWAITING_PAYMENT (see orders/service.py::change_payment_method)."""
    order = await orders_service.get_owned(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, order_id=order_id
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    try:
        order = await orders_service.change_payment_method(
            db, organization_id=current_user.organization_id, order=order,
            new_payment_method=payload.payment_method,
        )
    except (orders_service.InvalidOrderStateError, orders_service.InvalidPaymentMethodError,
            orders_service.PaymentMethodNotAvailableError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return OrderRead(**(await orders_service.to_read_dict(db, order)))


@router.post(
    "/mine/{order_id}/payment-proof",
    response_model=OrderRead,
    dependencies=[Depends(rate_limit("payment-proof-upload", max_requests=20, window_seconds=300))],
)
async def upload_my_order_payment_proof(
    order_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    """Customer attaches a photo/PDF of the bank transfer receipt -- extra
    evidence for the admin, never a payment confirmation by itself (see
    orders/service.py::upload_payment_proof's docstring)."""
    order = await orders_service.get_owned(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, order_id=order_id
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    file_bytes = await file.read()
    try:
        order = await orders_service.upload_payment_proof(
            db, organization_id=current_user.organization_id, order=order,
            file_bytes=file_bytes, content_type=file.content_type or "",
            original_filename=file.filename or "prova-pagamento", actor_user_id=current_user.user_id,
        )
    except orders_service.PaymentProofError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return OrderRead(**(await orders_service.to_read_dict(db, order)))


@router.get("/mine/{order_id}/payment-proof-url", response_model=PaymentProofUrlRead)
async def get_my_order_payment_proof_url(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentProofUrlRead:
    order = await orders_service.get_owned(
        db, organization_id=current_user.organization_id, customer_user_id=current_user.user_id, order_id=order_id
    )
    if order is None or order.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment proof not found")
    return PaymentProofUrlRead(url=orders_service.presigned_payment_proof_url(order))


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


@router.get("/{order_id}/payment-proof-url", response_model=PaymentProofUrlRead)
async def get_order_payment_proof_url(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> PaymentProofUrlRead:
    order = await orders_service.get_org_scoped(db, organization_id=current_user.organization_id, order_id=order_id)
    if order is None or order.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment proof not found")
    return PaymentProofUrlRead(url=orders_service.presigned_payment_proof_url(order))
