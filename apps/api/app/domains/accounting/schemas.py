import uuid
from datetime import datetime

from pydantic import BaseModel


class FinancialMovementRead(BaseModel):
    """One row in "Contabilità" -- a unified, read-only view merging a
    user's own wallet_transactions (LialCash) and their own paid orders'
    real-money payments (EUR, Stripe or bonifico), computed on the fly by
    accounting/service.py::list_my_movements. Deliberately NOT a new table:
    both underlying sources (WalletTransaction, Order) are already the
    single source of truth for their own domain, this just presents them
    together for the customer's own bookkeeping."""

    id: str
    kind: str  # "WALLET" | "ORDER_PAYMENT"
    # Raw WalletTransaction.type/source (both null for an ORDER_PAYMENT row)
    # -- labels are a frontend concern, same as wallet-panel.tsx's own
    # TYPE_LABELS/SOURCE_LABELS maps already do for the wallet-only view.
    type: str | None = None
    source: str | None = None
    # Raw Order.payment_method (null for a WALLET row).
    payment_method: str | None = None
    # Signed for a WALLET row (negative = money left this wallet); always
    # positive for an ORDER_PAYMENT row (a payment is never negative).
    amount_cents: int
    currency: str  # "LIALCASH" | "EUR"
    product_name: str | None = None
    order_id: uuid.UUID | None = None
    note: str | None = None
    created_at: datetime
