"""Come si paga un contratto Lial Energy: unica soluzione, 3 rate o 12 rate.

Contracts only. The Shop's own checkout (orders, imported orders) is a
separate, already-working flow and is untouched by any of this -- an order is
a purchase, a contract is a subscription to a service, and merging the two
would make both worse.

**Everything here is created through the Stripe API, per contract.** There are
no pre-made Stripe Products or Prices to keep in sync: the amount comes from
the breakdown frozen on the contract itself (`catalog/pricing.py`), which
already accounts for that customer's VAT. A fixed Price in the Stripe
dashboard would have to be re-made by hand on every price change and would
know nothing about who is buying.

**3 rate and 12 rate are the same mechanism**, a real Stripe subscription
that charges the card by itself and stops after N instalments -- they differ
only in N. No external financing provider is involved: Lial Energy is
splitting its own invoice, not lending anything, which is why this needs no
capability beyond ordinary card payments.
"""

from dataclasses import dataclass

PLAN_FULL = "FULL"
PLAN_INSTALMENTS_3 = "INSTALMENTS_3"
PLAN_MONTHLY_12 = "MONTHLY_12"


@dataclass(frozen=True)
class PaymentPlan:
    key: str
    #: 1 means a single charge; anything higher is a subscription that
    #: cancels itself once this many invoices have been paid.
    instalments: int
    label: str
    description: str


PAYMENT_PLANS: tuple[PaymentPlan, ...] = (
    PaymentPlan(
        key=PLAN_FULL,
        instalments=1,
        label="Soluzione unica",
        description="Un solo pagamento con carta, subito.",
    ),
    PaymentPlan(
        key=PLAN_INSTALMENTS_3,
        instalments=3,
        label="3 rate mensili",
        description="La prima rata oggi, le altre due addebitate automaticamente ogni mese.",
    ),
    PaymentPlan(
        key=PLAN_MONTHLY_12,
        instalments=12,
        label="12 rate mensili",
        description="La prima rata oggi, le altre undici addebitate automaticamente ogni mese.",
    ),
)


def plan_by_key(key: str | None) -> PaymentPlan | None:
    return next((p for p in PAYMENT_PLANS if p.key == key), None)


@dataclass(frozen=True)
class PlanBreakdown:
    """Exactly what the customer will be charged, and when.

    A Stripe subscription bills the SAME amount every period, and an amount
    rarely divides evenly by 3 or 12 -- so the instalment is rounded to the
    cent and `total_cents` is `instalment x instalments`, which can differ
    from the contract by a few cents in either direction
    (`rounding_difference_cents`, at most 6 cents for 12 instalments).

    That difference is **shown to the customer next to each option** rather
    than hidden. The obvious-looking alternatives are both worse: adding the
    remainder to the first invoice needs a Stripe Product created per
    contract (`add_invoice_items` cannot take an inline product), which
    litters the account with one object per sale to recover a few cents; and
    silently rounding up overcharges without saying so.
    """

    plan: PaymentPlan
    #: What the contract itself says is owed.
    contract_total_cents: int
    #: What this plan will actually collect: instalment x instalments.
    total_cents: int
    instalment_cents: int
    #: total_cents - (contract_total_cents - discount_cents). Zero whenever
    #: it divides evenly, which it does for every price in the catalog.
    rounding_difference_cents: int
    #: Session 64: taken off a single payment only (never off instalments).
    discount_percentage: int = 0
    discount_cents: int = 0

    @property
    def is_subscription(self) -> bool:
        return self.plan.instalments > 1


def discount_cents_for(total_cents: int, percentage: int) -> int:
    """The discount on a single payment, half-up to the cent. Taken off the
    price VAT included, which is the same as discounting the net price and
    applying VAT afterwards: VAT is proportional."""
    if percentage <= 0 or total_cents <= 0:
        return 0
    return min(total_cents, (total_cents * percentage * 2 + 100) // 200)


def breakdown_for(
    plan: PaymentPlan, total_cents: int, *, discount_percentage: int = 0, discount_cents: int | None = None
) -> PlanBreakdown:
    """`discount_percentage` prices a plan that is being offered;
    `discount_cents` re-reads one already chosen (frozen on the contract as
    contracts.payment_discount_cents), so a later change of the setting never
    restates what a customer paid. Both apply to a single payment only."""
    if plan.instalments <= 1:
        discount = discount_cents if discount_cents is not None else discount_cents_for(total_cents, discount_percentage)
        percentage = discount_percentage if discount_cents is None else (
            round(discount * 100 / total_cents) if total_cents else 0
        )
        return PlanBreakdown(
            plan=plan,
            contract_total_cents=total_cents,
            total_cents=total_cents - discount,
            instalment_cents=total_cents - discount,
            rounding_difference_cents=0,
            discount_percentage=percentage if discount else 0,
            discount_cents=discount,
        )
    # Half-up on the cent, the same rounding the VAT calculation uses.
    instalment = (total_cents * 2 + plan.instalments) // (plan.instalments * 2)
    plan_total = instalment * plan.instalments
    return PlanBreakdown(
        plan=plan,
        contract_total_cents=total_cents,
        total_cents=plan_total,
        instalment_cents=instalment,
        rounding_difference_cents=plan_total - total_cents,
    )


def contract_breakdown(plan: PaymentPlan, contract) -> PlanBreakdown:
    """What a contract that already chose `plan` is charged."""
    return breakdown_for(
        plan, int(contract.gross_amount_cents or 0),
        discount_cents=int(getattr(contract, "payment_discount_cents", 0) or 0) if plan.instalments <= 1 else 0,
    )


def available_breakdowns(total_cents: int, *, full_payment_discount_percentage: int = 0) -> list[PlanBreakdown]:
    """Every plan, priced for this specific contract.

    A plan whose instalment would round to zero is dropped: Stripe refuses a
    zero-amount recurring price, and offering "12 rate da 0,00" on a very
    small contract would be nonsense before it was an error."""
    out = []
    for plan in PAYMENT_PLANS:
        breakdown = breakdown_for(plan, total_cents, discount_percentage=full_payment_discount_percentage)
        if breakdown.instalment_cents <= 0:
            continue
        out.append(breakdown)
    return out
