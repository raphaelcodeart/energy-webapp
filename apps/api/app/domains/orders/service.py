import logging
import uuid

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.email import EmailNotConfiguredError, send_html_email
from app.core.email_templates import render_email
from app.domains.catalog.models import Product, ProductVersion
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.orders.models import ORDER_PAYMENT_METHODS, Order
from app.domains.organizations import service as organizations_service
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service

logger = logging.getLogger(__name__)


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


class PaymentProofError(OrderError):
    """Covers both a bad file (unsupported type / too large) and uploading a
    proof to an order it doesn't apply to (not BANK_TRANSFER, or no longer
    AWAITING_PAYMENT)."""


class CashbackNotAvailableError(OrderError):
    """Raised when cashback_requested=True but either the product doesn't
    offer it (ProductVersion.cashback_enabled is False) or there's no real
    new payment for it to apply to (the wallet credit already covers the
    whole price)."""


class InvalidOtpError(OrderError):
    """Raised when self-checkout spends existing wallet LialCash
    (credit_applied_cents > 0) without a valid, still-fresh OTP code -- see
    create_order's otp_code parameter and
    auth/service.py::WALLET_CREDIT_SPEND_OTP_PURPOSE."""


# Fixed, same "flat, admin can't override it per product" design as
# invoice_redemptions/models.py::CASHBACK_PERCENTAGE (3% there, 5% here --
# two different flows, deliberately not sharing a constant). What the
# customer pays extra, on top of whatever they actually owe in new money, to
# opt into "riscuoti subito cashback" on an eligible order -- see
# _credit_order_cashback() below for where it's paid back.
ORDER_CASHBACK_PERCENTAGE = 5


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
        "cashback_available": version.cashback_enabled,
        "cashback_percentage": ORDER_CASHBACK_PERCENTAGE,
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
        "product_image_url": version.image_url if version else None,
        "created_by_user_id": order.created_by_user_id,
        "amount_cents": order.amount_cents,
        "credit_applied_cents": order.credit_applied_cents,
        # Includes the cashback surcharge (0 when cashback wasn't requested)
        # -- this is the actual amount owed in new money for this order, via
        # bank transfer or card.
        "residual_amount_cents": order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents,
        "cashback_requested": order.cashback_requested,
        "cashback_surcharge_cents": order.cashback_surcharge_cents,
        "cashback_credited_at": order.cashback_credited_at,
        "status": order.status,
        "payment_method": order.payment_method,
        "stripe_checkout_session_id": order.stripe_checkout_session_id,
        "payment_proof_uploaded_at": order.payment_proof_uploaded_at,
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
    cashback_requested: bool = False,
    otp_code: str | None = None,
    require_otp_for_credit_spend: bool = True,
) -> Order:
    """require_otp_for_credit_spend defaults to True (self-checkout, POST
    /orders/mine) -- spending existing wallet LialCash needs a fresh emailed
    OTP so a stolen session token alone can't drain a wallet. The staff
    endpoint (POST /orders, wallet.manage-gated) passes False: an admin
    applying a customer's credit on their behalf is already an audited,
    permissioned action, and the OTP would go to the CUSTOMER's inbox, not
    the admin's -- requiring it there would make the admin flow unusable,
    not safer."""
    version, _product = await _get_sellable_product_version(
        db, organization_id=organization_id, product_version_id=product_version_id
    )
    amount_cents = version.base_price_cents
    cap = max_creditable_cents(amount_cents=amount_cents, credit_discount_percentage=version.credit_discount_percentage)
    if credit_applied_cents < 0 or credit_applied_cents > cap:
        raise InvalidCreditAmountError(
            f"credit_applied_cents must be between 0 and {cap} for this product ({version.credit_discount_percentage}% of {amount_cents})"
        )

    if credit_applied_cents > 0 and require_otp_for_credit_spend:
        from app.domains.auth import service as auth_service

        if not otp_code or not await auth_service.verify_otp(
            db, user_id=customer_user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code=otp_code
        ):
            raise InvalidOtpError("Codice di conferma mancante, non valido o scaduto.")

    # residual_before_cashback is the actual "100%" base this order owes in
    # new money before any cashback surcharge -- also what a returned
    # cashback credit is computed FROM (see _credit_order_cashback), never
    # the pre-credit-discount amount_cents. Crediting cashback off a higher
    # base than what was genuinely paid new would let a customer manufacture
    # credit from credit already spent -- exactly the invariant this
    # wallet's whole design (docs/cashback-partner-invoices-plan.md) exists
    # to prevent.
    residual_before_cashback = amount_cents - credit_applied_cents
    cashback_surcharge_cents = 0
    if cashback_requested:
        if not version.cashback_enabled:
            raise CashbackNotAvailableError("Questo prodotto non consente il cashback.")
        if residual_before_cashback <= 0:
            raise CashbackNotAvailableError(
                "Il cashback richiede un pagamento residuo maggiore di zero -- il credito wallet copre già l'intero importo."
            )
        cashback_surcharge_cents = round(residual_before_cashback * ORDER_CASHBACK_PERCENTAGE / 100)

    total_to_charge = residual_before_cashback + cashback_surcharge_cents

    # Only matters when something is actually going to be charged -- if
    # credit alone covers the price (and no cashback was requested, which
    # would be impossible in that case anyway), payment_method is stored
    # as-given but never acted upon (the order skips straight to PAID
    # below), so an unavailable/garbage value there shouldn't block a
    # 100%-credit order.
    if total_to_charge > 0:
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
        cashback_requested=cashback_requested,
        cashback_surcharge_cents=cashback_surcharge_cents,
        status="AWAITING_PAYMENT",
        payment_method=payment_method,
        note=note,
    )
    db.add(order)
    await db.flush()  # assigns order.id, no commit yet

    # Same "staff sees every new operational event" convention as
    # contracts/service.py::create_contract's CONTRACT_CREATED notification --
    # added before whichever commit below actually happens, so it lands in
    # the same transaction as the order row itself.
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_CREATED", entity_type="order", entity_id=order.id,
        title=f"Nuovo ordine: {version.name}", body=f"{amount_cents / 100:.2f} EUR -- {payment_method}",
        exclude_user_id=actor_user_id,
    )

    if credit_applied_cents > 0:
        assert wallet is not None
        if total_to_charge == 0:
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

    await _send_order_confirmation_email(db, organization_id=organization_id, order=order, version=version)
    return order


