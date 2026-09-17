"""Il dettaglio di un movimento, e di ciò a cui si riferisce (Session 54).

"Contabilità" lists movements; clicking one -- or the order, cashback
redemption or contract it points to -- opens everything there is to know
about it: what, how much, how it was paid, and a timeline with the exact
time of every step and who did it (created, receipt uploaded, payment
confirmed by Stripe or by an administrator, cashback credited...).

One entry point, `build_detail(ref)`, for one shape (AccountingDetailRead),
whatever the ref names:

- ``wallet:<transaction id>`` -- a LialCash movement;
- ``order:<id>`` -- a Shop order, regular or imported-products (two tables,
  one kind: same rule as the rest of accounting);
- ``redemption:<id>`` -- a cashback redemption of a partner invoice;
- ``contract:<id>`` -- a Lial Energy contract and its instalments.

`owner_user_id` scopes everything to one customer's own things; None is the
administrator's view. Anything that does not belong to the owner is simply
not found -- never a hint that it exists.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.catalog.models import ProductVersion
from app.domains.wallets.service import _resolve_display_names

PAYMENT_METHOD_LABELS = {"CARD": "Carta (Stripe)", "BANK_TRANSFER": "Bonifico"}

ORDER_STATUS = {
    "AWAITING_PAYMENT": ("In attesa di pagamento", "warning"),
    "PAID": ("Pagato", "success"),
    "CANCELLED": ("Annullato", "danger"),
}
REDEMPTION_STATUS = {
    "SUBMITTED": ("Inviata", "warning"),
    "VERIFIED": ("Verificata, da pagare", "warning"),
    "PAYMENT_PENDING": ("In attesa di pagamento", "warning"),
    "CREDITED": ("Accreditata", "success"),
    "REJECTED": ("Respinta", "danger"),
}
CONTRACT_STATUS = {
    "DRAFT": "Bozza", "SUBMITTED": "Inviato", "DOCUMENTS_PENDING": "Documenti mancanti",
    "UNDER_REVIEW": "In revisione", "APPROVED": "Approvato", "PAYMENT_PENDING": "In attesa di pagamento",
    "PAID": "Pagato", "ACTIVATION_PENDING": "In attivazione", "ACTIVE": "Attivo", "SUSPENDED": "Sospeso",
    "CANCELLED": "Cessato", "EXPIRED": "Scaduto", "RENEWED": "Rinnovato", "REJECTED": "Respinto",
}
WALLET_TYPE_LABELS = {
    "ADMIN_CREDIT": "Accredito",
    "TRANSFER": "Trasferimento",
    "PURCHASE_DEBIT": "Pagamento con LialCash",
    "REVERSAL": "Storno",
}
WALLET_SOURCE_LABELS = {
    "MANUAL_ADMIN": "Ricarica manuale",
    "WELCOME_BONUS": "Omaggio di benvenuto",
    "INVOICE_REDEMPTION_BASE": "Riscatto fattura",
    "INVOICE_REDEMPTION_BONUS": "Bonus 5% riscatto fattura",
    "ORDER_CASHBACK_BASE": "Cashback ordine",
    "ORDER_CASHBACK_BONUS": "Bonus 5% cashback ordine",
    "CONTRACT_CASHBACK": "Cashback contratto Lial Energy",
}
INSTALMENT_SOURCE_LABELS = {
    "STRIPE_CHECKOUT": "Carta, al pagamento (Stripe)",
    "STRIPE_INVOICE": "Carta, addebito automatico mensile (Stripe)",
    "ADMIN": "Confermata dall'amministrazione",
}
PLAN_LABELS = {"FULL": "Soluzione unica", "INSTALMENTS_3": "3 rate mensili", "MONTHLY_12": "12 rate mensili"}


class DetailNotFoundError(Exception):
    pass


def _code(value: uuid.UUID) -> str:
    return str(value)[:8].upper()


def _euro(cents: int | None) -> str:
    if cents is None:
        return "—"
    return f"{cents / 100:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _fact(label: str, value: object, mono: bool = False) -> dict | None:
    if value is None or value == "":
        return None
    return {"label": label, "value": str(value), "mono": mono}


def _event(label: str, at: datetime | None, by: str | None = None, tone: str = "done") -> dict:
    # Some older columns are timestamp WITHOUT time zone and come back naive;
    # they were always written in UTC. Made aware here, or sorting a
    # timeline that mixes them with aware ones fails.
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return {"label": label, "at": at, "by": by, "tone": tone}


async def _names(db: AsyncSession, organization_id: uuid.UUID, *user_ids: uuid.UUID | None) -> dict[uuid.UUID, str]:
    ids = {u for u in user_ids if u is not None}
    return await _resolve_display_names(db, organization_id=organization_id, user_ids=ids) if ids else {}


def _clean(detail: dict) -> dict:
    detail["facts"] = [f for f in detail.get("facts", []) if f is not None]
    detail["timeline"] = sorted(
        detail.get("timeline", []), key=lambda e: (e["at"] is None, e["at"] or datetime.max.replace(tzinfo=UTC))
    )
    return detail


async def build_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, ref: str, owner_user_id: uuid.UUID | None
) -> dict:
    kind, _, raw_id = ref.partition(":")
    try:
        entity_id = uuid.UUID(raw_id)
    except ValueError as exc:
        raise DetailNotFoundError(ref) from exc
    builders = {
        "wallet": _wallet_detail,
        "order": _order_detail,
        "redemption": _redemption_detail,
        "contract": _contract_detail,
    }
    builder = builders.get(kind)
    if builder is None:
        raise DetailNotFoundError(ref)
    detail = await builder(db, organization_id=organization_id, entity_id=entity_id, owner_user_id=owner_user_id)
    return _clean({"ref": f"{kind}:{entity_id}", **detail})


# --- LialCash -------------------------------------------------------------------


async def _wallet_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, entity_id: uuid.UUID, owner_user_id: uuid.UUID | None
) -> dict:
    from app.domains.wallets.models import Wallet, WalletTransaction

    txn = await db.get(WalletTransaction, entity_id)
    if txn is None or txn.organization_id != organization_id:
        raise DetailNotFoundError()
    from_wallet = await db.get(Wallet, txn.from_wallet_id) if txn.from_wallet_id else None
    to_wallet = await db.get(Wallet, txn.to_wallet_id) if txn.to_wallet_id else None
    if owner_user_id is not None and owner_user_id not in {
        from_wallet.user_id if from_wallet else None, to_wallet.user_id if to_wallet else None
    }:
        raise DetailNotFoundError()
    names = await _names(
        db, organization_id, from_wallet.user_id if from_wallet else None,
        to_wallet.user_id if to_wallet else None, txn.actor_user_id,
    )
    outgoing = (
        from_wallet is not None and (owner_user_id is None and to_wallet is None or from_wallet.user_id == owner_user_id)
    )
    title = WALLET_SOURCE_LABELS.get(txn.source or "") or WALLET_TYPE_LABELS.get(txn.type, "Movimento LialCash")
    related = []
    txn_order_id = txn.reference_order_id or txn.reference_imported_order_id or txn.reference_cj_order_id
    if txn_order_id:
        related.append(f"order:{txn_order_id}")
    if txn.reference_invoice_redemption_id:
        related.append(f"redemption:{txn.reference_invoice_redemption_id}")
    if txn.reference_contract_id:
        related.append(f"contract:{txn.reference_contract_id}")
    return {
        "kind": "WALLET",
        "title": title,
        "subtitle": txn.note,
        "status": "Registrato",
        "status_tone": "success",
        "amount_cents": txn.amount_cents,
        "currency": "LIALCASH",
        "direction": "out" if outgoing else "in",
        "facts": [
            _fact("Tipo", WALLET_TYPE_LABELS.get(txn.type, txn.type)),
            _fact("Origine", WALLET_SOURCE_LABELS.get(txn.source or "")),
            _fact("Da", f"{names.get(from_wallet.user_id, '—')} · {from_wallet.address}" if from_wallet else None),
            _fact("A", f"{names.get(to_wallet.user_id, '—')} · {to_wallet.address}" if to_wallet else None),
            _fact("Ordine", f"#{_code(txn_order_id)}") if txn_order_id else None,
            _fact("Riscatto", f"#{_code(txn.reference_invoice_redemption_id)}") if txn.reference_invoice_redemption_id else None,
            _fact("Contratto", f"#{_code(txn.reference_contract_id)}") if txn.reference_contract_id else None,
            _fact("Storna il movimento", _code(txn.reverses_transaction_id), mono=True) if txn.reverses_transaction_id else None,
            _fact("Nota", txn.note),
            _fact("ID movimento", txn.id, mono=True),
        ],
        "timeline": [
            _event("Movimento registrato sul wallet", txn.created_at,
                   by=names.get(txn.actor_user_id) if txn.actor_user_id else "Automatico"),
        ],
        "related_refs": related,
        "tab": "wallet",
        "order_id": txn_order_id,
        "invoice_redemption_id": txn.reference_invoice_redemption_id,
        "contract_id": txn.reference_contract_id,
    }


# --- Ordini -----------------------------------------------------------------------


async def _order_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, entity_id: uuid.UUID, owner_user_id: uuid.UUID | None
) -> dict:
    from app.domains.cj_dropshipping.models import CjOrder
    from app.domains.imported_products.models import ImportedProduct, ImportedProductOrder
    from app.domains.orders.models import Order

    cj_order = await db.get(CjOrder, entity_id)
    if cj_order is not None:
        return await _cj_order_detail(db, organization_id=organization_id, order=cj_order, owner_user_id=owner_user_id)
    order = await db.get(Order, entity_id)
    product_name = None
    cashback_surcharge = 0
    cashback_credited_at = None
    cashback_requested = False
    if order is not None:
        version = await db.get(ProductVersion, order.product_version_id)
        product_name = version.name if version else None
        cashback_surcharge = order.cashback_surcharge_cents or 0
        cashback_credited_at = order.cashback_credited_at
        cashback_requested = order.cashback_requested
        catalog = "Shop"
    else:
        order = await db.get(ImportedProductOrder, entity_id)
        if order is not None:
            product = await db.get(ImportedProduct, order.imported_product_id)
            product_name = product.name if product else None
        catalog = "Acquisti LialEnergy"
    if order is None or order.organization_id != organization_id:
        raise DetailNotFoundError()
    if owner_user_id is not None and order.customer_user_id != owner_user_id:
        raise DetailNotFoundError()

    names = await _names(
        db, organization_id, order.customer_user_id, order.created_by_user_id, order.paid_by_user_id,
        order.cancelled_by_user_id,
    )
    paid_cents = order.amount_cents - order.credit_applied_cents + cashback_surcharge
    status_label, tone = ORDER_STATUS.get(order.status, (order.status, "neutral"))
    card = order.payment_method == "CARD"
    timeline = [
        _event("Ordine creato", order.created_at, by=names.get(order.created_by_user_id)),
    ]
    if order.payment_proof_uploaded_at:
        timeline.append(_event(
            "Ricevuta del bonifico caricata", order.payment_proof_uploaded_at,
            by=order.payment_proof_original_filename,
        ))
    if order.paid_at:
        timeline.append(_event(
            "Pagamento confermato", order.paid_at,
            by="Stripe (automatico)" if card and order.paid_by_user_id is None else names.get(order.paid_by_user_id),
        ))
    elif order.status == "AWAITING_PAYMENT":
        timeline.append(_event("In attesa del pagamento", None, tone="pending"))
    if cashback_credited_at:
        timeline.append(_event("Cashback accreditato", cashback_credited_at))
    if order.cancelled_at:
        timeline.append(_event(
            "Ordine annullato", order.cancelled_at, by=names.get(order.cancelled_by_user_id), tone="warning"
        ))
    return {
        "kind": "ORDER",
        "title": product_name or "Ordine",
        "subtitle": f"Ordine #{_code(order.id)} · {catalog}",
        "status": status_label,
        "status_tone": tone,
        "amount_cents": order.amount_cents,
        "currency": "EUR",
        "direction": "out",
        "facts": [
            _fact("Cliente", names.get(order.customer_user_id)) if owner_user_id is None else None,
            _fact("Prezzo", _euro(order.amount_cents)),
            _fact("Pagato con LialCash", _euro(order.credit_applied_cents)) if order.credit_applied_cents else None,
            _fact("Supplemento cashback", _euro(cashback_surcharge)) if cashback_surcharge else None,
            _fact("Pagato in euro", _euro(paid_cents)),
            _fact("Metodo", PAYMENT_METHOD_LABELS.get(order.payment_method, order.payment_method)),
            _fact("Cashback richiesto", "Sì" if cashback_requested else None),
            _fact("Ricevuta bonifico", order.payment_proof_original_filename),
            _fact("Sessione Stripe", order.stripe_checkout_session_id, mono=True),
            _fact("Motivo annullamento", getattr(order, "cancellation_reason", None)),
            _fact("Nota", order.note),
            _fact("ID ordine", order.id, mono=True),
        ],
        "timeline": timeline,
        "related_refs": [],
        "tab": "orders",
        "order_id": order.id,
    }


async def _cj_order_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, order, owner_user_id: uuid.UUID | None
) -> dict:
    """A Shop Lial Partner order: the same payment story as any order, plus
    shipping -- where it goes, when it left, tracking, delivery."""
    from app.domains.cj_dropshipping import service as cj_service
    from app.domains.cj_dropshipping.models import CjProduct, CjVariant

    if order.organization_id != organization_id:
        raise DetailNotFoundError()
    if owner_user_id is not None and order.customer_user_id != owner_user_id:
        raise DetailNotFoundError()
    product = await db.get(CjProduct, order.cj_product_id)
    variant = await db.get(CjVariant, order.cj_variant_id)
    names = await _names(
        db, organization_id, order.customer_user_id, order.created_by_user_id, order.paid_by_user_id,
        order.cancelled_by_user_id, order.forwarded_by_user_id,
    )
    status_label, tone = ORDER_STATUS.get(order.status, (order.status, "neutral"))
    card = order.payment_method == "CARD"
    timeline = [_event("Ordine creato", order.created_at, by=names.get(order.created_by_user_id))]
    if order.payment_proof_uploaded_at:
        timeline.append(_event(
            "Ricevuta del bonifico caricata", order.payment_proof_uploaded_at, by=order.payment_proof_original_filename
        ))
    if order.paid_at:
        timeline.append(_event(
            "Pagamento confermato", order.paid_at,
            by="Stripe (automatico)" if card and order.paid_by_user_id is None else names.get(order.paid_by_user_id),
        ))
    elif order.status == "AWAITING_PAYMENT":
        timeline.append(_event("In attesa del pagamento", None, tone="pending"))
    if order.cancelled_at:
        timeline.append(_event(
            "Ordine annullato", order.cancelled_at, by=names.get(order.cancelled_by_user_id), tone="warning"
        ))
    if order.status == "PAID":
        # The customer sees "received" until the supplier is paid, whatever
        # the reason (Session 63); staff see the supplier side step by step.
        if owner_user_id is None:
            if order.forwarded_at and order.cj_order_id:
                timeline.append(_event("Creato su CJ", order.forwarded_at, by=names.get(order.forwarded_by_user_id) or "Automatico"))
            if order.cj_payment_status == "PAYMENT_REQUIRED":
                timeline.append(_event("Pagamento CJ richiesto", None, tone="warning"))
            elif order.fulfillment_status == "ERROR":
                timeline.append(_event("Invio a CJ non riuscito", None, by=order.forward_error, tone="warning"))
        if order.cj_paid_at:
            timeline.append(_event(
                "In preparazione" if owner_user_id is not None else "Pagato su CJ: in preparazione", order.cj_paid_at
            ))
        else:
            timeline.append(_event("Ordine ricevuto: in attesa di preparazione", None, tone="pending"))
        if order.shipped_at:
            timeline.append(_event("Spedito", order.shipped_at, by=order.tracking_number))
        elif order.fulfillment_status != "CJ_CANCELLED":
            timeline.append(_event("Spedizione", None, tone="pending"))
        if order.delivered_at:
            timeline.append(_event("Consegnato", order.delivered_at))
        if order.fulfillment_status == "CJ_CANCELLED":
            timeline.append(_event("Annullato dal fornitore", order.last_cj_sync_at, tone="warning"))
    address = f"{order.recipient_name}, {order.address_line1}{', ' + order.address_line2 if order.address_line2 else ''}, {order.postal_code} {order.city} ({order.province})"
    admin_facts = [] if owner_user_id is not None else [
        _fact("Cliente", names.get(order.customer_user_id)),
        _fact("Ordine CJ", order.cj_order_id, mono=True),
        _fact("Stato su CJ", order.cj_order_status),
        _fact("Pagamento CJ", order.cj_payment_status),
        _fact("Costo CJ reale (USD)", f"{order.cj_amount_usd:.2f}" if order.cj_amount_usd is not None else None),
        _fact("Corriere", order.logistic_name),
        _fact("Costo CJ stimato (USD)", f"{order.unit_cost_usd * order.quantity + order.shipping_cost_usd:.2f}"),
        _fact("Sandbox", "Sì" if order.sandbox else None),
        _fact("Errore invio", order.forward_error),
    ]
    return {
        "kind": "ORDER",
        "title": product.name if product else "Ordine",
        # The customer never sees where a product comes from (Session 62).
        "subtitle": f"Ordine #{_code(order.id)} · "
        + ("Marketplace 1" if owner_user_id is not None else "Shop Lial Partner (CJ)"),
        "status": status_label,
        "status_tone": tone,
        "amount_cents": order.amount_cents,
        "currency": "EUR",
        "direction": "out",
        "facts": [
            *admin_facts,
            _fact("Variante", variant.label if variant else None),
            _fact("Quantità", order.quantity),
            _fact("Prezzo unitario", _euro(order.unit_price_cents)),
            _fact("Spedizione", _euro(order.shipping_cents) if order.shipping_cents else "Inclusa"),
            _fact("Totale", _euro(order.amount_cents)),
            _fact("Pagato con LialCash", _euro(order.credit_applied_cents)) if order.credit_applied_cents else None,
            _fact("Pagato in euro", _euro(order.amount_cents - order.credit_applied_cents)),
            _fact("Metodo", PAYMENT_METHOD_LABELS.get(order.payment_method, order.payment_method)),
            _fact("Consegna a", address),
            _fact("Tempi di consegna stimati", f"{order.shipping_days} giorni" if order.shipping_days else None),
            _fact("Tracking", order.tracking_number, mono=True),
            _fact("Segui la spedizione", cj_service.tracking_url(order.tracking_number)),
            _fact("Ricevuta bonifico", order.payment_proof_original_filename),
            _fact("Motivo annullamento", order.cancellation_reason),
            _fact("Nota", order.note),
            _fact("ID ordine", order.id, mono=True),
        ],
        "timeline": timeline,
        "related_refs": [],
        "tab": "orders",
        "order_id": order.id,
    }


# --- Riscatti cashback ------------------------------------------------------------------


async def _redemption_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, entity_id: uuid.UUID, owner_user_id: uuid.UUID | None
) -> dict:
    from app.domains.invoice_redemptions.models import InvoiceRedemption
    from app.domains.partners.models import Partner

    redemption = await db.get(InvoiceRedemption, entity_id)
    if redemption is None or redemption.organization_id != organization_id:
        raise DetailNotFoundError()
    if owner_user_id is not None and redemption.customer_user_id != owner_user_id:
        raise DetailNotFoundError()
    partner = await db.get(Partner, redemption.partner_id)
    names = await _names(
        db, organization_id, redemption.customer_user_id, redemption.verified_by_user_id,
        redemption.credited_by_user_id,
    )
    from app.domains.invoice_redemptions.service import payment_due_cents

    due = payment_due_cents(redemption.confirmed_amount_cents)
    status_label, tone = REDEMPTION_STATUS.get(redemption.status, (redemption.status, "neutral"))
    card = redemption.payment_method == "CARD"
    timeline = [_event("Fattura inviata", redemption.created_at, by=names.get(redemption.customer_user_id))]
    if redemption.verified_at:
        timeline.append(_event("Fattura verificata", redemption.verified_at, by=names.get(redemption.verified_by_user_id)))
    if redemption.payment_proof_uploaded_at:
        timeline.append(_event(
            "Ricevuta del bonifico caricata", redemption.payment_proof_uploaded_at,
            by=redemption.payment_proof_original_filename,
        ))
    if redemption.credited_at:
        timeline.append(_event(
            "Pagamento confermato e LialCash accreditati", redemption.credited_at,
            by="Stripe (automatico)" if card and redemption.credited_by_user_id is None
            else names.get(redemption.credited_by_user_id),
        ))
    elif redemption.status not in ("REJECTED",):
        timeline.append(_event("In attesa di completamento", None, tone="pending"))
    if redemption.status == "REJECTED":
        timeline.append(_event("Respinta", redemption.verified_at, by=names.get(redemption.verified_by_user_id), tone="warning"))
    return {
        "kind": "REDEMPTION",
        "title": f"Riscatto cashback{f' · {partner.name}' if partner else ''}",
        "subtitle": f"Riscatto #{_code(redemption.id)}",
        "status": status_label,
        "status_tone": tone,
        "amount_cents": due if due is not None else redemption.confirmed_amount_cents or redemption.declared_amount_cents,
        "currency": "EUR",
        "direction": "out",
        "facts": [
            _fact("Cliente", names.get(redemption.customer_user_id)) if owner_user_id is None else None,
            _fact("Partner", partner.name if partner else None),
            _fact("Importo fattura dichiarato", _euro(redemption.declared_amount_cents)),
            _fact("Importo fattura confermato", _euro(redemption.confirmed_amount_cents))
            if redemption.confirmed_amount_cents else None,
            _fact("Quota pagata per il riscatto", _euro(due)) if due else None,
            _fact("Metodo", PAYMENT_METHOD_LABELS.get(redemption.payment_method or "")),
            _fact("Causale bonifico", redemption.payment_reference_code, mono=True),
            _fact("Fattura caricata", redemption.original_filename),
            _fact("Ricevuta bonifico", redemption.payment_proof_original_filename),
            _fact("Sessione Stripe", redemption.stripe_checkout_session_id, mono=True),
            _fact("Motivo del rifiuto", redemption.rejection_reason),
            _fact("ID riscatto", redemption.id, mono=True),
        ],
        "timeline": timeline,
        "related_refs": [],
        "tab": "cashback",
        "invoice_redemption_id": redemption.id,
    }


# --- Contratti --------------------------------------------------------------------------


async def _contract_detail(
    db: AsyncSession, *, organization_id: uuid.UUID, entity_id: uuid.UUID, owner_user_id: uuid.UUID | None
) -> dict:
    from app.domains.contracts.models import Contract, ContractInstalment, ContractStatusHistory
    from app.domains.customers.models import Address, Customer, SupplyPoint

    contract = await db.get(Contract, entity_id)
    if contract is None or contract.organization_id != organization_id:
        raise DetailNotFoundError()
    customer = await db.get(Customer, contract.customer_id)
    if owner_user_id is not None and (customer is None or customer.user_id != owner_user_id):
        raise DetailNotFoundError()
    version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
    supply_point = await db.get(SupplyPoint, contract.supply_point_id)
    address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
    instalments = list(
        (
            await db.execute(
                select(ContractInstalment)
                .where(ContractInstalment.contract_id == contract.id)
                .order_by(ContractInstalment.number)
            )
        ).scalars()
    )
    history = list(
        (
            await db.execute(
                select(ContractStatusHistory)
                .where(ContractStatusHistory.contract_id == contract.id)
                .order_by(ContractStatusHistory.created_at)
            )
        ).scalars()
    )
    names = await _names(
        db, organization_id, customer.user_id if customer else None,
        *[h.actor_user_id for h in history], *[i.confirmed_by_user_id for i in instalments],
    )
    paid = [i for i in instalments if i.status == "PAID"]
    status = CONTRACT_STATUS.get(contract.status, contract.status)
    tone = (
        "success" if contract.status in ("ACTIVE", "RENEWED")
        else "danger" if contract.status in ("REJECTED", "CANCELLED", "SUSPENDED")
        else "warning"
    )

    # The steps that matter for money and activation, not every hop of the
    # state machine (the automatic cascades would triple the list).
    milestones = {
        "SUBMITTED": "Contratto inviato",
        "UNDER_REVIEW": "Documenti completi, in revisione",
        "APPROVED": "Approvato dall'amministrazione",
        "ACTIVE": "Contratto attivo",
        "REJECTED": "Respinto",
        "SUSPENDED": "Sospeso",
        "CANCELLED": "Cessato",
        "RENEWED": "Rinnovato",
    }
    timeline = [_event("Contratto creato", contract.created_at)]
    for h in history:
        if h.to_status in milestones:
            timeline.append(_event(
                milestones[h.to_status], h.created_at,
                by=names.get(h.actor_user_id) if h.reason != "Automatico -- nessuna decisione separata richiesta" else "Automatico",
                tone="warning" if h.to_status in ("REJECTED", "SUSPENDED", "CANCELLED") else "done",
            ))
    for i in paid:
        timeline.append(_event(
            f"Pagamento {'' if i.instalments_total == 1 else f'rata {i.number}/{i.instalments_total} '}ricevuto · {_euro(i.amount_cents)}",
            i.paid_at,
            by=INSTALMENT_SOURCE_LABELS.get(i.payment_source or "")
            + (f" ({names.get(i.confirmed_by_user_id)})" if i.confirmed_by_user_id else ""),
        ))
    for i in instalments:
        if i.status == "FAILED":
            timeline.append(_event(f"Rata {i.number} non addebitata", None, tone="warning"))
    if contract.cashback_credited_at:
        timeline.append(_event("Cashback LialCash accreditato", contract.cashback_credited_at))
    if contract.billing_stopped_at:
        timeline.append(_event("Addebiti mensili interrotti", contract.billing_stopped_at, tone="warning"))
    next_due = next((i for i in instalments if i.status == "SCHEDULED"), None)
    if next_due is not None and contract.billing_stopped_at is None:
        timeline.append(_event(
            f"Prossima rata {next_due.number}/{next_due.instalments_total} · {_euro(next_due.amount_cents)} "
            f"prevista il {next_due.due_date.strftime('%d/%m/%Y')}",
            None, tone="pending",
        ))

    point = (
        f"POD {supply_point.pod_code}" if supply_point and supply_point.pod_code
        else f"PDR {supply_point.pdr_code}" if supply_point and supply_point.pdr_code
        else None
    )
    return {
        "kind": "CONTRACT",
        "title": version.name if version else "Contratto Lial Energy",
        "subtitle": f"Contratto #{_code(contract.id)} · pratica #{_code(contract.contract_request_id)}",
        "status": status,
        "status_tone": tone,
        "amount_cents": contract.gross_amount_cents,
        "currency": "EUR",
        "direction": "out",
        "facts": [
            _fact("Cliente", names.get(customer.user_id) if customer and customer.user_id else None)
            if owner_user_id is None else None,
            _fact("Intestatario", " ".join(x for x in (contract.holder_first_name, contract.holder_last_name) if x)),
            _fact("Punto di fornitura", point),
            _fact("Indirizzo", f"{address.street}, {address.postal_code} {address.city} ({address.province})" if address else None),
            _fact("Totale contratto", _euro(contract.gross_amount_cents)),
            _fact("IVA", f"{contract.vat_rate}% · {_euro(contract.vat_amount_cents)}") if contract.vat_amount_cents else None,
            _fact("Modalità di pagamento", PLAN_LABELS.get(contract.payment_plan or "")),
            _fact("Pagato finora", f"{_euro(sum(i.amount_cents for i in paid))} · {len(paid)}/{len(instalments)} "
                  f"{'rate' if len(instalments) != 1 else 'pagamento'}") if instalments else None,
            _fact("Attivo dal", contract.activated_at.strftime("%d/%m/%Y") if contract.activated_at else None),
            _fact("Scadenza", contract.expires_at.strftime("%d/%m/%Y") if contract.expires_at else None),
            _fact("IBAN", contract.iban, mono=True),
            _fact("Abbonamento Stripe", contract.stripe_subscription_id, mono=True),
            _fact("ID contratto", contract.id, mono=True),
        ],
        "timeline": timeline,
        "instalments": [
            {
                "number": i.number,
                "instalments_total": i.instalments_total,
                "due_date": i.due_date.isoformat(),
                "amount_cents": i.amount_cents,
                "status": i.status,
                "paid_at": i.paid_at,
                "source": INSTALMENT_SOURCE_LABELS.get(i.payment_source or ""),
                "confirmed_by": names.get(i.confirmed_by_user_id) if i.confirmed_by_user_id else None,
            }
            for i in instalments
        ],
        "related_refs": [],
        "tab": "contracts",
        "contract_id": contract.id,
    }
