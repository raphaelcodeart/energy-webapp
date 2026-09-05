import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.catalog.models import Product, ProductVersion
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.orders.models import ORDER_PAYMENT_METHODS, Order
from app.domains.organizations import service as organizations_service
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service


class OrderError(Exception):
    pass


class ProductNotEligibleError(OrderError):
    pass


class InvalidCreditAmountError(OrderError):
    pass


class InvalidOrderStateError(OrderError):
    pass


class InvalidPaymentMethodError(OrderError):
    pass


class PaymentMethodNotAvailableError(OrderError):
    pass


async def _get_sellable_product_version(
    db: AsyncSession, *, organization_id: uuid.UUID, product_version_id: uuid.UUID
) -> tuple[ProductVersion, Product]:
    version = await db.get(ProductVersion, product_version_id)
    if version is None:
        raise ProductNotEligibleError("Product version not found")
    product = await db.get(Product, version.product_id)
    if product is None or product.organization_id != organization_id:
        raise ProductNotEligibleError("Product version not found")
    if product.category == "INTERNAL":
        raise ProductNotEligibleError(
            "I prodotti Interno Lial Energy si acquistano come contratto, non come ordine -- vedi POST /contracts."
        )
    return version, product


def max_creditable_cents(*, amount_cents: int, credit_discount_percentage: int) -> int:
    return round(amount_cents * credit_discount_percentage / 100)


async def get_available_payment_methods(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    """Gates what a checkout screen may even offer for the residual --
    both create_order() (server-side enforcement) and every quote endpoint
    (so the UI never shows a button that would just fail) read this."""
    return {
        "bank_transfer": await organizations_service.is_bank_transfer_configured(db, organization_id=organization_id),
        "card": await organizations_service.is_stripe_configured(db, organization_id=organization_id),
    }


async def get_quote(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, product_version_id: uuid.UUID
) -> dict:
    version, _product = await _get_sellable_product_version(
        db, organization_id=organization_id, product_version_id=product_version_id
    )
    wallet = await wallets_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=customer_user_id
    )
    methods = await get_available_payment_methods(db, organization_id=organization_id)
    return {
        "product_version_id": version.id,
        "product_name": version.name,
        "amount_cents": version.base_price_cents,
        "credit_discount_percentage": version.credit_discount_percentage,
        "max_creditable_cents": max_creditable_cents(
            amount_cents=version.base_price_cents, credit_discount_percentage=version.credit_discount_percentage
        ),
        "customer_wallet_balance_cents": wallet.balance_cents if wallet else 0,
        "bank_transfer_available": methods["bank_transfer"],
        "card_available": methods["card"],
    }


