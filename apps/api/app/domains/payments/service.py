import logging
import uuid
from datetime import UTC, datetime

import stripe
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.domains.contracts import payment_plans
from app.domains.contracts.models import Contract, ContractRequest, ContractRequestCheckout
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
    charging somebody who had finished paying.

    `proration_behavior="none"`: the stop date falls a few days into the
    period after the last instalment, and without it Stripe would credit the
    customer for those "unused" days of a month they never owed."""
    subscription = stripe.Subscription.retrieve(subscription_id, api_key=secret_key)
    # From API "basil" the billing period lives on the items, not on the
    # subscription; the anchor is on the subscription in every version.
    start = (
        getattr(subscription, "billing_cycle_anchor", None)
        or getattr(subscription, "start_date", None)
        or int(datetime.now(UTC).timestamp())
    )
    # The first instalment is charged immediately, so (instalments - 1)
    # further monthly periods remain.
    cancel_at = start + (instalments - 1) * 31 * 24 * 3600
    stripe.Subscription.modify(
        subscription_id, api_key=secret_key, cancel_at=cancel_at, proration_behavior="none"
    )


async def create_checkout_session_for_request(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    request: ContractRequest,
    plan_key: str,
    actor_user_id: uuid.UUID,
    success_url: str,
    cancel_url: str,
) -> str:
    """One Checkout for every payable contract of a pratica (Session 52).

    One line per contract, each carrying its contract id in the metadata of
    its inline product -- in a subscription that is what ties each
    subscription item, and so each line of every monthly invoice, back to
    its contract. Amounts come from each contract's frozen price, split by
    that contract's own plan breakdown: the customer pays the sum, each
    contract receives exactly its own instalment.

    The contracts and amounts are frozen in a contract_request_checkouts row
    before the customer is sent to Stripe; the webhook pays what that row
    says, never what the pratica looks like by the time it arrives.

    Earlier sessions of the same pratica still open are expired, best
    effort: a second tab should not be able to take a second payment."""
    from app.domains.contracts import requests as requests_service

    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Il pagamento con carta non è attivo al momento. Riprova più tardi.")
    plan = payment_plans.plan_by_key(plan_key)
    if plan is None:
        raise PaymentsError("Modalità di pagamento non valida.")

    points = requests_service.payable_points(await requests_service.list_points(db, request=request))
    if not points:
        raise PaymentsError("In questa pratica non c'è nessun contratto da pagare.")
    option = next(o for o in requests_service.plan_options(points) if o.plan.key == plan.key)
    if not option.available:
        raise PaymentsError(option.unavailable_reason or "Modalità di pagamento non disponibile.")

    code = str(request.id)[:8].upper()
    metadata = {
        "kind": "contract_request",
        "contract_request_id": str(request.id),
        "organization_id": str(organization_id),
        "payment_plan": plan.key,
    }
    frozen_lines = []
    line_items = []
    labels = await _point_labels(db, points)
    for contract in points:
        breakdown = payment_plans.breakdown_for(plan, int(contract.gross_amount_cents or 0))
        frozen_lines.append({
            "contract_id": str(contract.id),
            "gross_cents": int(contract.gross_amount_cents or 0),
            "instalment_cents": breakdown.instalment_cents,
        })
        price_data = {
            "currency": "eur",
            "product_data": {
                "name": labels[contract.id],
                # Stripe's page shows a subscription as "X € al mese" and
                # nothing more; without this line nobody can tell that it
                # stops, or what it adds up to.
                "description": (
                    f"{plan.instalments} rate mensili da {_euro(breakdown.instalment_cents)} · "
                    f"totale {_euro(breakdown.total_cents)}"
                    if breakdown.is_subscription
                    else f"Pagamento unico · pratica {code}"
                ),
                "metadata": {"contract_id": str(contract.id), "contract_request_id": str(request.id)},
            },
            "unit_amount": breakdown.instalment_cents,
        }
        if breakdown.is_subscription:
            price_data["recurring"] = {"interval": "month"}
        line_items.append({"price_data": price_data, "quantity": 1})

    params = {
        "api_key": secret_key,
        "mode": "subscription" if plan.instalments > 1 else "payment",
        "line_items": line_items,
        "client_reference_id": str(request.id),
        "metadata": metadata,
        "success_url": success_url,
        "cancel_url": cancel_url,
        # Said in words right above the pay button (Session 56): on an
        # instalment plan Stripe itself only ever shows the monthly figure,
        # and a customer paying "340 € al mese" for a 1.020 € pratica must
        # read that it is 3 of them, and that they stop by themselves.
        "custom_text": {"submit": {"message": _checkout_summary(plan, option, len(points))}},
    }
    if plan.instalments > 1:
        params["subscription_data"] = {"metadata": metadata, "description": f"Pratica Lial Energy {code}"}
    else:
        params["payment_intent_data"] = {"metadata": metadata, "description": f"Pratica Lial Energy {code}"}

    previous_open = list(
        (
            await db.execute(
                select(ContractRequestCheckout).where(
                    ContractRequestCheckout.contract_request_id == request.id,
                    ContractRequestCheckout.completed_at.is_(None),
                )
            )
        ).scalars()
    )
    session = stripe.checkout.Session.create(**params)
    if not session.url:
        raise StripeNotConfiguredError("Stripe non ha restituito un indirizzo di pagamento valido.")

    db.add(
        ContractRequestCheckout(
            organization_id=organization_id,
            contract_request_id=request.id,
            stripe_checkout_session_id=session.id,
            payment_plan=plan.key,
            lines=frozen_lines,
            total_cents=option.total_cents,
            instalment_cents=option.instalment_cents,
            created_by_user_id=actor_user_id,
        )
    )
    await db.commit()

    for old in previous_open:
        try:
            stripe.checkout.Session.expire(old.stripe_checkout_session_id, api_key=secret_key)
        except Exception:  # noqa: BLE001 -- already completed or expired: nothing to stop
            logger.info("Checkout %s of pratica %s not expired (already closed)", old.stripe_checkout_session_id, code)
    return session.url


def _euro(cents: int) -> str:
    return f"{cents / 100:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _checkout_summary(plan: payment_plans.PaymentPlan, option, contracts: int) -> str:
    what = "1 contratto" if contracts == 1 else f"{contracts} contratti"
    if plan.instalments <= 1:
        return f"Pagamento unico di {_euro(option.total_cents)} per {what} Lial Energy."
    return (
        f"Paghi {plan.instalments} rate mensili da {_euro(option.instalment_cents)}, per un totale di "
        f"{_euro(option.total_cents)} ({what}). La prima rata oggi, le altre addebitate automaticamente ogni "
        f"mese: gli addebiti si fermano da soli dopo la {plan.instalments}ª rata."
    )


async def _point_labels(db: AsyncSession, points: list[Contract]) -> dict[uuid.UUID, str]:
    """"Luce Energia Circolare — Via Roma 1, Roma": what the customer sees on
    the Stripe page, one line per POD. The POD code is used when known
    (contracts from before Session 53), the address otherwise."""
    from app.domains.catalog.models import ProductVersion
    from app.domains.customers.models import Address, SupplyPoint

    out = {}
    for contract in points:
        supply_point = await db.get(SupplyPoint, contract.supply_point_id)
        address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
        version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
        if supply_point is not None and supply_point.pod_code:
            point = f"POD {supply_point.pod_code}"
        elif supply_point is not None and supply_point.pdr_code:
            point = f"PDR {supply_point.pdr_code}"
        elif address is not None:
            point = f"{address.street}, {address.city}"
        else:
            point = f"Contratto {str(contract.id)[:8].upper()}"
        out[contract.id] = f"{version.name} — {point}" if version else point
    return out


async def _handle_request_checkout(db: AsyncSession, *, organization_id: uuid.UUID, session, secret_key: str) -> str:
    from app.domains.contracts import requests as requests_service

    checkout = (
        await db.execute(
            select(ContractRequestCheckout).where(
                ContractRequestCheckout.organization_id == organization_id,
                ContractRequestCheckout.stripe_checkout_session_id == session["id"],
            )
        )
    ).scalar_one_or_none()
    if checkout is None:
        return "nessuna pratica per questa sessione"

    subscription_id = getattr(session, "subscription", None)
    subscription_id = str(subscription_id) if subscription_id else None
    items: dict[str, str] = {}
    if subscription_id:
        try:
            items = _subscription_items_by_contract(secret_key=secret_key, subscription_id=subscription_id)
        except Exception:
            # The payment happened and must be recorded whatever else fails.
            # Without the item map later invoices cannot be split per
            # contract, so this is loud: it is fixable by hand, a lost
            # payment is not.
            logger.exception("Could not map subscription items of %s", subscription_id)
    invoice = getattr(session, "invoice", None)
    outcome = await requests_service.apply_checkout(
        db, checkout=checkout, stripe_invoice_id=str(invoice) if invoice else None,
        stripe_subscription_id=subscription_id,
        stripe_customer_id=str(getattr(session, "customer", "") or "") or None,
        subscription_items=items,
    )

    plan = payment_plans.plan_by_key(checkout.payment_plan)
    if subscription_id and plan is not None and plan.instalments > 1:
        if len(items) < len(checkout.lines):
            outcome += "; ATTENZIONE: voci dell'abbonamento non abbinate a tutti i contratti"
        try:
            await _stop_subscription_after_last_instalment(
                secret_key=secret_key, subscription_id=subscription_id, instalments=plan.instalments
            )
        except Exception:
            logger.exception("Could not set cancel_at on subscription %s (checkout %s)", subscription_id, checkout.id)
            outcome += "; ATTENZIONE: cancel_at non impostato"
    return outcome


def _subscription_items_by_contract(*, secret_key: str, subscription_id: str) -> dict[str, str]:
    """contract id -> subscription item id, read from the metadata each line
    was created with."""
    subscription = stripe.Subscription.retrieve(
        subscription_id, api_key=secret_key, expand=["items.data.price.product"]
    )
    out = {}
    for item in subscription["items"]["data"]:
        product = item["price"]["product"]
        metadata = getattr(product, "metadata", None)
        contract_id = getattr(metadata, "contract_id", None) if metadata is not None else None
        if contract_id:
            out[str(contract_id)] = str(item["id"])
    return out


def _invoice_lines(*, secret_key: str, invoice) -> list[tuple[str, int]]:
    """(subscription item id, amount) for every line of an invoice. Always
    read from the API rather than from the event: a webhook payload carries
    only the first lines of an invoice, and a pratica can have twenty."""
    lines = stripe.Invoice.list_lines(str(invoice["id"]), api_key=secret_key, limit=100)
    out = []
    for line in lines.auto_paging_iter():
        item_id = getattr(line, "subscription_item", None)
        if not item_id:
            parent = getattr(line, "parent", None)
            details = getattr(parent, "subscription_item_details", None) if parent is not None else None
            item_id = getattr(details, "subscription_item", None) if details is not None else None
        if item_id:
            out.append((str(item_id), int(getattr(line, "amount", 0) or 0)))
    return out


async def stop_contract_billing(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, actor_user_id: uuid.UUID
) -> Contract:
    """Stops Stripe charging one contract every month -- a contract rejected
    or cancelled after the customer chose to pay in instalments.

    In a pratica only that contract's line leaves the subscription; the
    other contracts keep being charged. When it was the last line, or the
    subscription belonged to this contract alone, the subscription itself is
    cancelled. Refunds of what was already collected stay a deliberate human
    decision on the Stripe dashboard. Commits."""
    from app.domains.audit import service as audit_service

    if contract.stripe_subscription_id is None:
        raise PaymentsError("Questo contratto non ha addebiti mensili attivi.")
    if contract.billing_stopped_at is not None:
        raise PaymentsError("Gli addebiti di questo contratto sono già stati interrotti.")
    secret_key = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    if not secret_key:
        raise StripeNotConfiguredError("Stripe non è configurato per questa organizzazione.")

    siblings = list(
        (
            await db.execute(
                select(Contract).where(
                    Contract.organization_id == organization_id,
                    Contract.stripe_subscription_id == contract.stripe_subscription_id,
                    Contract.id != contract.id,
                    Contract.billing_stopped_at.is_(None),
                )
            )
        ).scalars()
    )
    try:
        if contract.stripe_subscription_item_id and siblings:
            stripe.SubscriptionItem.delete(
                contract.stripe_subscription_item_id, api_key=secret_key, proration_behavior="none"
            )
            action = "riga rimossa dall'abbonamento"
        else:
            stripe.Subscription.cancel(contract.stripe_subscription_id, api_key=secret_key)
            action = "abbonamento annullato"
    except stripe.error.StripeError as exc:
        raise PaymentsError(f"Stripe ha rifiutato l'operazione: {exc.user_message or exc}") from exc

    contract.billing_stopped_at = utcnow()
    contract.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="contract.billing_stopped", entity_type="contract", entity_id=str(contract.id),
        new_value={"subscription_id": contract.stripe_subscription_id, "action": action},
    )
    await db.commit()
    await db.refresh(contract)
    return contract


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
    """First payment of a contract landed: mark it paid, credit the LialCash,
    and -- for an instalment plan -- tell Stripe when to stop charging.

    If the documents are already approved the contract cascades to ACTIVE
    and commissions fire, exactly as an admin confirming a bank transfer
    does. If they are not (payment is accepted before approval), the
    payment is recorded and the contract waits for approval to activate."""
    from app.domains.contracts import service as contracts_service

    invoice = getattr(session, "invoice", None)
    contract = await contracts_service.mark_paid_via_stripe(
        db, organization_id=organization_id, stripe_checkout_session_id=session["id"],
        stripe_invoice_id=str(invoice) if invoice else None,
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
            if contract.status not in ("REJECTED", "CANCELLED"):
                await contracts_service.credit_contract_instalment_cashback(
                    db, organization_id=organization_id, contract=contract, instalment_ref="first"
                )
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


def _invoice_subscription_id(invoice) -> str | None:
    """Where an invoice says which subscription it belongs to.

    Stripe moved it: up to API 2025-03-31 it was `invoice.subscription`;
    from "basil" onwards (this account and SDK are on 2026-08-26.dahlia) it is
    `invoice.parent.subscription_details.subscription`, and the old field is
    simply absent. Reading only the old place made every monthly instalment
    look like an invoice with no subscription -- silently ignored: no
    cashback, no commissions, no failed-charge alert. Both are read so an
    endpoint pinned to either version works."""
    legacy = getattr(invoice, "subscription", None)
    if legacy:
        return str(legacy)
    parent = getattr(invoice, "parent", None)
    details = getattr(parent, "subscription_details", None) if parent is not None else None
    subscription = getattr(details, "subscription", None) if details is not None else None
    return str(subscription) if subscription else None


async def _subscription_is_shared(db: AsyncSession, *, organization_id: uuid.UUID, subscription_id: str) -> bool:
    """True when the subscription was opened by a pratica checkout -- its
    contracts carry a subscription item each. False for a contract paid on
    its own, whose single-line invoices need no splitting."""
    row = (
        await db.execute(
            select(Contract.id).where(
                Contract.organization_id == organization_id,
                Contract.stripe_subscription_id == subscription_id,
                Contract.stripe_subscription_item_id.is_not(None),
            ).limit(1)
        )
    ).first()
    return row is not None


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
        elif kind == "contract_request":
            outcome = await _handle_request_checkout(
                db, organization_id=organization_id, session=session, secret_key=secret_key
            )
            await _finish_event(db, row=event_row, outcome=outcome)
            return
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
        subscription_id = _invoice_subscription_id(invoice)
        if subscription_id:
            lines = None
            if await _subscription_is_shared(db, organization_id=organization_id, subscription_id=str(subscription_id)):
                # A pratica's subscription: the invoice is N lines for N
                # contracts, and each must reach its own contract.
                lines = _invoice_lines(secret_key=secret_key, invoice=invoice)
            outcome = await contracts_service.record_subscription_invoice(
                db,
                organization_id=organization_id,
                subscription_id=str(subscription_id),
                paid=event["type"] == "invoice.paid",
                amount_cents=int(getattr(invoice, "amount_paid", 0) or getattr(invoice, "amount_due", 0) or 0),
                invoice_id=str(invoice["id"]),
                billing_reason=getattr(invoice, "billing_reason", None),
                lines=lines,
            )
            await _finish_event(db, row=event_row, outcome=outcome)
            return

    await _finish_event(db, row=event_row, outcome=f"gestito: {event['type']}")
