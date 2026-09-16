"""The single place VAT and contract pricing are decided.

Before this module, VAT lived only in two React components
(`customer-products-panel.tsx`, `product-detail-modal.tsx`) that multiplied
the price by `1 + vat/100` for display. Nothing on the server ever computed
it, so "the price" a customer saw and "the price" the backend would have
charged were two independent implementations waiting to disagree.

Everything about how much a contract costs now goes through here, and every
caller is server-side. Nothing in this module ever reads a number sent by a
browser: it takes a `ProductVersion` row and a customer kind, both loaded
from the database, and returns the breakdown.

The breakdown is **snapshotted onto the contract** at creation
(`contracts.net_amount_cents / vat_rate / vat_amount_cents /
gross_amount_cents`), so changing a product's VAT rate tomorrow can never
retroactively restate a contract someone already signed -- the same
"frozen at the moment it happens" discipline already used for network
snapshots and commission calculations.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domains.catalog.models import ProductVersion

# --- Who a product may be sold to -------------------------------------------
#
# `products.customer_type` used to be a free string with a vocabulary
# (PMI, ENERGY_INTENSIVE, SOLE_PROPRIETOR, CONDOMINIUM) that did not line up
# with `customers.kind` (PRIVATE, SOLE_PROPRIETOR, COMPANY, CONDOMINIUM) --
# two enums nobody ever compared, so no product was ever filtered by who the
# buyer was. The business question is genuinely binary ("privati", "aziende /
# P.IVA", or both), so that is what the column now holds. The old values
# still parse, mapping onto the same binary answer, so no existing row and
# no old API client breaks.
PRIVATE_PRODUCT_CUSTOMER_TYPE = "PRIVATE"
BUSINESS_PRODUCT_CUSTOMER_TYPE = "BUSINESS"
BOTH_PRODUCT_CUSTOMER_TYPES = "BOTH"

PRODUCT_CUSTOMER_TYPES = frozenset(
    {PRIVATE_PRODUCT_CUSTOMER_TYPE, BUSINESS_PRODUCT_CUSTOMER_TYPE, BOTH_PRODUCT_CUSTOMER_TYPES}
)

_LEGACY_PRODUCT_CUSTOMER_TYPES = {
    "SOLE_PROPRIETOR": BUSINESS_PRODUCT_CUSTOMER_TYPE,
    "PMI": BUSINESS_PRODUCT_CUSTOMER_TYPE,
    "CONDOMINIUM": BUSINESS_PRODUCT_CUSTOMER_TYPE,
    "ENERGY_INTENSIVE": BUSINESS_PRODUCT_CUSTOMER_TYPE,
}

# --- Who pays VAT -----------------------------------------------------------
#
# Business rule, stated by the business: a contract for a private individual
# carries no VAT; a contract for a business / VAT-registered customer is
# priced net + VAT. `customers.kind` is the only input, so the answer can
# never depend on anything a browser sent.
#
# Deliberately NOT reusing `customers/service.py::PRIVATE_LIKE_KINDS`, which
# groups SOLE_PROPRIETOR with PRIVATE: that grouping answers a different
# question (does this customer have a first/last name or a company name?).
# A ditta individuale has a person's name AND a P.IVA, so it belongs with
# "private" there and with "business" here. Two different axes, two
# different constants, on purpose.
VAT_LIABLE_CUSTOMER_KINDS = frozenset({"SOLE_PROPRIETOR", "COMPANY", "CONDOMINIUM"})


def normalize_product_customer_type(value: str | None) -> str:
    """Maps any historical `products.customer_type` value onto the current
    three-value vocabulary. An unknown value is treated as BOTH rather than
    hidden from everyone -- failing open on a display filter is far less
    damaging than a product silently disappearing from the catalog."""
    if not value:
        return BOTH_PRODUCT_CUSTOMER_TYPES
    upper = value.strip().upper()
    if upper in PRODUCT_CUSTOMER_TYPES:
        return upper
    return _LEGACY_PRODUCT_CUSTOMER_TYPES.get(upper, BOTH_PRODUCT_CUSTOMER_TYPES)


def is_business_customer(customer_kind: str | None) -> bool:
    return (customer_kind or "").strip().upper() in VAT_LIABLE_CUSTOMER_KINDS


def product_allows_customer_kind(product_customer_type: str | None, customer_kind: str | None) -> bool:
    """Whether a product may be offered to a customer of this kind. Used both
    to filter the catalog a customer/promoter sees AND to reject a contract
    creation server-side -- hiding the card is never the enforcement."""
    normalized = normalize_product_customer_type(product_customer_type)
    if normalized == BOTH_PRODUCT_CUSTOMER_TYPES:
        return True
    if normalized == BUSINESS_PRODUCT_CUSTOMER_TYPE:
        return is_business_customer(customer_kind)
    return not is_business_customer(customer_kind)


def vat_rate_for(*, product_vat_percentage: float | None, customer_kind: str | None) -> Decimal:
    """The VAT rate actually applied, as a percentage (e.g. Decimal("22")).

    Zero for a private customer no matter what the product says -- the
    customer's status decides whether VAT applies at all, the product only
    decides which rate applies when it does."""
    if not is_business_customer(customer_kind):
        return Decimal(0)
    if product_vat_percentage is None:
        return Decimal(0)
    rate = Decimal(str(product_vat_percentage))
    return rate if rate > 0 else Decimal(0)


@dataclass(frozen=True)
class PriceBreakdown:
    """What gets snapshotted onto a contract and shown to the customer."""

    net_amount_cents: int
    #: Percentage points, e.g. Decimal("22") -- NOT a 0..1 fraction.
    vat_rate: Decimal
    vat_amount_cents: int
    gross_amount_cents: int

    @property
    def has_vat(self) -> bool:
        return self.vat_amount_cents > 0


def _vat_cents(net_cents: int, vat_rate: Decimal) -> int:
    """Half-up on the cent, the way an Italian invoice rounds. Decimal, not
    float: 249_00 * 22 / 100 in binary floating point is not exactly 5478."""
    if vat_rate <= 0 or net_cents <= 0:
        return 0
    raw = (Decimal(net_cents) * vat_rate) / Decimal(100)
    return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def compute_price(*, net_amount_cents: int, product_vat_percentage: float | None, customer_kind: str | None) -> PriceBreakdown:
    rate = vat_rate_for(product_vat_percentage=product_vat_percentage, customer_kind=customer_kind)
    vat_cents = _vat_cents(net_amount_cents, rate)
    return PriceBreakdown(
        net_amount_cents=net_amount_cents,
        vat_rate=rate,
        vat_amount_cents=vat_cents,
        gross_amount_cents=net_amount_cents + vat_cents,
    )


# --- Where a LialCash credit comes from -------------------------------------
#
# Three mutually exclusive answers, derived rather than stored, so there is
# no fourth column that can drift out of sync with the two that actually
# drive behaviour (`cashback_enabled` for orders, `contract_cashback_
# percentage` for contracts). Exposed on the product API so both the
# dashboard and a human reading the catalog can see, per product, which
# rule applies -- which is exactly what "rendere esplicita la provenienza
# dell'accredito" asks for.
CASHBACK_MODE_NONE = "NO_CASHBACK"
#: Partner/dropshipping: opt-in, the customer pays the 5% surcharge
#: (orders/service.py::ORDER_CASHBACK_PERCENTAGE) to earn it. Unchanged.
CASHBACK_MODE_STANDARD = "STANDARD"
#: Lial Energy's own services (contracts, and formazione when catalogued):
#: credited automatically on payment, with NO surcharge asked of anyone.
CASHBACK_MODE_AUTOMATIC_INTERNAL = "AUTOMATIC_INTERNAL_SERVICE"


def cashback_mode_for(*, category: str | None, version: ProductVersion) -> str:
    if (category or "").upper() == "INTERNAL":
        return (
            CASHBACK_MODE_AUTOMATIC_INTERNAL
            if int(version.contract_cashback_percentage or 0) > 0
            else CASHBACK_MODE_NONE
        )
    return CASHBACK_MODE_STANDARD if version.cashback_enabled else CASHBACK_MODE_NONE


def contract_cashback_cents(*, version: ProductVersion, gross_amount_cents: int) -> int:
    """The LialCash a paid contract credits: a percentage of the GROSS
    amount, i.e. VAT included, because what the customer actually handed
    over is what comes back. Never computed from a pre-discount or
    otherwise inflated base -- same anti-inflation rule as the order
    cashback."""
    percentage = int(version.contract_cashback_percentage or 0)
    if percentage <= 0 or gross_amount_cents <= 0:
        return 0
    raw = (Decimal(gross_amount_cents) * Decimal(percentage)) / Decimal(100)
    return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def product_vat_percentage(version: ProductVersion) -> float | None:
    """Reads the rate out of the `tax_configuration` JSONB, which is where
    this project has always kept it (there is no dedicated column, and
    `ProductVersionRead.from_version()` flattens the same key for the API)."""
    configuration = version.tax_configuration or {}
    raw = configuration.get("vat_percentage")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


#: How many months one billing period covers. The catalog price of a Lial
#: Energy product is a canone per period (the dashboard has always printed
#: "/mese" next to it), not the price of the whole contract.
BILLING_PERIOD_MONTHS = {"MONTHLY": 1, "QUARTERLY": 3, "ANNUAL": 12}


#: Only these product types are priced per period. A PHYSICAL or DIGITAL
#: product is a one-off purchase at its listed price, whatever billing
#: period/duration its version happens to carry -- the admin form defaults
#: every version to MONTHLY / 12 months, and a t-shirt must never become
#: 12 x its price.
RECURRING_PRODUCT_TYPES = frozenset({"ENERGY_CONTRACT", "SUBSCRIPTION"})


def contract_billing_periods(version: ProductVersion, *, product_type: str | None) -> int:
    """How many canoni one contract term is made of: 12 for a 12-month
    contract billed monthly, 4 for one billed quarterly. 1 for a one-off
    product type, a version with no duration or an unknown billing period --
    charging exactly the listed price is the only safe reading of any of
    them."""
    if (product_type or "").upper() not in RECURRING_PRODUCT_TYPES:
        return 1
    duration = int(version.contract_duration_months or 0)
    period_months = BILLING_PERIOD_MONTHS.get((version.billing_period or "").upper())
    if duration <= 0 or period_months is None:
        return 1
    return max(1, duration // period_months)


def contract_net_amount_cents(version: ProductVersion, *, product_type: str | None) -> int:
    """The taxable amount of a whole Lial Energy contract, VAT excluded.

    `base_price_cents` is the canone for ONE billing period, and the
    contract costs that canone for every period of its term: a "15 € /mese"
    product on a 12-month contract is 180 € + IVA (business decision,
    Session 49 -- until then this returned the single canone, so a
    12-month contract was priced as one month). Paying in 12 instalments
    therefore charges exactly the monthly canone, 3 instalments a quarter
    of the year each, and "soluzione unica" the whole year.

    `initial_fee_cents` and `recurring_fee_cents` exist on the version but
    have never been charged by any code path in this project, so folding
    them in here would silently start billing amounts nobody has ever
    agreed to.

    This one function is still the only place that decides it -- every
    price in the app, every payment plan and every VAT figure is derived
    from it."""
    return int(version.base_price_cents or 0) * contract_billing_periods(version, product_type=product_type)


def compute_contract_price(
    *, version: ProductVersion, customer_kind: str | None, product_type: str | None
) -> PriceBreakdown:
    """The full server-side price of one contract. The only entry point
    contracts/service.py and the payment flow are allowed to use."""
    return compute_price(
        net_amount_cents=contract_net_amount_cents(version, product_type=product_type),
        product_vat_percentage=product_vat_percentage(version),
        customer_kind=customer_kind,
    )
