import uuid

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

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
    unchanged on the completed-session event."""
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
        metadata={"order_id": str(order.id), "organization_id": str(organization_id)},
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


async def handle_webhook_event(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: bytes, sig_header: str
) -> None:
    """The webhook URL is per-organization (see payments/router.py --
    /payments/stripe/webhook/{organization_id}), which is how a single
    endpoint stays correct in a multi-tenant deployment: each org's own
    webhook secret verifies only that org's events, and mark_paid_via_stripe
    below is scoped to organization_id too, so one org's Stripe account can
    never touch another org's orders even in principle."""
    webhook_secret = await organizations_service.get_stripe_webhook_secret(db, organization_id=organization_id)
    if not webhook_secret:
        raise StripeNotConfiguredError("Il webhook Stripe non è configurato per questa organizzazione.")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise WebhookVerificationError(str(exc)) from exc

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        try:
            await orders_service.mark_paid_via_stripe(
                db, organization_id=organization_id, stripe_checkout_session_id=session["id"]
            )
        except orders_service.OrderError:
            # No order in this org matches that session id -- not this
            # webhook call's problem to solve, and not a reason to make
            # Stripe retry forever. Silently ignore.
            pass
