/** Chi può comprare cosa, e quanto costa davvero.
 *
 * Mirrors `apps/api/app/domains/catalog/pricing.py`. The server is the
 * authority for both rules -- it filters nothing here that it does not also
 * reject there -- but the catalog has to know the same answer to avoid
 * showing a customer a contract they would then be refused.
 *
 * Keep the two in sync. If they ever disagree, the server wins.
 */

const PRIVATE = "PRIVATE";
const BUSINESS = "BUSINESS";
const BOTH = "BOTH";

/** `products.customer_type` used to hold PMI / ENERGY_INTENSIVE /
    SOLE_PROPRIETOR / CONDOMINIUM -- a vocabulary that never lined up with
    `customers.kind`, so nothing could compare the two. Old values collapse
    onto BUSINESS; anything unrecognized fails OPEN (visible to everyone),
    because a display filter quietly hiding a product from the whole catalog
    is far worse than showing one product too many. */
export function normalizeProductCustomerType(value: string | null | undefined): string {
  if (!value) return BOTH;
  const upper = value.trim().toUpperCase();
  if (upper === PRIVATE || upper === BUSINESS || upper === BOTH) return upper;
  if (["SOLE_PROPRIETOR", "PMI", "CONDOMINIUM", "ENERGY_INTENSIVE"].includes(upper)) return BUSINESS;
  return BOTH;
}

/** Deliberately NOT the same grouping as the one that decides whether a
    customer has a first/last name or a company name (where SOLE_PROPRIETOR
    counts as "private"): a ditta individuale has a person's name AND a
    P.IVA. Two different questions. */
export function isBusinessCustomer(customerKind: string | null | undefined): boolean {
  return ["SOLE_PROPRIETOR", "COMPANY", "CONDOMINIUM"].includes((customerKind ?? "").trim().toUpperCase());
}

export function productAllowsCustomerKind(
  productCustomerType: string | null | undefined,
  customerKind: string | null | undefined
): boolean {
  const normalized = normalizeProductCustomerType(productCustomerType);
  if (normalized === BOTH) return true;
  // Unknown customer kind (e.g. the catalog rendered before the customer
  // record has loaded) must not hide anything -- same fail-open rule.
  if (!customerKind) return true;
  if (normalized === BUSINESS) return isBusinessCustomer(customerKind);
  return !isBusinessCustomer(customerKind);
}

export type PriceBreakdown = {
  netCents: number;
  /** Percentage points (22), not a fraction. 0 for a private customer. */
  vatRate: number;
  vatCents: number;
  grossCents: number;
};

/** The business rule, stated by the business: a contract for a private
    individual carries no VAT; a contract for a business is priced net + VAT.
    The customer's status decides WHETHER VAT applies, the product only
    decides WHICH rate applies when it does.
 *
 * `customerKind` null means "we don't know who is looking yet" -- e.g. the
 * shop grid, where nobody is buying a contract. There the product's own rate
 * is shown, which is what the catalog always did.
 */
export function computePrice(
  netCents: number,
  productVatPercentage: number | null | undefined,
  customerKind: string | null | undefined,
  { assumeBusinessWhenUnknown = true }: { assumeBusinessWhenUnknown?: boolean } = {}
): PriceBreakdown {
  const rateApplies = customerKind == null ? assumeBusinessWhenUnknown : isBusinessCustomer(customerKind);
  const rate = rateApplies && productVatPercentage ? productVatPercentage : 0;
  // Round half-up on the cent, matching catalog/pricing.py::_vat_cents.
  const vatCents = rate > 0 && netCents > 0 ? Math.round((netCents * rate) / 100) : 0;
  return { netCents, vatRate: rate, vatCents, grossCents: netCents + vatCents };
}

export function formatEuroCents(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}
