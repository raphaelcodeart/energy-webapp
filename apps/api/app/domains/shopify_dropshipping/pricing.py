"""From the Shopify store's figure to what the customer pays in EUR.

    base  = variant cost (inventory item unit cost) or the store's price,
            per ShopifySettings.price_basis -- the price when no cost is set
    price = base x rate x (1 + markup%) + fixed markup
            then rounded UP to x,90 / x,99 (or to the cent)

Same rules as cj_dropshipping/pricing.py: rounding only goes up, integer
cents and Decimal, never a float.
"""

from decimal import ROUND_CEILING, Decimal

from app.domains.shopify_dropshipping.models import ShopifySettings


def _round_up(cents: int, rounding: str) -> int:
    if rounding not in ("90", "99"):
        return cents
    target = int(rounding)
    euros, rest = divmod(cents, 100)
    return euros * 100 + target if rest <= target else (euros + 1) * 100 + target


def base_amount(*, cost: Decimal | None, price: Decimal, settings: ShopifySettings) -> Decimal:
    if settings.price_basis == "COST" and cost is not None and Decimal(cost) > 0:
        return Decimal(cost)
    return Decimal(price)


def to_eur_cents(amount: Decimal | float | str, rate: Decimal) -> int:
    cents = Decimal(str(amount)) * Decimal(rate) * 100
    return int(cents.to_integral_value(rounding=ROUND_CEILING))


def sale_price_cents(
    *,
    cost: Decimal | None,
    price: Decimal,
    settings: ShopifySettings,
    markup_percentage: int | None = None,
) -> int:
    """The price of one unit; `markup_percentage` overrides the organization's."""
    markup = settings.markup_percentage if markup_percentage is None else markup_percentage
    rate = Decimal(settings.currency_rate)
    base = base_amount(cost=cost, price=price, settings=settings)
    cents = base * rate * 100 * (Decimal(100 + markup) / 100) + Decimal(settings.markup_fixed_cents or 0)
    if settings.shipping_mode == "INCLUDED":
        cents += Decimal(settings.shipping_flat_cents or 0)
    return _round_up(int(cents.to_integral_value(rounding=ROUND_CEILING)), settings.price_rounding)


def shipping_price_cents(*, settings: ShopifySettings) -> int:
    """Flat shipping at checkout, one per order; nothing when included."""
    if settings.shipping_mode == "INCLUDED":
        return 0
    return settings.shipping_flat_cents or 0