async def _send_order_confirmation_email(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order, version: ProductVersion
) -> None:
    """Best-effort, fires after the order is already committed -- an SMTP
    hiccup or (for a CARD order) a Stripe hiccup here must never undo an
    order that has already been created. Explains exactly how to pay: the
    IBAN for bank transfer, or a real Stripe payment link for card -- a
    fresh Checkout Session created here specifically for the email, since
    the residual/attempt the customer sees in their dashboard may create a
    separate one later (see attach_stripe_checkout_session's "only the
    latest attempt is honored" rule -- harmless, either link still works
    until the customer actually pays)."""
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return

    settings = get_settings()
    residual_cents = order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents
    order_code = str(order.id)[:8].upper()
    order_code_line = f"<p>Numero ordine: <strong>#{order_code}</strong></p>"
    cashback_line = (
        f"<p>Include il {ORDER_CASHBACK_PERCENTAGE}% per il cashback che riceverai come LialCash "
        "non appena il pagamento sarà confermato.</p>"
        if order.cashback_requested else ""
    )
    cta_label: str | None = None
    cta_url: str | None = None

    if order.status == "PAID":
        heading = "Ordine confermato"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{version.name}</strong> è confermato.</p>"
            f"<p>Totale: {order.amount_cents / 100:.2f} &euro;"
            + (f" (di cui {order.credit_applied_cents / 100:.2f} LialCash)" if order.credit_applied_cents else "")
            + "</p><p>Non è richiesto alcun pagamento aggiuntivo.</p>"
        )
    elif order.payment_method == "CARD":
        from app.domains.payments import service as payments_service

        heading = "Completa il pagamento del tuo ordine"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{version.name}</strong> è stato registrato.</p>"
            f"<p>Da pagare: <strong>{residual_cents / 100:.2f} &euro;</strong>"
            + (f" (dopo {order.credit_applied_cents / 100:.2f} LialCash già applicati)" if order.credit_applied_cents else "")
            + "</p>"
            + cashback_line
            + "<p>Completa il pagamento con carta cliccando il pulsante qui sotto.</p>"
        )
        try:
            cta_url = await payments_service.create_checkout_session_for_order(
                db, organization_id=organization_id, order=order,
                success_url=f"{settings.public_app_base_url}/customer",
                cancel_url=f"{settings.public_app_base_url}/customer",
            )
            cta_label = "Paga con carta"
        except payments_service.StripeNotConfiguredError:
            logger.warning("Order %s confirmation email sent without a Stripe link (Stripe not configured)", order.id)
        except stripe.error.StripeError:
            # A real Stripe API problem (bad/revoked key, Stripe outage, ...)
            # must never take the already-committed order down with it --
            # the customer can still pay later from "I miei Ordini", which
            # requests its own fresh session on demand.
            logger.exception("Order %s confirmation email sent without a Stripe link (Stripe API error)", order.id)
    else:
        bank_settings = await organizations_service.get_settings(db, organization_id=organization_id)
        iban = bank_settings.get("bank_iban")
        heading = "Completa il pagamento del tuo ordine"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{version.name}</strong> è stato registrato.</p>"
            f"<p>Da pagare tramite bonifico: <strong>{residual_cents / 100:.2f} &euro;</strong>"
            + (f" (dopo {order.credit_applied_cents / 100:.2f} LialCash già applicati)" if order.credit_applied_cents else "")
            + "</p>"
            + cashback_line
        )
        if iban:
            body_html += (
                f"<p><strong>IBAN:</strong> {iban}<br>"
                f"<strong>Intestatario:</strong> {bank_settings.get('bank_account_holder') or 'Lial Energy'}<br>"
                f"<strong>Causale:</strong> Ordine {order_code}</p>"
            )
            if bank_settings.get("bank_transfer_instructions"):
                body_html += f"<p>{bank_settings['bank_transfer_instructions']}</p>"
        else:
            body_html += "<p>Contatta l'amministrazione per le coordinate bancarie.</p>"

    html = render_email(
        preheader=f"Riepilogo del tuo ordine -- {version.name}",
        heading=heading,
        body_html=body_html,
        cta_label=cta_label,
        cta_url=cta_url,
    )
    try:
        send_html_email(
            to=user.email,
            subject=f"Conferma ordine - {version.name} - Lial Energy",
            html_body=html,
            text_body=f"{heading}: {version.name}, totale {order.amount_cents / 100:.2f} EUR.",
        )
    except EmailNotConfiguredError:
        logger.warning("Order confirmation email for %s not sent (SMTP not configured), order=%s", user.email, order.id)