async def _resolve_display_name(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Same lookup order as invoice_redemptions/service.py's copy of this --
    duplicated for the same reason (a private, wallets-domain-local batch
    helper isn't meant to be imported across domains)."""
    agent = (
        await db.execute(
            select(AgentProfile.display_name).where(
                AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if agent:
        return agent

    customer = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if customer is not None:
        profile = await db.get(CustomerProfile, customer.id)
        company = await db.get(Company, customer.id)
        name = display_name_for(customer.kind, profile, company)
        if name != "—":
            return name

    user = await db.get(User, user_id)
    return user.email if user else "—"


async def to_read_dict(db: AsyncSession, order: Order) -> dict:
    version = await db.get(ProductVersion, order.product_version_id)
    customer_name = await _resolve_display_name(
        db, organization_id=order.organization_id, user_id=order.customer_user_id
    )
    return {
        "id": order.id,
        "customer_user_id": order.customer_user_id,
        "customer_display_name": customer_name,
        "product_version_id": order.product_version_id,
        "product_name": version.name if version else "—",
        "created_by_user_id": order.created_by_user_id,
        "amount_cents": order.amount_cents,
        "credit_applied_cents": order.credit_applied_cents,
        "residual_amount_cents": order.amount_cents - order.credit_applied_cents,
        "status": order.status,
        "payment_method": order.payment_method,
        "note": order.note,
        "paid_at": order.paid_at,
        "cancelled_at": order.cancelled_at,
        "cancellation_reason": order.cancellation_reason,
        "created_at": order.created_at,
    }


async def hydrate(db: AsyncSession, orders: list[Order]) -> list[dict]:
    return [await to_read_dict(db, o) for o in orders]


async def create_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    product_version_id: uuid.UUID,
    credit_applied_cents: int,
    actor_user_id: uuid.UUID,
    payment_method: str = "BANK_TRANSFER",
    note: str | None = None,
) -> Order:
    version, _product = await _get_sellable_product_version(
        db, organization_id=organization_id, product_version_id=product_version_id
    )
    amount_cents = version.base_price_cents
    cap = max_creditable_cents(amount_cents=amount_cents, credit_discount_percentage=version.credit_discount_percentage)
    if credit_applied_cents < 0 or credit_applied_cents > cap:
        raise InvalidCreditAmountError(
            f"credit_applied_cents must be between 0 and {cap} for this product ({version.credit_discount_percentage}% of {amount_cents})"
        )

    # Only matters when something is actually going to be charged -- if
    # credit alone covers the price, payment_method is stored as-given but
    # never acted upon (the order skips straight to PAID below), so an
    # unavailable/garbage value there shouldn't block a 100%-credit order.
    residual = amount_cents - credit_applied_cents
    if residual > 0:
        if payment_method not in ORDER_PAYMENT_METHODS:
            raise InvalidPaymentMethodError(f"payment_method must be one of {ORDER_PAYMENT_METHODS}")
        available = await get_available_payment_methods(db, organization_id=organization_id)
        if payment_method == "BANK_TRANSFER" and not available["bank_transfer"]:
            raise PaymentMethodNotAvailableError("Il pagamento con bonifico non è configurato.")
        if payment_method == "CARD" and not available["card"]:
            raise PaymentMethodNotAvailableError("Il pagamento con carta non è configurato.")

    wallet = None
    if credit_applied_cents > 0:
        # Checked BEFORE the order row is ever created, not just left to the
        # atomic debit's own CAS guard below -- creating the order first and
        # rolling back on a failed debit would work too, but an explicit
        # rollback() here would conflict with the SAVEPOINT-based session
        # wrapping the test suite's `db` fixture uses (same reasoning as the
        # identical-in-spirit comment on debit_and_transfer's insufficient-
        # balance path). This pre-check can't catch a same-instant race with
        # another debit against the same wallet -- that rarer case is still
        # caught correctly by the CAS in debit_wallet_for_purchase, just
        # without this function's own guarantee that no Order row survives
        # it; an accepted, documented trade-off, not a bug.
        wallet = await wallets_service.get_or_create_wallet(
            db, organization_id=organization_id, user_id=customer_user_id
        )
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Insufficient balance")

    order = Order(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        product_version_id=product_version_id,
        created_by_user_id=actor_user_id,
        amount_cents=amount_cents,
        credit_applied_cents=credit_applied_cents,
        status="AWAITING_PAYMENT",
        payment_method=payment_method,
        note=note,
    )
    db.add(order)
    await db.flush()  # assigns order.id, no commit yet

    if credit_applied_cents > 0:
        assert wallet is not None
        if residual == 0:
            order.status = "PAID"
            order.paid_by_user_id = actor_user_id
            order.paid_at = utcnow()
        # debit_wallet_for_purchase() commits -- this single commit captures
        # the order row (including the PAID transition above, if any) AND
        # the debit transaction together, atomically.
        debit_txn = await wallets_service.debit_wallet_for_purchase(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=credit_applied_cents,
            reference_order_id=order.id, actor_user_id=actor_user_id,
            note=f"Ordine {version.name}", idempotency_key=f"order:{order.id}:credit",
        )
        order.credit_debit_transaction_id = debit_txn.id
        await db.commit()
        await db.refresh(order)
    else:
        await db.commit()
        await db.refresh(order)
    return order


async def get_org_scoped(db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID) -> Order | None:
    order = await db.get(Order, order_id)
    if order is None or order.organization_id != organization_id:
        return None
    return order


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, status_filter: str | None = None
) -> list[Order]:
    stmt = select(Order).where(Order.organization_id == organization_id)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    stmt = stmt.order_by(Order.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def list_orders_for_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID
) -> list[Order]:
    stmt = (
        select(Order)
        .where(Order.organization_id == organization_id, Order.customer_user_id == customer_user_id)
        .order_by(Order.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> Order:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise OrderError("Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot confirm payment for an order in status {order.status}")

    order.status = "PAID"
    order.paid_by_user_id = actor_user_id
    order.paid_at = utcnow()

    version = await db.get(ProductVersion, order.product_version_id)
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="order", entity_id=order.id,
        title=f"Il tuo ordine per {version.name if version else 'un prodotto'} è confermato",
        body=None,
    )
    await db.commit()
    await db.refresh(order)
    return order


async def cancel_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> Order:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise OrderError("Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot cancel an order in status {order.status}")

    if order.credit_debit_transaction_id is not None:
        # Reverses the exact PURCHASE_DEBIT row -- see
        # wallets/service.py::reverse_transaction's PURCHASE_DEBIT handling.
        await wallets_service.reverse_transaction(
            db, organization_id=organization_id, transaction_id=order.credit_debit_transaction_id,
            actor_user_id=actor_user_id, reason=f"Ordine annullato: {reason}",
            idempotency_key=f"order:{order.id}:cancel-refund",
        )

    order.status = "CANCELLED"
    order.cancelled_by_user_id = actor_user_id
    order.cancelled_at = utcnow()
    order.cancellation_reason = reason
    await db.commit()
    await db.refresh(order)
    return order


async def attach_stripe_checkout_session(db: AsyncSession, *, order: Order, session_id: str) -> Order:
    """Records which Stripe Checkout Session is currently "live" for this
    order's residual -- overwrites any previous session id rather than
    appending, so only the customer's latest checkout attempt is ever
    honored by the webhook (see payments/service.py). Does not change
    order.status: the order stays AWAITING_PAYMENT until Stripe confirms
    payment via the webhook, exactly like a bank transfer stays
    AWAITING_PAYMENT until an admin confirms it."""
    order.payment_method = "CARD"
    order.stripe_checkout_session_id = session_id
    await db.commit()
    await db.refresh(order)
    return order


async def mark_paid_via_stripe(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str
) -> Order:
    """Called only from the Stripe webhook (payments/router.py) once
    checkout.session.completed fires -- the one case in this whole domain
    where `PAID` is reached with no human actor, mirroring how
    reference_invoice_redemption_id credits also have actor_user_id set to
    whichever admin confirmed them, except here there IS no admin: paid_by_
    user_id stays NULL, same as an ADMIN_CREDIT's actor_user_id can be NULL
    for a system-originated row."""
    stmt = select(Order).where(
        Order.organization_id == organization_id, Order.stripe_checkout_session_id == stripe_checkout_session_id
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise OrderError("Order not found for this Stripe checkout session")
    if order.status != "AWAITING_PAYMENT":
        # Stripe can and does retry webhook delivery -- a second delivery
        # for an already-PAID order is expected, not an error; no-op.
        return order

    order.status = "PAID"
    order.paid_at = utcnow()

    version = await db.get(ProductVersion, order.product_version_id)
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="order", entity_id=order.id,
        title=f"Il tuo ordine per {version.name if version else 'un prodotto'} è confermato",
        body="Pagamento con carta ricevuto.",
    )
    await db.commit()
    await db.refresh(order)
    return order
