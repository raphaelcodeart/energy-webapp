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

/** Down to the second -- for a payment timeline, where "when exactly was it
    confirmed" is the whole question. */
export function formatDateTimeFull(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

/** "12 set" / "09:41" -- the compact date and time of a list row. */
export function formatDayShort(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

/** "settembre 2026" -- the month a list group is headed by. */
export function monthKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function monthLabel(key: string): string {
  const [year, month] = key.split("-").map(Number);
  const label = new Date(year!, month! - 1, 1).toLocaleDateString("it-IT", { month: "long", year: "numeric" });
  return label.charAt(0).toUpperCase() + label.slice(1);
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
  WELCOME_BONUS: "Omaggio di benvenuto",
  INVOICE_REDEMPTION_BASE: "Riscatto fattura",
  INVOICE_REDEMPTION_BONUS: "Bonus 5% riscatto fattura",
  ORDER_CASHBACK_BASE: "Cashback ordine",
  ORDER_CASHBACK_BONUS: "Bonus 5% cashback ordine",
  // Automatic, surcharge-free credit on a paid Lial Energy contract --
  // deliberately a different rule from the two 5% ones above.
  CONTRACT_CASHBACK: "Cashback contratto Lial Energy",
};

const TYPE_LABELS: Record<string, string> = {
  ADMIN_CREDIT: "Ricarica/Cashback",
  TRANSFER: "Trasferimento",
  PURCHASE_DEBIT: "Pagamento con LialCash",
  REVERSAL: "Storno",
};

const CASHBACK_SOURCES = new Set([
  "ORDER_CASHBACK_BASE", "ORDER_CASHBACK_BONUS", "INVOICE_REDEMPTION_BASE", "INVOICE_REDEMPTION_BONUS",
  "CONTRACT_CASHBACK",
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
  if (m.kind === "ORDER_PAYMENT" || m.kind === "REDEMPTION_PAYMENT" || m.kind === "CONTRACT_PAYMENT") return "out";
  return m.amount_cents < 0 ? "out" : "in";
}

export function movementSignedAmountCents(m: FinancialMovementRead): number {
  const abs = Math.abs(m.amount_cents);
  return movementDirection(m) === "out" ? -abs : abs;
}

/** Coarse category for a dedicated "Tipo" column -- exactly the
    "pagamento / ricarica / altro" grouping requested, kept separate from
    the more detailed movementLabel() below. */
export function movementCategory(m: FinancialMovementRead): "Ricarica" | "Cashback" | "Pagamento" | "Contratto" | "Trasferimento" | "Storno" | "Altro" {
  if (m.kind === "CONTRACT_PAYMENT") return "Contratto";
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
  if (m.kind === "CONTRACT_PAYMENT") {
    return m.note ? `Pagamento contratto · ${m.note}` : "Pagamento contratto";
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
  if (m.contract_id) return { label: `Contratto #${shortCode(m.contract_id)}`, href: `${basePath}?tab=contracts` };
  return null;
}

/** What the movement itself opens: a LialCash row opens that movement, a
    real-money row opens the order / redemption / contract it paid. */
export function movementDetailRef(m: FinancialMovementRead): string | null {
  if (m.kind === "WALLET") return `wallet:${m.id}`;
  if (m.kind === "ORDER_PAYMENT" && m.order_id) return `order:${m.order_id}`;
  if (m.kind === "REDEMPTION_PAYMENT" && m.invoice_redemption_id) return `redemption:${m.invoice_redemption_id}`;
  if (m.kind === "CONTRACT_PAYMENT" && m.contract_id) return `contract:${m.contract_id}`;
  return null;
}

/** The thing a movement belongs to, as a chip: "Riscatto #AB12CD34" opens
    that redemption, whichever of its movements the chip is on. */
export function movementEntity(m: FinancialMovementRead): { label: string; ref: string } | null {
  if (m.order_id) return { label: `Ordine #${shortCode(m.order_id)}`, ref: `order:${m.order_id}` };
  if (m.invoice_redemption_id) return { label: `Riscatto #${shortCode(m.invoice_redemption_id)}`, ref: `redemption:${m.invoice_redemption_id}` };
  if (m.contract_id) return { label: `Contratto #${shortCode(m.contract_id)}`, ref: `contract:${m.contract_id}` };
  return null;
}

/** Every movement of the same order, redemption or contract. */
export function movementsOfEntity(
  movements: FinancialMovementRead[],
  entity: { order_id: string | null; invoice_redemption_id: string | null; contract_id: string | null }
): FinancialMovementRead[] {
  return movements.filter(
    (m) =>
      (entity.order_id && m.order_id === entity.order_id) ||
      (entity.invoice_redemption_id && m.invoice_redemption_id === entity.invoice_redemption_id) ||
      (entity.contract_id && m.contract_id === entity.contract_id)
  );
}