async def _send_order_paid_email(
    db: AsyncSession, *, order: Order, version: ProductVersion | None
) -> None:
    """Best-effort, fires after the order is already committed PAID -- the
    second of the two customer emails a product order gets (the first is
    _send_order_confirmation_email's "ordine ricevuto" at creation, which
    deliberately never claims the payment itself is done). Same email
    regardless of which of the two ways an order reaches PAID: an admin
    confirming a bank transfer (confirm_payment) or Stripe's webhook
    confirming a card payment (mark_paid_via_stripe) -- only the method
    label in the body differs, both call this exact function."""
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return

    method_label = "Carta (Stripe)" if order.payment_method == "CARD" else "Bonifico bancario"
    product_name = version.name if version else "un prodotto"
    paid_at_label = order.paid_at.strftime("%d/%m/%Y %H:%M") if order.paid_at else "-"
    # What actually landed as new money on THIS payment -- not the raw
    # product price, which credit/cashback can both make different from what
    # was really charged (see to_read_dict's residual_amount_cents).
    amount_paid_cents = order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents
    cashback_credited_line = ""
    if order.cashback_requested and order.cashback_credited_at:
        total_cashback_cents = (order.amount_cents - order.credit_applied_cents) + order.cashback_surcharge_cents
        cashback_credited_line = (
            f"<p>Hai ricevuto <strong>{total_cashback_cents / 100:.2f} LialCash</strong> sul tuo wallet.</p>"
        )
    body_html = (
        "<p>Il pagamento del tuo ordine &egrave; stato confermato.</p>"
        f"<p><strong>Numero ordine:</strong> #{str(order.id)[:8].upper()}<br>"
        f"<strong>Prodotto:</strong> {product_name}<br>"
        f"<strong>Importo pagato:</strong> {amount_paid_cents / 100:.2f} &euro;<br>"
        f"<strong>Metodo di pagamento:</strong> {method_label}<br>"
        "<strong>Stato:</strong> Pagato<br>"
        f"<strong>Data:</strong> {paid_at_label}</p>"
        + cashback_credited_line
    )
    html = render_email(
        preheader="Pagamento completato con successo",
        heading="Pagamento completato con successo",
        body_html=body_html,
        cta_label="Vai ai miei ordini",
        cta_url=f"{get_settings().public_app_base_url}/customer",
    )
    try:
        send_html_email(
            to=user.email,
            subject=f"Pagamento confermato - Ordine {str(order.id)[:8]} - Lial Energy",
            html_body=html,
            text_body=(
                f"Pagamento completato con successo. Ordine {order.id}, {product_name}, "
                f"{order.amount_cents / 100:.2f} EUR, {method_label}."
            ),
        )
    except EmailNotConfiguredError:
        logger.warning("Order-paid email for %s not sent (SMTP not configured), order=%s", user.email, order.id)


