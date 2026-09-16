import uuid
from datetime import datetime

from pydantic import BaseModel


class FinancialMovementRead(BaseModel):
    """One row in "Contabilità" -- a unified, read-only view merging a
    user's own wallet_transactions (LialCash) and their own paid orders'/
    credited invoice redemptions' real-money payments (EUR, Stripe or
    bonifico), computed on the fly by accounting/service.py::
    list_my_movements (one customer) or list_all_movements (admin, every
    customer, optionally filtered). Deliberately NOT a new table: every
    underlying source (WalletTransaction, Order, ImportedProductOrder,
    InvoiceRedemption) is already the single source of truth for its own
    domain, this just presents them together for bookkeeping."""

    id: str
    kind: str  # "WALLET" | "ORDER_PAYMENT" | "REDEMPTION_PAYMENT" | "CONTRACT_PAYMENT"
    # Raw WalletTransaction.type/source (both null for a real-money row) --
    # labels are a frontend concern, same as wallet-panel.tsx's own
    # TYPE_LABELS/SOURCE_LABELS maps already do for the wallet-only view.
    type: str | None = None
    source: str | None = None
    # Raw Order/InvoiceRedemption.payment_method (null for a WALLET row).
    payment_method: str | None = None
    # Signed for a WALLET row (negative = money left this wallet); always
    # positive for an ORDER_PAYMENT/REDEMPTION_PAYMENT row (a payment is
    # never negative).
    amount_cents: int
    currency: str  # "LIALCASH" | "EUR"
    # "What this movement is about" -- product name for an order-linked row,
    # partner name for an invoice-redemption-linked row (both the LialCash
    # credit rows AND, since Session 35, the REDEMPTION_PAYMENT row itself).
    product_name: str | None = None
    # Deliberately unified: an order placed for a manually-catalogued
    # product (orders.id) and one placed for an imported-catalog product
    # (imported_product_orders.id) are two different tables internally (see
    # imported_products/models.py -- kept apart only to isolate the product
    # CATALOG import mechanism), but from here on out -- order management,
    # accounting, "I miei Ordini" -- they are presented identically. Both
    # populate this same field; the frontend never needs to know or care
    # which table actually backs a given order id.
    order_id: uuid.UUID | None = None
    invoice_redemption_id: uuid.UUID | None = None
    #: A contract instalment paid (CONTRACT_PAYMENT, Session 54) or the
    #: LialCash cashback a contract earned (WALLET).
    contract_id: uuid.UUID | None = None
    contract_request_id: uuid.UUID | None = None
    note: str | None = None
    # Populated on every row (admin view: whichever customer it belongs to;
    # customer's own view: always their own id/None name, since who else's
    # would it be). Lets the admin "Contabilità" screen filter by customer
    # and show per-customer totals without a second lookup.
    customer_user_id: uuid.UUID | None = None
    customer_display_name: str | None = None
    created_at: datetime


class AccountingSummaryRead(BaseModel):
    """The totals at the top of "Contabilità" (Session 54), computed on the
    server from the same movements the list shows -- never added up again in
    the browser, so the cards and the list cannot disagree."""

    #: Real money paid, card + bank transfer, and its split.
    spent_total_cents: int = 0
    spent_card_cents: int = 0
    spent_bank_transfer_cents: int = 0
    spent_this_month_cents: int = 0
    spent_orders_cents: int = 0
    spent_redemptions_cents: int = 0
    spent_contracts_cents: int = 0
    payments_count: int = 0
    #: LialCash.
    lialcash_balance_cents: int = 0
    lialcash_received_cents: int = 0
    lialcash_spent_cents: int = 0
    cashback_received_cents: int = 0
    #: Contracts.
    contracts_active: int = 0
    instalments_paid: int = 0
    next_instalment_due_date: str | None = None
    next_instalment_cents: int | None = None
    #: Commissions, only for someone who is also a promoter (null otherwise).
    commissions_total_cents: int | None = None
    commissions_to_collect_cents: int | None = None
    commissions_paid_cents: int | None = None
    commissions_count: int | None = None


class DetailFact(BaseModel):
    label: str
    value: str
    mono: bool = False


class DetailEvent(BaseModel):
    label: str
    at: datetime | None = None
    by: str | None = None
    #: done / pending / warning -- how the step is drawn on the timeline.
    tone: str = "done"


class DetailInstalment(BaseModel):
    number: int
    instalments_total: int
    due_date: str
    amount_cents: int
    status: str
    paid_at: datetime | None = None
    source: str | None = None
    confirmed_by: str | None = None


class AccountingDetailRead(BaseModel):
    """Everything about one movement or one thing a movement refers to
    (an order, a cashback redemption, a contract), in one shape the detail
    popup draws the same way whatever it is: facts, a timeline with exact
    times and who did what, and -- for a contract -- its instalments."""

    ref: str
    kind: str  # WALLET / ORDER / REDEMPTION / CONTRACT
    title: str
    subtitle: str | None = None
    status: str | None = None
    #: success / warning / danger / neutral
    status_tone: str = "neutral"
    amount_cents: int | None = None
    currency: str = "EUR"
    direction: str | None = None  # in / out
    facts: list[DetailFact] = []
    timeline: list[DetailEvent] = []
    instalments: list[DetailInstalment] = []
    #: Refs of the things this one is tied to ("order:<id>", "contract:<id>").
    related_refs: list[str] = []
    #: Which dashboard tab manages it: orders / cashback / contracts / wallet.
    tab: str | None = None
    #: Order id / redemption id / contract id this detail is about, so the
    #: popup can list every movement of the same thing.
    order_id: uuid.UUID | None = None
    invoice_redemption_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
