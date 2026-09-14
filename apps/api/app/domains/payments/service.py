import logging
import uuid
from datetime import UTC, datetime

import stripe
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.contracts import payment_plans
from app.domains.contracts.models import Contract
from app.domains.imported_products import service as imported_products_service
from app.domains.imported_products.models import ImportedProductOrder
from app.domains.invoice_redemptions import service as invoice_redemptions_service
from app.domains.invoice_redemptions.models import InvoiceRedemption
from app.domains.orders import service as orders_service
from app.domains.orders.models import Order
from app.domains.organizations import service as organizations_service
from app.domains.payments.models import StripeWebhookEvent

logger = logging.getLogger(__name__)


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


async def create_checkout_session_for_contract(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    contract: Contract,
    plan_key: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Checkout for a Lial Energy CONTRACT -- one payment, or a real Stripe
    subscription that charges the card by itself and stops after N
    instalments.

    Everything is created through the API, per contract: the Price is built
    inline from the amount frozen on this contract
    (`contracts.gross_amount_cents`, already VAT-correct for this customer),
    so there is no Stripe Product or Price in the dashboard to keep in sync
    with the catalog, and a price change tomorrow cannot restate a contract
    somebody already agreed to.

    3 rate and 12 rate use the same mechanism and differ only in the count.
    Nothing is financed by a third party -- Lial Energy is splitting its own
    invoice -- so this needs no capability beyond ordinary card payments.

    Never marks the contract paid: only the verified webhook does that. The
    success URL is not proof of anything.
    """
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    plan = payment_plans.plan_by_key(plan_key)
    if plan is None:
        raise PaymentsError("Modalità di pagamento non valida.")
    total_cents = contract.gross_amount_cents
    if not total_cents or total_cents <= 0:
        raise PaymentsError("Questo contratto non ha un importo da pagare.")
    breakdown = payment_plans.breakdown_for(plan, total_cents)
    if breakdown.instalment_cents <= 0:
        raise PaymentsError("Importo troppo basso per questa modalità di pagamento.")

    product_name = f"Contratto Lial Energy {str(contract.id)[:8].upper()}"
    metadata = {
        "kind": "contract",
        "contract_id": str(contract.id),
        "organization_id": str(organization_id),
        "payment_plan": plan.key,
    }

    if not breakdown.is_subscription:
        session = stripe.checkout.Session.create(
            api_key=secret_key,
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": product_name},
                    "unit_amount": breakdown.total_cents,
                },
                "quantity": 1,
            }],
            client_reference_id=str(contract.id),
            metadata=metadata,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    else:
        # No add_invoice_items for the rounding remainder: that API needs a
        # Stripe Product created up front (it cannot take an inline
        # product_data), which would mean one Product object per contract
        # cluttering the account to recover at most 6 cents. The instalment
        # is rounded instead and the resulting total is shown to the
        # customer -- see payment_plans.PlanBreakdown.
        session = stripe.checkout.Session.create(
            api_key=secret_key,
            mode="subscription",
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "product_data": {"name": f"{product_name} — rata mensile"},
                    "unit_amount": breakdown.instalment_cents,
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }],
            client_reference_id=str(contract.id),
            metadata=metadata,
            subscription_data={"metadata": metadata},
            success_url=success_url,
            cancel_url=cancel_url,
        )

    from app.domains.contracts import service as contracts_service

    await contracts_service.attach_stripe_checkout_session(
        db, contract=contract, session_id=session.id, plan_key=plan.key
    )
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un URL di checkout valido.")
    return session.url


async def _stop_subscription_after_last_instalment(
    *, secret_key: str, subscription_id: str, instalments: int
) -> None:
    """A Stripe subscription runs forever unless told otherwise, so "12 rate"
    has to be made true explicitly: the subscription is set to cancel at the
    end of the period in which the last instalment falls.

    Done here, right after the subscription exists, rather than counting
    invoices as they arrive -- that would leave the stop condition spread
    across months of webhook deliveries, and one missed delivery would keep
    charging somebody who had finished paying."""
    subscription = stripe.Subscription.retrieve(subscription_id, api_key=secret_key)
    start = getattr(subscription, "current_period_start", None) or int(datetime.now(UTC).timestamp())
    # The first instalment is charged immediately, so (instalments - 1)
    # further monthly periods remain.
    cancel_at = start + (instalments - 1) * 31 * 24 * 3600
    stripe.Subscription.modify(subscription_id, api_key=secret_key, cancel_at=cancel_at)


async def _claim_event(
    db: AsyncSession, *, organization_id: uuid.UUID, event_id: str, event_type: str
) -> StripeWebhookEvent | None:
    """Records the event id before anything is done with it, and returns None
    if it has already been seen.

    Insert-first rather than check-then-insert: two concurrent deliveries of
    the same event would both pass a check, and Stripe redelivers freely and
    promises only at-least-once. The UNIQUE constraint is what actually
    decides which delivery proceeds."""
    row = StripeWebhookEvent(
        organization_id=organization_id, stripe_event_id=event_id, event_type=event_type
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return None
    await db.refresh(row)
    return row


async def _finish_event(db: AsyncSession, *, row: StripeWebhookEvent | None, outcome: str) -> None:
    if row is None:
        return
    row.processed_at = datetime.now(UTC)
    row.outcome = outcome[:255]
    await db.commit()


async def _handle_contract_checkout(
    db: AsyncSession, *, organization_id: uuid.UUID, session, secret_key: str
) -> str:
    """First payment of a contract landed: mark it paid (which cascades the
    contract to ACTIVE and triggers commissions, exactly as an admin
    confirming a bank transfer does), and -- for an instalment plan -- tell
    Stripe when to stop charging."""
    from app.domains.contracts import service as contracts_service

    contract = await contracts_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=session["id"]
    )
    if contract is None:
        return "nessun contratto per questa sessione"

    subscription_id = getattr(session, "subscription", None)
    if subscription_id:
        plan = payment_plans.plan_by_key(contract.payment_plan)
        await contracts_service.attach_stripe_subscription(
            db, contract=contract, subscription_id=str(subscription_id),
            customer_id=str(getattr(session, "customer", "") or "") or None,
        )
        if plan is not None and plan.instalments > 1:
            try:
                await _stop_subscription_after_last_instalment(
                    secret_key=secret_key,
                    subscription_id=str(subscription_id),
                    instalments=plan.instalments,
                )
            except Exception:
                # The contract is paid and active either way. A subscription
                # left without its stop date would keep charging, so this is
                # loud in the log and visible on the event row rather than
                # swallowed -- but it must not fail the webhook, which would
                # make Stripe retry an event already applied.
                logger.exception(
                    "Could not set cancel_at on subscription %s (contract %s)",
                    subscription_id, contract.id,
                )
                return f"contratto {contract.id} pagato; ATTENZIONE: cancel_at non impostato"
    return f"contratto {contract.id} pagato"


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

    # Needed only by the contract branch, which calls back into Stripe to set
    # a subscription's stop date. Fetched here so that branch stays a pure
    # function of what it is given.
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id) or ""

    # Exactly-once, at the event level. Everything below used to rely on each
    # handler happening to be idempotent on its own -- true for the flows
    # that existed, but contract subscriptions fire invoice.paid every month
    # for the same subscription, so "the same event twice" and "the next
    # instalment" had to stop being indistinguishable.
    event_row = await _claim_event(
        db, organization_id=organization_id,
        event_id=str(event["id"]), event_type=str(event["type"]),
    )
    if event_row is None:
        return  # already processed; acknowledge and do nothing

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
        elif kind == "contract":
            outcome = await _handle_contract_checkout(
                db, organization_id=organization_id, session=session, secret_key=secret_key
            )
            await _finish_event(db, row=event_row, outcome=outcome)
            return
        else:
            try:
                await orders_service.mark_paid_via_stripe(
                    db, organization_id=organization_id, stripe_checkout_session_id=session["id"]
                )
            except orders_service.OrderError:
                pass

    elif event["type"] in ("invoice.paid", "invoice.payment_failed"):
        # Every instalment after the first. The contract is already ACTIVE by
        # then, so nothing about its status changes here -- this is about
        # telling somebody when a monthly charge does not go through, which
        # is the one thing an instalment plan can do that a single payment
        # cannot.
        from app.domains.contracts import service as contracts_service

        invoice = event["data"]["object"]
        subscription_id = getattr(invoice, "subscription", None)
        if subscription_id:
            outcome = await contracts_service.record_subscription_invoice(
                db,
                organization_id=organization_id,
                subscription_id=str(subscription_id),
                paid=event["type"] == "invoice.paid",
                amount_cents=int(getattr(invoice, "amount_paid", 0) or getattr(invoice, "amount_due", 0) or 0),
            )
            await _finish_event(db, row=event_row, outcome=outcome)
            return

    await _finish_event(db, row=event_row, outcome=f"gestito: {event['type']}")
