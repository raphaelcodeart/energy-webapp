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
    kind: str  # "WALLET" | "ORDER_PAYMENT" | "REDEMPTION_PAYMENT"
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
    note: str | None = None
    # Populated on every row (admin view: whichever customer it belongs to;
    # customer's own view: always their own id/None name, since who else's
    # would it be). Lets the admin "Contabilità" screen filter by customer
    # and show per-customer totals without a second lookup.
    customer_user_id: uuid.UUID | None = None
    customer_display_name: str | None = None
    created_at: datetime
