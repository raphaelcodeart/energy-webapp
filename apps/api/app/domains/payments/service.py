import uuid

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.imported_products import service as imported_products_service
from app.domains.imported_products.models import ImportedProductOrder
from app.domains.invoice_redemptions import service as invoice_redemptions_service
from app.domains.invoice_redemptions.models import InvoiceRedemption
from app.domains.orders import service as orders_service
from app.domains.orders.models import Order
from app.domains.organizations import service as organizations_service


class PaymentsError(Exception):
    pass


class StripeNotConfiguredError(PaymentsError):
    pass


class WebhookVerificationError(PaymentsError):
    pass


async def create_checkout_session_for_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    order: Order,
    success_url: str,
    cancel_url: str,
) -> str:
    """Creates a Stripe Checkout Session for exactly the order's residual
    (amount_cents - credit_applied_cents already applied, never the full
    price) and records the session id on the order (attach_stripe_checkout_
    session -- does NOT mark it PAID; only the webhook does that, once
    Stripe actually confirms the charge). client_reference_id is how
    handle_webhook_event() below finds this order back -- Stripe echoes it
    unchanged on the completed-session event. metadata.kind="order" is how
    the webhook routes the event to orders_service instead of
    invoice_redemptions_service (see create_checkout_session_for_redemption
    below, the only other kind)."""
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    # Includes the cashback surcharge when the order opted into "riscuoti
    # subito cashback" (0 otherwise) -- see orders/service.py::create_order
    # and ORDER_CASHBACK_PERCENTAGE. Never the full price, always just what's
    # actually still owed in new money.
    residual_cents = order.amount_cents - order.credit_applied_cents + order.cashback_surcharge_cents
    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Ordine {order.id}"},
                    "unit_amount": residual_cents,
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(order.id),
        metadata={"kind": "order", "order_id": str(order.id), "organization_id": str(organization_id)},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await orders_service.attach_stripe_checkout_session(db, order=order, session_id=session.id)
    if not session.url:
        # Stripe types this as Optional but a "payment" mode Session always
        # gets a hosted checkout URL in practice -- this only guards mypy
        # and a genuinely unexpected empty response from Stripe's API.
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def create_checkout_session_for_redemption(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    redemption: InvoiceRedemption,
    success_url: str,
    cancel_url: str,
) -> str:
    """Same shape as create_checkout_session_for_order, for the "pay
    CASHBACK_PERCENTAGE% to redeem an invoice" flow -- charges exactly
    payment_due_cents(confirmed_amount_cents), never the full invoice
    amount (that's not owed at all, it was already paid to the partner
    supplier; only the redemption fee is). metadata.kind="invoice_redemption"
    is how the webhook routes here instead of orders_service."""
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    due_cents = invoice_redemptions_service.payment_due_cents(redemption.confirmed_amount_cents)
    if not due_cents or due_cents <= 0:
        raise StripeNotConfiguredError("Nessun importo da pagare per questo riscatto.")

    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Riscatto cashback {redemption.id}"},
                    "unit_amount": due_cents,
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(redemption.id),
        metadata={
            "kind": "invoice_redemption", "invoice_redemption_id": str(redemption.id),
            "organization_id": str(organization_id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await invoice_redemptions_service.attach_stripe_checkout_session(db, redemption=redemption, session_id=session.id)
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def create_checkout_session_for_imported_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    order: ImportedProductOrder,
    success_url: str,
    cancel_url: str,
) -> str:
    """Same shape as create_checkout_session_for_order, for the "Acquisti
    LialEnergy" imported-products plugin's own parallel order table --
    metadata.kind="imported_order" is the third and last value
    handle_webhook_event() below routes on."""
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    residual_cents = order.amount_cents - order.credit_applied_cents
    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"Ordine {order.id}"},
                    "unit_amount": residual_cents,
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(order.id),
        metadata={"kind": "imported_order", "imported_order_id": str(order.id), "organization_id": str(organization_id)},
        success_url=success_url,
        cancel_url=cancel_url,
    )
    await imported_products_service.attach_stripe_checkout_session(db, order=order, session_id=session.id)
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def handle_webhook_event(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: bytes, sig_header: str
) -> None:
    """The webhook URL is per-organization (see payments/router.py --
    /payments/stripe/webhook/{organization_id}), which is how a single
    endpoint stays correct in a multi-tenant deployment: each org's own
    webhook secret verifies only that org's events, and both
    mark_paid_via_stripe functions below are scoped to organization_id too,
    so one org's Stripe account can never touch another org's orders or
    redemptions even in principle.

    Routes on the session's own metadata.kind (set at creation, see the two
    create_checkout_session_for_* functions above) rather than trying one
    lookup then the other -- a session id could in principle collide across
    the two tables' independent uniqueness constraints, and routing
    explicitly avoids ever depending on that not happening. Missing/unknown
    metadata (e.g. a session created before this field existed) falls back
    to "order", the original and only kind before Session 30."""
    webhook_secret = await organizations_service.get_stripe_webhook_secret(db, organization_id=organization_id)
    if not webhook_secret:
        raise StripeNotConfiguredError("Il webhook Stripe non è configurato per questa organizzazione.")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise WebhookVerificationError(str(exc)) from exc

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # session/session.metadata are stripe.StripeObject, not a dict --
        # this SDK version's StripeObject deliberately has no .get() (raises
        # AttributeError pointing at .to_dict()/subscript access instead),
        # only attribute access and __getitem__ for known keys. getattr()
        # with a default is what safely handles both "no metadata at all"
        # (a session created before Session 30 added this field) and "no
        # kind key in metadata" in one expression.
        kind = getattr(getattr(session, "metadata", None), "kind", "order")
        if kind == "invoice_redemption":
            try:
                await invoice_redemptions_service.mark_paid_via_stripe(
                    db, organization_id=organization_id, stripe_checkout_session_id=session["id"]
                )
            except invoice_redemptions_service.InvoiceRedemptionError:
                # No redemption in this org matches that session id -- not
                # this webhook call's problem to solve, and not a reason to
                # make Stripe retry forever. Silently ignore.
                pass
        elif kind == "imported_order":
            try:
                await imported_products_service.mark_paid_via_stripe(
                    db, organization_id=organization_id, stripe_checkout_session_id=session["id"]
                )
            except imported_products_service.ImportedProductsError:
                pass
        else:
            try:
                await orders_service.mark_paid_via_stripe(
                    db, organization_id=organization_id, stripe_checkout_session_id=session["id"]
                )
            except orders_service.OrderError:
                pass
