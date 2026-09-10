import type { FinancialMovementRead } from "@/lib/types";

/** Shared formatting/labeling for every "Contabilità" screen (customer's
    own accounting-panel.tsx, admin's admin-accounting-panel.tsx) -- kept in
    one place so a movement reads identically everywhere it's shown. */

export function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

// LialCash is Lial Energy's internal wallet credit, never plain EUR.
export function lialCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} LialCash`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { dateStyle: "medium", timeStyle: "short" });
}

export function shortCode(id: string): string {
  return id.slice(0, 8).toUpperCase();
}

const PAYMENT_METHOD_LABELS: Record<string, string> = {
  BANK_TRANSFER: "Bonifico",
  CARD: "Carta (Stripe)",
};

const SOURCE_LABELS: Record<string, string> = {
  MANUAL_ADMIN: "Ricarica manuale",
  INVOICE_REDEMPTION_BASE: "Riscatto fattura",
  INVOICE_REDEMPTION_BONUS: "Bonus 5% riscatto fattura",
  ORDER_CASHBACK_BASE: "Cashback ordine",
  ORDER_CASHBACK_BONUS: "Bonus 5% cashback ordine",
};

const TYPE_LABELS: Record<string, string> = {
  ADMIN_CREDIT: "Ricarica/Cashback",
  TRANSFER: "Trasferimento",
  PURCHASE_DEBIT: "Pagamento con LialCash",
  REVERSAL: "Storno",
};

const CASHBACK_SOURCES = new Set([
  "ORDER_CASHBACK_BASE", "ORDER_CASHBACK_BONUS", "INVOICE_REDEMPTION_BASE", "INVOICE_REDEMPTION_BONUS",
]);

/** Whether a movement put money IN the customer's pocket/wallet ("entrata")
    or took it OUT ("uscita") -- the single most important thing to see at
    a glance on a bookkeeping screen. A WALLET row's sign already encodes
    this (see accounting/service.py). An ORDER_PAYMENT/REDEMPTION_PAYMENT
    row is always real money the customer spent from their own bank/card --
    an outflow -- even though amount_cents is stored positive (a payment is
    never negative, see FinancialMovementRead's docstring): the direction
    has to be inferred from `kind`, not the raw sign, for those two. */
export function movementDirection(m: FinancialMovementRead): "in" | "out" {
  if (m.kind === "ORDER_PAYMENT" || m.kind === "REDEMPTION_PAYMENT") return "out";
  return m.amount_cents < 0 ? "out" : "in";
}

export function movementSignedAmountCents(m: FinancialMovementRead): number {
  const abs = Math.abs(m.amount_cents);
  return movementDirection(m) === "out" ? -abs : abs;
}

/** Coarse category for a dedicated "Tipo" column -- exactly the
    "pagamento / ricarica / altro" grouping requested, kept separate from
    the more detailed movementLabel() below. */
export function movementCategory(m: FinancialMovementRead): "Ricarica" | "Cashback" | "Pagamento" | "Trasferimento" | "Storno" | "Altro" {
  if (m.kind === "ORDER_PAYMENT" || m.kind === "REDEMPTION_PAYMENT") return "Pagamento";
  if (m.type === "PURCHASE_DEBIT") return "Pagamento";
  if (m.type === "TRANSFER") return "Trasferimento";
  if (m.type === "REVERSAL") return "Storno";
  if (m.type === "ADMIN_CREDIT") return m.source && CASHBACK_SOURCES.has(m.source) ? "Cashback" : "Ricarica";
  return "Altro";
}

/** The detailed, human-readable description of what the movement actually
    is -- "Bonus 5% riscatto fattura", "Pagamento riscatto (Carta)", etc. */
export function movementLabel(m: FinancialMovementRead): string {
  if (m.kind === "ORDER_PAYMENT") {
    const method = m.payment_method ? PAYMENT_METHOD_LABELS[m.payment_method] ?? m.payment_method : null;
    return method ? `Pagamento ordine (${method})` : "Pagamento ordine";
  }
  if (m.kind === "REDEMPTION_PAYMENT") {
    const method = m.payment_method ? PAYMENT_METHOD_LABELS[m.payment_method] ?? m.payment_method : null;
    return method ? `Pagamento riscatto fattura (${method})` : "Pagamento riscatto fattura";
  }
  const sourceLabel = m.source ? SOURCE_LABELS[m.source] : undefined;
  return sourceLabel ?? (m.type ? TYPE_LABELS[m.type] ?? m.type : "Movimento wallet");
}

/** Clickable-chip target for a movement's order_id/invoice_redemption_id --
    both order tables (regular + imported-products, unified server-side
    into the same order_id, see FinancialMovementRead's docstring) land on
    "I miei Ordini"; a redemption lands on "Riscatta Cashback". basePath
    lets the same helper serve both the customer and promoter dashboards
    (admin has no such deep-linking, so admin screens don't call this). */
export function movementReferenceLink(m: FinancialMovementRead, basePath: "/customer" | "/promoter"): { label: string; href: string } | null {
  if (m.order_id) return { label: `Ordine #${shortCode(m.order_id)}`, href: `${basePath}?tab=orders` };
  if (m.invoice_redemption_id) return { label: `Riscatto #${shortCode(m.invoice_redemption_id)}`, href: `${basePath}?tab=cashback` };
  return null;
}