async def get_org_scoped(db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID) -> Order | None:
    order = await db.get(Order, order_id)
    if order is None or order.organization_id != organization_id:
        return None
    return order


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, order_id: uuid.UUID
) -> Order | None:
    """Same ownership-scoped lookup pattern as
    invoice_redemptions/service.py::get_owned -- backs every customer-facing
    "my order" mutation (payment-proof upload, payment-method change) so a
    customer can never touch someone else's order by guessing its id."""
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None or order.customer_user_id != customer_user_id:
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


async def _credit_order_cashback(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order, version: ProductVersion | None,
    actor_user_id: uuid.UUID | None,
) -> None:
    """The other half of "riscuoti subito cashback": once an order that
    opted in reaches PAID (bank transfer admin-confirmed, or Stripe
    webhook), credits the customer's wallet with exactly what they just
    paid new for this order -- the pre-surcharge residual (100%) plus the
    surcharge itself (the 5% bonus) -- as two separate LialCash rows, same
    "the ledger always shows the split explicitly" reasoning as
    invoice_redemptions/service.py::confirm_payment's base+bonus pair.
    Never more than that: the credited total is always <= what genuinely
    landed as real revenue on this exact order, so this can never manufacture
    credit out of credit already spent (see create_order's
    residual_before_cashback comment for the same invariant enforced at the
    other end).

    Idempotent two ways at once: the guard below (cashback_credited_at is
    only ever set once) and, independently, credit_wallet()'s own
    idempotency-key dedup (derived from the order id, never client-supplied)
    -- either alone would be enough to make a retried Stripe webhook a
    no-op, but there is no reason not to have both."""
    if not order.cashback_requested or order.cashback_credited_at is not None:
        return
    base_cents = order.amount_cents - order.credit_applied_cents
    bonus_cents = order.cashback_surcharge_cents
    if base_cents <= 0 or bonus_cents <= 0:
        # Should be unreachable (create_order already refuses cashback with
        # no real residual to reward) -- defensive, not a real code path.
        return

    product_name = version.name if version else "un prodotto"
    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=order.customer_user_id
    )
    await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=base_cents,
        type_="ADMIN_CREDIT", actor_user_id=actor_user_id, source="ORDER_CASHBACK_BASE",
        reference_order_id=order.id, note=f"Cashback ordine {product_name}",
        idempotency_key=f"order:{order.id}:cashback-base",
    )
    await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=bonus_cents,
        type_="ADMIN_CREDIT", actor_user_id=actor_user_id, source="ORDER_CASHBACK_BONUS",
        reference_order_id=order.id, note=f"Bonus {ORDER_CASHBACK_PERCENTAGE}% cashback ordine {product_name}",
        idempotency_key=f"order:{order.id}:cashback-bonus",
    )
    order.cashback_credited_at = utcnow()


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> Order:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise OrderError("Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot confirm payment for an order in status {order.status}")
    if order.payment_method == "CARD":
        # This is the manual bank-transfer confirmation action ("Conferma
        # bonifico ricevuto") -- a CARD order can only ever reach PAID via
        # mark_paid_via_stripe(), called from the Stripe webhook once
        # Stripe itself confirms the charge. Refusing it here (not just
        # hiding the button in admin-orders-panel.tsx) is the actual
        # enforcement: an admin must never be able to mark a Stripe order
        # paid without Stripe's own confirmation, matching the same
        # "browser back on the success page proves nothing" principle for
        # the admin side too.
        raise InvalidOrderStateError(
            "Questo ordine si paga con carta: la conferma arriva automaticamente da Stripe, "
            "non è richiesta (né consentita) un'azione manuale."
        )

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
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAID", entity_type="order", entity_id=order.id,
        title=f"Bonifico confermato: {version.name if version else 'ordine'}",
        body=f"{order.amount_cents / 100:.2f} EUR", exclude_user_id=actor_user_id,
    )
    # credit_wallet() (called from here) commits internally -- this captures
    # the PAID transition and notifications above together with the
    # cashback credit rows, atomically, same pattern as create_order's own
    # debit_wallet_for_purchase call.
    await _credit_order_cashback(db, organization_id=organization_id, order=order, version=version, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(order)
    await _send_order_paid_email(db, order=order, version=version)
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


async def change_payment_method(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order, new_payment_method: str
) -> Order:
    """Lets a customer switch an AWAITING_PAYMENT order between BANK_TRANSFER
    and CARD -- e.g. tired of waiting on a bank transfer, wants to pay by
    card right now instead. The caller (router) has already resolved and
    ownership-checked `order`. Clearing stripe_checkout_session_id when
    moving AWAY from CARD is not cosmetic: mark_paid_via_stripe() looks an
    order up BY that session id, so a stale/abandoned Stripe session left
    attached could otherwise mark this order paid off a card payment that
    has nothing to do with the bank transfer the customer switched to."""
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot change payment method for an order in status {order.status}")
    if new_payment_method not in ORDER_PAYMENT_METHODS:
        raise InvalidPaymentMethodError(f"payment_method must be one of {ORDER_PAYMENT_METHODS}")

    if new_payment_method != order.payment_method:
        available = await get_available_payment_methods(db, organization_id=organization_id)
        if new_payment_method == "BANK_TRANSFER" and not available["bank_transfer"]:
            raise PaymentMethodNotAvailableError("Il pagamento con bonifico non è configurato.")
        if new_payment_method == "CARD" and not available["card"]:
            raise PaymentMethodNotAvailableError("Il pagamento con carta non è configurato.")
        if order.payment_method == "CARD":
            order.stripe_checkout_session_id = None
        order.payment_method = new_payment_method
        await db.commit()
        await db.refresh(order)
    return order


async def upload_payment_proof(
    db: AsyncSession, *, organization_id: uuid.UUID, order: Order,
    file_bytes: bytes, content_type: str, original_filename: str, actor_user_id: uuid.UUID,
) -> Order:
    """Attaches a customer-uploaded photo/PDF of a bank transfer receipt to
    an AWAITING_PAYMENT/BANK_TRANSFER order -- purely advisory extra
    evidence for whoever clicks "Conferma bonifico ricevuto" in
    admin-orders-panel.tsx; never changes order.status by itself. Reuses
    core/storage.py's private documents bucket directly, same as
    invoice_redemptions/service.py::submit_redemption -- no reason to route
    this through the `documents` domain, whose contract_id is NOT NULL by
    design."""
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document

    if order.status != "AWAITING_PAYMENT":
        raise PaymentProofError(f"Cannot attach a payment proof to an order in status {order.status}")
    if order.payment_method != "BANK_TRANSFER":
        raise PaymentProofError("La prova di pagamento è prevista solo per gli ordini pagati con bonifico.")

    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"order-payment-proofs/{order.customer_user_id}",
        )
    except UploadValidationError as exc:
        raise PaymentProofError(str(exc)) from exc

    order.payment_proof_storage_key = storage_key
    order.payment_proof_original_filename = original_filename
    order.payment_proof_uploaded_at = utcnow()

    version = await db.get(ProductVersion, order.product_version_id)
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAYMENT_PROOF_UPLOADED", entity_type="order", entity_id=order.id,
        title=f"Prova di pagamento caricata: {version.name if version else 'ordine'}",
        body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(order)
    return order


PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS = 300


def presigned_payment_proof_url(order: Order) -> str:
    from app.core.storage import generate_presigned_document_url as storage_presign_document

    assert order.payment_proof_storage_key is not None  # guaranteed by the router's own check
    return storage_presign_document(
        storage_key=order.payment_proof_storage_key, expires_in_seconds=PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS
    )


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
    # No actor to exclude here (see docstring above -- Stripe confirmed this,
    # not a human), unlike confirm_payment's staff notification.
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAID", entity_type="order", entity_id=order.id,
        title=f"Pagamento Stripe confermato: {version.name if version else 'ordine'}",
        body=f"{order.amount_cents / 100:.2f} EUR",
    )
    # No actor here either -- Stripe confirmed this, not an admin. See
    # _credit_order_cashback's own docstring for why this is idempotent
    # against Stripe's webhook retries.
    await _credit_order_cashback(db, organization_id=organization_id, order=order, version=version, actor_user_id=None)
    await db.commit()
    await db.refresh(order)
    await _send_order_paid_email(db, order=order, version=version)
    return order
