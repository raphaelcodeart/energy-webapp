"""Marketplace 3 (Shopify dropshipping): settings, catalog, checkout, fulfillment.

See models.py for why this is a domain of its own. The checkout is the CJ
one step by step (credit cap, OTP before spending LialCash, bank transfer or
card +surcharge for the rest, Stripe webhook as the only proof of a card
payment); what differs is the supplier side -- the paid order is created in
the organization's Shopify store as a completed draft order, and shipping is
read back from that order's fulfillments.
"""

import html
import logging
import re
import uuid
from datetime import timedelta
from decimal import Decimal

import stripe
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.email import send_html_email_best_effort
from app.core.email_templates import render_email
from app.domains.audit import service as audit_service
from app.domains.marketplaces import rules
from app.domains.notifications import service as notifications_service
from app.domains.organizations import service as organizations_service
from app.domains.shopify_dropshipping import client as shopify
from app.domains.shopify_dropshipping import pricing
from app.domains.shopify_dropshipping.models import (
    PRICE_BASES,
    PRICE_ROUNDINGS,
    SHIPPING_MODES,
    SHOPIFY_ORDER_PAYMENT_METHODS,
    ShopifyOrder,
    ShopifyProduct,
    ShopifySettings,
    ShopifyVariant,
)
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service

logger = logging.getLogger(__name__)

MAX_QUANTITY = 10
MAX_ATTEMPTS = 6
#: The order is in the store and still moving: worth asking Shopify about.
FOLLOWED_FULFILLMENT = ("SENT", "SHIPPED")


class ShopifyError(Exception):
    pass


class ShopifyValidationError(ShopifyError):
    pass


class ShopifyNotFoundError(ShopifyError):
    pass


class InvalidOtpError(ShopifyError):
    pass


def order_number(order: ShopifyOrder) -> str:
    return f"LIAL-{str(order.id)[:8].upper()}"


def order_tag(order: ShopifyOrder) -> str:
    """Our order's mark in the store (Shopify tags are at most 40 characters):
    deterministic, so a retry finds the order an earlier attempt created."""
    return f"lial-{order.id.hex}"


def html_to_text(value: str | None, limit: int = 8000) -> str:
    """Store descriptions are HTML: kept as plain text with line breaks,
    nothing from a third party is ever rendered as markup on our pages."""
    if not value:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", value)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "• ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:limit]


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


# --- Impostazioni -------------------------------------------------------------------------------


async def get_settings_row(db: AsyncSession, *, organization_id: uuid.UUID) -> ShopifySettings:
    row = (
        await db.execute(select(ShopifySettings).where(ShopifySettings.organization_id == organization_id))
    ).scalar_one_or_none()
    if row is None:
        row = ShopifySettings(organization_id=organization_id, default_credit_percentage=rules.DEFAULT_CREDIT_PERCENTAGE)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def settings_read_dict(row: ShopifySettings) -> dict:
    return {
        "shop_domain": row.shop_domain,
        "access_token_configured": bool(row.access_token),
        "access_token_hint": f"…{row.access_token[-4:]}" if row.access_token else None,
        "api_version": row.api_version,
        "enabled": row.enabled,
        "shop_name": row.shop_name,
        "shop_currency": row.shop_currency,
        "currency_rate": float(row.currency_rate),
        "price_basis": row.price_basis,
        "markup_percentage": row.markup_percentage,
        "markup_fixed_cents": row.markup_fixed_cents,
        "price_rounding": row.price_rounding,
        "shipping_mode": row.shipping_mode,
        "shipping_flat_cents": row.shipping_flat_cents,
        "shipping_days": row.shipping_days,
        "default_credit_percentage": row.default_credit_percentage,
        "max_credit_percentage": rules.MAX_CREDIT_PERCENTAGE,
        "auto_forward": row.auto_forward,
        "last_connected_at": row.last_connected_at,
    }


PRICING_KEYS = (
    "currency_rate", "price_basis", "markup_percentage", "markup_fixed_cents", "price_rounding",
    "shipping_mode", "shipping_flat_cents",
)


async def update_settings(
    db: AsyncSession, *, row: ShopifySettings, updates: dict, actor_user_id: uuid.UUID
) -> ShopifySettings:
    """Saves the settings; a changed pricing rule re-prices every variant from
    its stored Shopify figures straight away."""
    if "price_rounding" in updates and updates["price_rounding"] not in PRICE_ROUNDINGS:
        raise ShopifyValidationError("Arrotondamento non valido.")
    if "shipping_mode" in updates and updates["shipping_mode"] not in SHIPPING_MODES:
        raise ShopifyValidationError("Modalità di spedizione non valida.")
    if "price_basis" in updates and updates["price_basis"] not in PRICE_BASES:
        raise ShopifyValidationError("Base di prezzo non valida.")
    if "default_credit_percentage" in updates:
        try:
            rules.check_credit_percentage(updates["default_credit_percentage"])
        except rules.CreditPercentageError as exc:
            raise ShopifyValidationError(str(exc)) from exc
    if "shop_domain" in updates:
        domain = shopify.normalize_domain(updates["shop_domain"])
        if domain and not domain.endswith(".myshopify.com"):
            raise ShopifyValidationError("Il dominio deve essere quello .myshopify.com del negozio.")
        if domain != row.shop_domain:
            row.shop_name = row.shop_currency = None
            row.last_connected_at = None
        updates["shop_domain"] = domain
    if "access_token" in updates:
        token = (updates.pop("access_token") or "").strip() or None
        if token != row.access_token:
            row.access_token = token
            row.last_connected_at = None
    enabling = updates.get("enabled")
    if enabling and not (updates.get("shop_domain", row.shop_domain) and row.access_token):
        raise ShopifyValidationError("Per attivare il Marketplace servono prima il dominio e il token del negozio Shopify.")
    reprice = any(k in updates and updates[k] != getattr(row, k) for k in PRICING_KEYS)
    for key, value in updates.items():
        setattr(row, key, value)
    row.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="shopify.settings_updated", entity_type="shopify_settings", entity_id=str(row.id),
        new_value={k: (str(v) if isinstance(v, Decimal) else v) for k, v in updates.items()},
    )
    await db.commit()
    await db.refresh(row)
    if reprice:
        await reprice_all(db, settings=row)
    return row


async def test_connection(db: AsyncSession, *, row: ShopifySettings) -> dict:
    shop = await shopify.shop_info(row)
    row.shop_name = (shop.get("name") or "")[:255] or None
    row.shop_currency = (shop.get("currencyCode") or "")[:3] or None
    if shop.get("myshopifyDomain"):
        row.shop_domain = shop["myshopifyDomain"]
    row.last_connected_at = utcnow()
    await db.commit()
    await db.refresh(row)
    return settings_read_dict(row)


def _variant_price(variant: ShopifyVariant, *, settings: ShopifySettings, product: ShopifyProduct) -> int:
    return pricing.sale_price_cents(
        cost=variant.cost_amount, price=variant.source_price_amount, settings=settings,
        markup_percentage=product.markup_percentage,
    )


async def reprice_all(db: AsyncSession, *, settings: ShopifySettings) -> int:
    products = list(
        (
            await db.execute(select(ShopifyProduct).where(ShopifyProduct.organization_id == settings.organization_id))
        ).scalars()
    )
    count = 0
    for product in products:
        for variant in await _variants(db, product.id):
            variant.price_cents = _variant_price(variant, settings=settings, product=product)
            count += 1
    await db.commit()
    return count


# --- Catalogo del negozio (ricerca e anteprima) ------------------------------------------------------


def _parse_product(node: dict, *, settings: ShopifySettings) -> dict:
    """A store product as the admin screens show it, with our price per variant."""
    images = [i["url"] for i in ((node.get("images") or {}).get("nodes") or []) if i.get("url")]
    featured = (node.get("featuredImage") or {}).get("url")
    if featured and featured not in images:
        images.insert(0, featured)
    variants = []
    for v in (node.get("variants") or {}).get("nodes") or []:
        item = v.get("inventoryItem") or {}
        cost = _decimal((item.get("unitCost") or {}).get("amount"))
        price = _decimal(v.get("price")) or Decimal(0)
        tracked = item.get("tracked", True)
        inventory = v.get("inventoryQuantity") if tracked else None
        label = v.get("title") or "Standard"
        if label == "Default Title":
            label = "Standard"
        variants.append({
            "variant_id": v["id"],
            "sku": v.get("sku") or None,
            "label": label[:255],
            "image_url": (v.get("image") or {}).get("url"),
            "cost_amount": float(cost) if cost is not None else None,
            "source_price_amount": float(price),
            "inventory": inventory,
            "price_cents": pricing.sale_price_cents(cost=cost, price=price, settings=settings),
        })
    prices = [v["price_cents"] for v in variants]
    return {
        "product_id": node["id"],
        "handle": node.get("handle"),
        "title": node.get("title") or "",
        "vendor": node.get("vendor"),
        "status": node.get("status"),
        "description_text": html_to_text(node.get("descriptionHtml")),
        "image_url": images[0] if images else None,
        "images": images[:20],
        "variants": variants,
        "min_price_cents": min(prices) if prices else None,
        "max_price_cents": max(prices) if prices else None,
        "currency": settings.shop_currency,
    }


async def search_catalog(
    db: AsyncSession, *, row: ShopifySettings, keyword: str | None, cursor: str | None
) -> dict:
    query = "status:active"
    if keyword:
        safe = keyword.replace("'", " ").replace('"', " ")
        query += f" AND (title:*{safe}* OR sku:{safe} OR vendor:*{safe}*)"
    page = await shopify.list_products(row, query=query, after=cursor)
    imported = {
        pid for pid in (
            await db.execute(
                select(ShopifyProduct.shopify_product_id).where(ShopifyProduct.organization_id == row.organization_id)
            )
        ).scalars()
    }
    items = []
    for node in page.get("nodes") or []:
        parsed = _parse_product(node, settings=row)
        parsed["already_imported"] = parsed["product_id"] in imported
        items.append(parsed)
    info = page.get("pageInfo") or {}
    return {"items": items, "next_cursor": info.get("endCursor") if info.get("hasNextPage") else None}


async def preview_product(db: AsyncSession, *, row: ShopifySettings, product_id: str) -> dict:
    node = await shopify.get_product(row, product_id=product_id)
    if not node:
        raise ShopifyNotFoundError("Prodotto non trovato nel negozio Shopify.")
    return _parse_product(node, settings=row)


# --- Prodotti importati --------------------------------------------------------------------------


async def _variants(db: AsyncSession, product_id: uuid.UUID) -> list[ShopifyVariant]:
    return list(
        (
            await db.execute(
                select(ShopifyVariant).where(ShopifyVariant.product_id == product_id).order_by(ShopifyVariant.created_at)
            )
        ).scalars()
    )


async def get_product(db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID) -> ShopifyProduct:
    product = await db.get(ShopifyProduct, product_id)
    if product is None or product.organization_id != organization_id:
        raise ShopifyNotFoundError("Prodotto non trovato.")
    return product


def _check_credit(value: int) -> int:
    try:
        return rules.check_credit_percentage(value)
    except rules.CreditPercentageError as exc:
        raise ShopifyValidationError(str(exc)) from exc


async def import_product(
    db: AsyncSession, *, row: ShopifySettings, actor_user_id: uuid.UUID, product_id: str, name: str,
    description: str | None, credit_discount_percentage: int | None, markup_percentage: int | None,
    variant_ids: list[str] | None, activate: bool,
) -> ShopifyProduct:
    existing = (
        await db.execute(
            select(ShopifyProduct).where(
                ShopifyProduct.organization_id == row.organization_id, ShopifyProduct.shopify_product_id == product_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ShopifyValidationError("Questo prodotto è già stato importato: lo trovi in Prodotti importati.")
    credit = _check_credit(row.default_credit_percentage if credit_discount_percentage is None else credit_discount_percentage)
    preview = await preview_product(db, row=row, product_id=product_id)
    chosen = [v for v in preview["variants"] if not variant_ids or v["variant_id"] in variant_ids]
    if not chosen:
        raise ShopifyValidationError("Scegli almeno una variante da vendere.")

    product = ShopifyProduct(
        organization_id=row.organization_id,
        shopify_product_id=product_id,
        handle=preview["handle"],
        name=name.strip() or (preview["title"] or "Prodotto")[:255],
        source_title=(preview["title"] or "")[:500] or None,
        vendor=(preview["vendor"] or "")[:255] or None,
        description=(description if description is not None else preview["description_text"])[:8000],
        image_url=preview["image_url"],
        images=preview["images"],
        status="ACTIVE" if activate else "INACTIVE",
        credit_discount_percentage=credit,
        markup_percentage=markup_percentage,
        last_synced_at=utcnow(),
        created_by_user_id=actor_user_id,
        updated_at=utcnow(),
    )
    db.add(product)
    await db.flush()
    for v in chosen:
        variant = ShopifyVariant(
            product_id=product.id,
            shopify_variant_id=v["variant_id"],
            sku=v["sku"],
            label=v["label"],
            image_url=v["image_url"],
            cost_amount=_decimal(v["cost_amount"]),
            source_price_amount=_decimal(v["source_price_amount"]) or Decimal(0),
            price_cents=0,
            inventory=v["inventory"],
            last_synced_at=utcnow(),
        )
        variant.price_cents = _variant_price(variant, settings=row, product=product)
        db.add(variant)
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="shopify.product_imported", entity_type="shopify_product", entity_id=str(product.id),
        new_value={"shopify_product_id": product_id, "variants": len(chosen)},
    )
    await db.commit()
    await db.refresh(product)
    return product


async def update_product(
    db: AsyncSession, *, row: ShopifySettings, product: ShopifyProduct, updates: dict, actor_user_id: uuid.UUID
) -> ShopifyProduct:
    if "credit_discount_percentage" in updates:
        _check_credit(updates["credit_discount_percentage"])
    reprice = "markup_percentage" in updates and updates["markup_percentage"] != product.markup_percentage
    for key, value in updates.items():
        setattr(product, key, value)
    product.updated_at = utcnow()
    if reprice:
        for variant in await _variants(db, product.id):
            variant.price_cents = _variant_price(variant, settings=row, product=product)
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="shopify.product_updated", entity_type="shopify_product", entity_id=str(product.id),
        new_value={k: v for k, v in updates.items() if k != "description"},
    )
    await db.commit()
    await db.refresh(product)
    return product


async def update_variant(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID, updates: dict
) -> ShopifyVariant:
    variant = await db.get(ShopifyVariant, variant_id)
    product = await db.get(ShopifyProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id:
        raise ShopifyNotFoundError("Variante non trovata.")
    for key, value in updates.items():
        setattr(variant, key, value)
    await db.commit()
    await db.refresh(variant)
    return variant


async def sync_product(db: AsyncSession, *, row: ShopifySettings, product: ShopifyProduct) -> ShopifyProduct:
    """Refreshes cost, price and stock from the store and re-prices. A variant
    no longer in the store is kept (orders point at it) but stops being sold;
    a product removed from the store stops being sold altogether."""
    try:
        node = await shopify.get_product(row, product_id=product.shopify_product_id)
    except shopify.ShopifyApiError as exc:
        product.sync_error = str(exc)[:500]
        product.last_synced_at = utcnow()
        await db.commit()
        await db.refresh(product)
        return product
    variants = await _variants(db, product.id)
    if node is None:
        for variant in variants:
            variant.available_in_store = False
        product.sync_error = "Il prodotto non esiste più nel negozio Shopify."
    else:
        parsed = _parse_product(node, settings=row)
        by_id = {v["variant_id"]: v for v in parsed["variants"]}
        product.source_title = (parsed["title"] or "")[:500] or None
        product.images = parsed["images"] or product.images
        for variant in variants:
            fresh = by_id.get(variant.shopify_variant_id)
            variant.available_in_store = fresh is not None and parsed["status"] in (None, "ACTIVE")
            if fresh is not None:
                variant.cost_amount = _decimal(fresh["cost_amount"])
                variant.source_price_amount = _decimal(fresh["source_price_amount"]) or variant.source_price_amount
                variant.inventory = fresh["inventory"]
            variant.last_synced_at = utcnow()
        product.sync_error = None if parsed["status"] in (None, "ACTIVE") else "Il prodotto non è attivo nel negozio Shopify."
    for variant in variants:
        variant.price_cents = _variant_price(variant, settings=row, product=product)
    product.last_synced_at = utcnow()
    product.updated_at = utcnow()
    await db.commit()
    await db.refresh(product)
    return product


async def sync_all_products(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    row = await get_settings_row(db, organization_id=organization_id)
    if not (row.shop_domain and row.access_token):
        return 0
    products = await list_products(db, organization_id=organization_id, active_only=False)
    for product in products:
        await sync_product(db, row=row, product=product)
    return len(products)


def variant_price(variant: ShopifyVariant) -> int:
    return variant.price_override_cents or variant.price_cents


def variant_sellable(variant: ShopifyVariant) -> bool:
    return variant.active and variant.available_in_store and (variant.inventory is None or variant.inventory > 0)


async def product_admin_dict(db: AsyncSession, product: ShopifyProduct) -> dict:
    variants = await _variants(db, product.id)
    sold = await db.execute(
        select(ShopifyOrder.id).where(ShopifyOrder.shopify_product_id == product.id, ShopifyOrder.status == "PAID")
    )
    return {
        "id": product.id,
        "shopify_product_id": product.shopify_product_id,
        "handle": product.handle,
        "name": product.name,
        "source_title": product.source_title,
        "vendor": product.vendor,
        "description": product.description,
        "image_url": product.image_url,
        "images": product.images or [],
        "status": product.status,
        "credit_discount_percentage": product.credit_discount_percentage,
        "markup_percentage": product.markup_percentage,
        "last_synced_at": product.last_synced_at,
        "sync_error": product.sync_error,
        "paid_orders": len(sold.all()),
        "created_at": product.created_at,
        "variants": [
            {
                "id": v.id,
                "shopify_variant_id": v.shopify_variant_id,
                "sku": v.sku,
                "label": v.label,
                "image_url": v.image_url,
                "cost_amount": float(v.cost_amount) if v.cost_amount is not None else None,
                "source_price_amount": float(v.source_price_amount),
                "price_cents": v.price_cents,
                "price_override_cents": v.price_override_cents,
                "effective_price_cents": variant_price(v),
                "inventory": v.inventory,
                "active": v.active,
                "available_in_store": v.available_in_store,
            }
            for v in variants
        ],
    }


async def list_products(db: AsyncSession, *, organization_id: uuid.UUID, active_only: bool) -> list[ShopifyProduct]:
    stmt = select(ShopifyProduct).where(ShopifyProduct.organization_id == organization_id)
    if active_only:
        stmt = stmt.where(ShopifyProduct.status == "ACTIVE")
    return list((await db.execute(stmt.order_by(ShopifyProduct.created_at.desc()))).scalars())


async def product_customer_dict(
    db: AsyncSession, product: ShopifyProduct, *, settings: ShopifySettings, card_surcharge_percentage: int
) -> dict | None:
    """Same shape as the CJ card (CjProductRead): one Shop grid for both."""
    variants = [v for v in await _variants(db, product.id) if v.active and v.available_in_store]
    if not variants:
        return None
    prices = [variant_price(v) for v in variants]
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "image_url": product.image_url,
        "images": product.images or [],
        "min_price_cents": min(prices),
        "max_price_cents": max(prices),
        "credit_discount_percentage": product.credit_discount_percentage,
        "shipping_days": settings.shipping_days,
        "shipping_included": settings.shipping_mode == "INCLUDED",
        #: The shown prices are the bank-transfer ones; card costs this much more.
        "card_surcharge_percentage": card_surcharge_percentage,
        "in_stock": any(variant_sellable(v) for v in variants),
        "variants": [
            {
                "id": v.id,
                "label": v.label,
                "image_url": v.image_url,
                "price_cents": variant_price(v),
                "in_stock": variant_sellable(v),
            }
            for v in variants
        ],
    }


# --- Checkout -------------------------------------------------------------------------------------


async def _sellable(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID
) -> tuple[ShopifyProduct, ShopifyVariant]:
    variant = await db.get(ShopifyVariant, variant_id)
    product = await db.get(ShopifyProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id or product.status != "ACTIVE":
        raise ShopifyValidationError("Prodotto non disponibile.")
    if not variant_sellable(variant):
        raise ShopifyValidationError("Questa variante al momento non è disponibile.")
    return product, variant


def max_creditable_cents(*, amount_cents: int, credit_discount_percentage: int) -> int:
    """Never the whole price, whatever is stored (marketplaces/rules.py)."""
    percentage = min(credit_discount_percentage, rules.MAX_CREDIT_PERCENTAGE)
    return min(round(amount_cents * percentage / 100), max(amount_cents - 1, 0))


def card_total_cents(*, residual_cents: int, percentage: int) -> int:
    return residual_cents + rules.card_surcharge_cents(residual_cents=residual_cents, percentage=percentage)


def amount_due_cents(order: ShopifyOrder) -> int:
    """What the customer pays in euro: residual after LialCash, plus the card
    surcharge when paying by card."""
    return order.amount_cents - order.credit_applied_cents + (order.card_surcharge_cents or 0)


async def freeze_card_surcharge(db: AsyncSession, *, order: ShopifyOrder) -> None:
    """The order's card surcharge for its current payment method, from today's
    setting -- never from the browser. Does not commit."""
    if order.status != "AWAITING_PAYMENT":
        return
    if order.payment_method == "CARD":
        percentage = await rules.get_card_surcharge_percentage(db, organization_id=order.organization_id)
        order.card_surcharge_cents = rules.card_surcharge_cents(
            residual_cents=order.amount_cents - order.credit_applied_cents, percentage=percentage
        )
    else:
        order.card_surcharge_cents = 0


async def payment_methods(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    return {
        "bank_transfer": await organizations_service.is_bank_transfer_configured(db, organization_id=organization_id),
        "card": await organizations_service.is_stripe_configured(db, organization_id=organization_id),
    }


async def get_quote(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, variant_id: uuid.UUID, quantity: int
) -> dict:
    if quantity < 1 or quantity > MAX_QUANTITY:
        raise ShopifyValidationError(f"Quantità da 1 a {MAX_QUANTITY}.")
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled:
        raise ShopifyValidationError("Questo shop non è disponibile al momento.")
    product, variant = await _sellable(db, organization_id=organization_id, variant_id=variant_id)
    if variant.inventory is not None and variant.inventory < quantity:
        raise ShopifyValidationError(f"Disponibili solo {variant.inventory} pezzi.")
    unit = variant_price(variant)
    shipping_cents = pricing.shipping_price_cents(settings=row)
    amount = unit * quantity + shipping_cents
    wallet = await wallets_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer_user_id)
    methods = await payment_methods(db, organization_id=organization_id)
    surcharge_percentage = await rules.get_card_surcharge_percentage(db, organization_id=organization_id)
    user = await db.get(User, customer_user_id)
    return {
        "variant_id": variant.id,
        "product_name": product.name,
        "variant_label": variant.label,
        "quantity": quantity,
        "unit_price_cents": unit,
        "items_cents": unit * quantity,
        "shipping_cents": shipping_cents,
        "shipping_included": row.shipping_mode == "INCLUDED",
        "shipping_days": row.shipping_days,
        "amount_cents": amount,
        "credit_discount_percentage": product.credit_discount_percentage,
        "max_creditable_cents": max_creditable_cents(
            amount_cents=amount, credit_discount_percentage=product.credit_discount_percentage
        ),
        "customer_wallet_balance_cents": wallet.balance_cents if wallet else 0,
        "card_surcharge_percentage": surcharge_percentage,
        "card_amount_cents": card_total_cents(residual_cents=amount, percentage=surcharge_percentage),
        "bank_transfer_available": methods["bank_transfer"],
        "card_available": methods["card"],
        "default_address": {
            "street": user.residence_street if user else None,
            "city": user.residence_city if user else None,
            "province": user.residence_province if user else None,
            "postal_code": user.residence_postal_code if user else None,
        },
    }


async def create_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    variant_id: uuid.UUID,
    quantity: int,
    address: dict,
    credit_applied_cents: int,
    payment_method: str,
    actor_user_id: uuid.UUID,
    otp_code: str | None,
    note: str | None,
) -> ShopifyOrder:
    """Places the order with every amount computed here, never taken from the browser."""
    quote = await get_quote(
        db, organization_id=organization_id, customer_user_id=customer_user_id, variant_id=variant_id, quantity=quantity
    )
    row = await get_settings_row(db, organization_id=organization_id)
    product, variant = await _sellable(db, organization_id=organization_id, variant_id=variant_id)
    amount = quote["amount_cents"]
    if credit_applied_cents < 0 or credit_applied_cents > quote["max_creditable_cents"]:
        raise ShopifyValidationError(
            f"Puoi usare al massimo {quote['max_creditable_cents'] / 100:.2f} LialCash per questo ordine."
        )
    if credit_applied_cents > 0:
        from app.domains.auth import service as auth_service

        if not otp_code or not await auth_service.verify_otp(
            db, user_id=customer_user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code=otp_code
        ):
            raise InvalidOtpError("Codice di conferma mancante, non valido o scaduto.")
    if payment_method not in SHOPIFY_ORDER_PAYMENT_METHODS:
        raise ShopifyValidationError("Metodo di pagamento non valido.")
    methods = await payment_methods(db, organization_id=organization_id)
    if payment_method == "BANK_TRANSFER" and not methods["bank_transfer"]:
        raise ShopifyValidationError("Il pagamento con bonifico non è configurato.")
    if payment_method == "CARD" and not methods["card"]:
        raise ShopifyValidationError("Il pagamento con carta non è configurato.")

    wallet = None
    if credit_applied_cents > 0:
        wallet = await wallets_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer_user_id)
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Saldo LialCash insufficiente.")

    order = ShopifyOrder(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        shopify_product_id=product.id,
        shopify_variant_id=variant.id,
        created_by_user_id=actor_user_id,
        quantity=quantity,
        unit_price_cents=quote["unit_price_cents"],
        shipping_cents=quote["shipping_cents"],
        amount_cents=amount,
        credit_applied_cents=credit_applied_cents,
        status="AWAITING_PAYMENT",
        payment_method=payment_method,
        note=note,
        recipient_name=address["recipient_name"],
        recipient_phone=address.get("recipient_phone"),
        address_line1=address["address_line1"],
        address_line2=address.get("address_line2"),
        city=address["city"],
        province=address["province"],
        postal_code=address["postal_code"],
        country_code="IT",
        shipping_days=row.shipping_days,
        unit_cost_amount=pricing.base_amount(cost=variant.cost_amount, price=variant.source_price_amount, settings=row),
        currency_rate=row.currency_rate,
    )
    db.add(order)
    await db.flush()
    await freeze_card_surcharge(db, order=order)
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="SHOPIFY_ORDER_CREATED", entity_type="shopify_order", entity_id=order.id,
        title=f"Nuovo ordine Shopify: {product.name}",
        body=f"{amount / 100:.2f} EUR -- {quantity} × {variant.label}",
        exclude_user_id=actor_user_id,
    )
    if credit_applied_cents > 0:
        assert wallet is not None
        debit = await wallets_service.debit_wallet_for_shopify_purchase(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=credit_applied_cents,
            reference_shopify_order_id=order.id, actor_user_id=actor_user_id,
            note=f"Acquisto {product.name}", idempotency_key=f"shopify-order:{order.id}:credit",
        )
        order.credit_debit_transaction_id = debit.id
    await db.commit()
    await db.refresh(order)
    await _send_order_email(db, order=order, product=product, variant=variant)
    return order


async def after_paid(db: AsyncSession, *, order: ShopifyOrder) -> None:
    """A paid order goes to the store by itself when the administrator chose
    so; otherwise it waits in "Marketplace 3 → Ordini" for "Invia a Shopify"."""
    row = await get_settings_row(db, organization_id=order.organization_id)
    if not row.auto_forward:
        return
    try:
        from app.celery_app import celery_app

        celery_app.send_task("app.celery_app.shopify_forward_order_task", args=[str(order.id)])
    except Exception:
        logger.exception("Could not queue Shopify forwarding of order %s", order.id)


# --- Ordini: letture ----------------------------------------------------------------------------------


async def get_org_scoped(db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID) -> ShopifyOrder | None:
    order = await db.get(ShopifyOrder, order_id)
    if order is None or order.organization_id != organization_id:
        return None
    return order


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, order_id: uuid.UUID
) -> ShopifyOrder | None:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None or order.customer_user_id != customer_user_id:
        return None
    return order


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID | None = None,
    status_filter: str | None = None,
) -> list[ShopifyOrder]:
    stmt = select(ShopifyOrder).where(ShopifyOrder.organization_id == organization_id)
    if customer_user_id is not None:
        stmt = stmt.where(ShopifyOrder.customer_user_id == customer_user_id)
    if status_filter:
        stmt = stmt.where(ShopifyOrder.status == status_filter)
    return list((await db.execute(stmt.order_by(ShopifyOrder.created_at.desc()))).scalars())


def tracking_link(order: ShopifyOrder) -> str | None:
    if order.tracking_url:
        return order.tracking_url
    return f"https://t.17track.net/it#nums={order.tracking_number}" if order.tracking_number else None


def delivery_status(order: ShopifyOrder) -> str | None:
    """The only shipping state a customer ever sees, same values as CJ."""
    if order.status != "PAID":
        return None
    if order.fulfillment_status == "CANCELLED":
        return "PROBLEM"
    if order.fulfillment_status == "DELIVERED":
        return "DELIVERED"
    if order.fulfillment_status == "SHIPPED":
        return "SHIPPED"
    if order.fulfillment_status == "SENT":
        return "PREPARING"
    return "RECEIVED"


async def order_read_dict(db: AsyncSession, order: ShopifyOrder, *, admin: bool) -> dict:
    from app.domains.imported_products.service import _resolve_display_name

    product = await db.get(ShopifyProduct, order.shopify_product_id)
    variant = await db.get(ShopifyVariant, order.shopify_variant_id)
    out = {
        "id": order.id,
        "customer_user_id": order.customer_user_id,
        "customer_display_name": await _resolve_display_name(
            db, organization_id=order.organization_id, user_id=order.customer_user_id
        ),
        "shopify_product_id": order.shopify_product_id,
        "shopify_variant_id": order.shopify_variant_id,
        "product_name": product.name if product else "—",
        "product_image_url": (variant.image_url if variant and variant.image_url else None) or (product.image_url if product else None),
        "variant_label": variant.label if variant else None,
        "created_by_user_id": order.created_by_user_id,
        "quantity": order.quantity,
        "unit_price_cents": order.unit_price_cents,
        "shipping_cents": order.shipping_cents,
        "amount_cents": order.amount_cents,
        "credit_applied_cents": order.credit_applied_cents,
        "residual_amount_cents": order.amount_cents - order.credit_applied_cents,
        "card_surcharge_cents": order.card_surcharge_cents or 0,
        "card_surcharge_percentage": await rules.get_card_surcharge_percentage(db, organization_id=order.organization_id),
        "amount_due_cents": amount_due_cents(order),
        "status": order.status,
        "payment_method": order.payment_method,
        "stripe_checkout_session_id": order.stripe_checkout_session_id,
        "payment_proof_uploaded_at": order.payment_proof_uploaded_at,
        "note": order.note,
        "paid_at": order.paid_at,
        "cancelled_at": order.cancelled_at,
        "cancellation_reason": order.cancellation_reason,
        "created_at": order.created_at,
        "recipient_name": order.recipient_name,
        "recipient_phone": order.recipient_phone,
        "address_line1": order.address_line1,
        "address_line2": order.address_line2,
        "city": order.city,
        "province": order.province,
        "postal_code": order.postal_code,
        "country_code": order.country_code,
        "shipping_days": order.shipping_days,
        "delivery_status": delivery_status(order),
        "tracking_number": order.tracking_number,
        "tracking_url": tracking_link(order),
        "shipped_at": order.shipped_at,
        "delivered_at": order.delivered_at,
    }
    if admin:
        cost_cents = (
            pricing.to_eur_cents(Decimal(order.unit_cost_amount) * order.quantity, Decimal(order.currency_rate))
            if order.unit_cost_amount is not None else None
        )
        out.update({
            "fulfillment_status": order.fulfillment_status,
            "shopify_order_id": order.shopify_order_id,
            "shopify_order_name": order.shopify_order_name,
            "shopify_draft_order_id": order.shopify_draft_order_id,
            "shopify_fulfillment_status": order.shopify_fulfillment_status,
            "tracking_company": order.tracking_company,
            "unit_cost_amount": float(order.unit_cost_amount) if order.unit_cost_amount is not None else None,
            "currency_rate": float(order.currency_rate),
            "supplier_cost_cents": cost_cents,
            "estimated_margin_cents": (
                order.amount_cents + (order.card_surcharge_cents or 0) - cost_cents if cost_cents is not None else None
            ),
            "attempt_count": order.attempt_count,
            "last_attempt_at": order.last_attempt_at,
            "next_retry_at": order.next_retry_at,
            "last_error_kind": order.last_error_kind,
            "forwarded_at": order.forwarded_at,
            "forward_error": order.forward_error,
            "last_sync_at": order.last_sync_at,
        })
    return out


# --- Ordini: pagamento (identico agli altri negozi) ---------------------------------------------------


async def _mark_paid(db: AsyncSession, *, order: ShopifyOrder, by_card: bool, actor_user_id: uuid.UUID | None) -> None:
    order.status = "PAID"
    order.paid_by_user_id = actor_user_id
    order.paid_at = utcnow()
    product = await db.get(ShopifyProduct, order.shopify_product_id)
    name = product.name if product else "un prodotto"
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="shopify_order", entity_id=order.id, title=f"Il tuo ordine per {name} è confermato",
        body="Ti avvisiamo appena viene spedito.",
    )
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="SHOPIFY_ORDER_PAID", entity_type="shopify_order", entity_id=order.id,
        title=f"{'Pagamento Stripe' if by_card else 'Bonifico'} confermato: {name}",
        body=f"{amount_due_cents(order) / 100:.2f} EUR -- da inviare al negozio Shopify",
    )


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> ShopifyOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise ShopifyNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise ShopifyValidationError("Questo ordine non è in attesa di pagamento.")
    if order.payment_method == "CARD":
        raise ShopifyValidationError("Un ordine pagato con carta viene confermato automaticamente da Stripe.")
    await _mark_paid(db, order=order, by_card=False, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


async def mark_paid_via_stripe(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str, order_id: str | None = None
) -> ShopifyOrder | None:
    """`order_id` comes from the session's metadata: a customer may pay
    through an older link (the confirmation email's) after a newer checkout
    replaced the session id stored on the order -- still this order."""
    order = (
        await db.execute(
            select(ShopifyOrder).where(
                ShopifyOrder.organization_id == organization_id,
                ShopifyOrder.stripe_checkout_session_id == stripe_checkout_session_id,
            )
        )
    ).scalar_one_or_none()
    if order is None and order_id:
        try:
            order = await get_org_scoped(db, organization_id=organization_id, order_id=uuid.UUID(str(order_id)))
        except ValueError:
            order = None
    if order is None or order.status != "AWAITING_PAYMENT":
        return order
    await _mark_paid(db, order=order, by_card=True, actor_user_id=None)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


async def cancel_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> ShopifyOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise ShopifyNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise ShopifyValidationError("Si può annullare solo un ordine non ancora pagato.")
    if order.credit_debit_transaction_id is not None:
        await wallets_service.reverse_transaction(
            db, organization_id=organization_id, transaction_id=order.credit_debit_transaction_id,
            actor_user_id=actor_user_id, reason=f"Ordine annullato: {reason}",
            idempotency_key=f"shopify-order:{order.id}:cancel-refund",
        )
    order.status = "CANCELLED"
    order.cancelled_by_user_id = actor_user_id
    order.cancelled_at = utcnow()
    order.cancellation_reason = reason
    await db.commit()
    await db.refresh(order)
    return order


async def change_payment_method(
    db: AsyncSession, *, organization_id: uuid.UUID, order: ShopifyOrder, new_payment_method: str
) -> ShopifyOrder:
    if order.status != "AWAITING_PAYMENT":
        raise ShopifyValidationError("Il metodo di pagamento si cambia solo prima di pagare.")
    if new_payment_method not in SHOPIFY_ORDER_PAYMENT_METHODS:
        raise ShopifyValidationError("Metodo di pagamento non valido.")
    if new_payment_method != order.payment_method:
        methods = await payment_methods(db, organization_id=organization_id)
        if new_payment_method == "BANK_TRANSFER" and not methods["bank_transfer"]:
            raise ShopifyValidationError("Il pagamento con bonifico non è configurato.")
        if new_payment_method == "CARD" and not methods["card"]:
            raise ShopifyValidationError("Il pagamento con carta non è configurato.")
        if order.payment_method == "CARD":
            order.stripe_checkout_session_id = None
        order.payment_method = new_payment_method
        await freeze_card_surcharge(db, order=order)
        await db.commit()
        await db.refresh(order)
    return order


async def upload_payment_proof(
    db: AsyncSession, *, organization_id: uuid.UUID, order: ShopifyOrder, file_bytes: bytes, content_type: str,
    original_filename: str, actor_user_id: uuid.UUID,
) -> ShopifyOrder:
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document

    if order.status != "AWAITING_PAYMENT" or order.payment_method != "BANK_TRANSFER":
        raise ShopifyValidationError("La ricevuta si carica solo per un ordine da pagare con bonifico.")
    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"shopify-order-payment-proofs/{order.customer_user_id}",
        )
    except UploadValidationError as exc:
        raise ShopifyValidationError(str(exc)) from exc
    order.payment_proof_storage_key = storage_key
    order.payment_proof_original_filename = original_filename
    order.payment_proof_uploaded_at = utcnow()
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAYMENT_PROOF_UPLOADED", entity_type="shopify_order", entity_id=order.id,
        title="Ricevuta di bonifico caricata: ordine Shopify", body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(order)
    return order


def presigned_payment_proof_url(order: ShopifyOrder) -> str:
    from app.core.storage import generate_presigned_document_url

    assert order.payment_proof_storage_key is not None
    return generate_presigned_document_url(storage_key=order.payment_proof_storage_key, expires_in_seconds=300)


async def prepare_card_payment(db: AsyncSession, *, order: ShopifyOrder) -> int:
    """Before a Stripe checkout: the order becomes a card order with its
    surcharge frozen, and the amount Stripe must charge is returned."""
    order.payment_method = "CARD"
    await freeze_card_surcharge(db, order=order)
    await db.flush()
    return amount_due_cents(order)


async def attach_stripe_checkout_session(db: AsyncSession, *, order: ShopifyOrder, session_id: str) -> ShopifyOrder:
    order.payment_method = "CARD"
    order.stripe_checkout_session_id = session_id
    await db.commit()
    await db.refresh(order)
    return order


async def _send_order_email(
    db: AsyncSession, *, order: ShopifyOrder, product: ShopifyProduct, variant: ShopifyVariant
) -> None:
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    settings = get_settings()
    code = str(order.id)[:8].upper()
    lines = (
        f"<p>Numero ordine: <strong>#{code}</strong></p>"
        f"<p><strong>{html.escape(product.name)}</strong> — {html.escape(variant.label)} × {order.quantity}<br>"
        f"Spedizione: {order.shipping_cents / 100:.2f} &euro;"
        + (f" (consegna stimata {html.escape(order.shipping_days)} giorni)" if order.shipping_days else "")
        + f"<br>Totale: <strong>{order.amount_cents / 100:.2f} &euro;</strong>"
        + (f" (di cui {order.credit_applied_cents / 100:.2f} LialCash)" if order.credit_applied_cents else "")
        + "</p>"
        f"<p>Consegna a: {html.escape(order.recipient_name)}, {html.escape(order.address_line1)}, "
        f"{html.escape(order.postal_code)} {html.escape(order.city)} ({html.escape(order.province)})</p>"
    )
    residual = order.amount_cents - order.credit_applied_cents
    cta_label = cta_url = None
    heading = "Completa il pagamento del tuo ordine"
    if order.payment_method == "CARD":
        from app.domains.payments import service as payments_service

        surcharge = order.card_surcharge_cents or 0
        lines += f"<p>Da pagare con carta: <strong>{(residual + surcharge) / 100:.2f} &euro;</strong>"
        if surcharge:
            lines += (
                f"<br><small>Include l'aumento per il pagamento con carta ({surcharge / 100:.2f} &euro;). "
                f"Con bonifico istantaneo paghi {residual / 100:.2f} &euro;.</small>"
            )
        lines += "</p>"
        try:
            cta_url = await payments_service.create_checkout_session_for_shopify_order(
                db, organization_id=order.organization_id, order=order,
                success_url=f"{settings.public_app_base_url}/customer?tab=orders",
                cancel_url=f"{settings.public_app_base_url}/customer?tab=orders",
            )
            cta_label = "Paga con carta"
        except (payments_service.StripeNotConfiguredError, stripe.error.StripeError):
            logger.exception("Shopify order %s confirmation email sent without a Stripe link", order.id)
    else:
        bank = await organizations_service.get_settings(db, organization_id=order.organization_id)
        lines += f"<p>Da pagare con bonifico: <strong>{residual / 100:.2f} &euro;</strong></p>"
        if bank.get("bank_iban"):
            lines += (
                f"<p><strong>IBAN:</strong> {bank['bank_iban']}<br>"
                f"<strong>Intestatario:</strong> {bank.get('bank_account_holder') or 'Lial Energy'}<br>"
                f"<strong>Causale:</strong> Ordine {code}</p>"
            )
    send_html_email_best_effort(
        context=f"Shopify order confirmation email (order={order.id})",
        to=user.email,
        subject=f"Conferma ordine - {product.name} - Lial Energy",
        html_body=render_email(
            preheader=f"Riepilogo del tuo ordine -- {product.name}", heading=heading, body_html=lines,
            cta_label=cta_label, cta_url=cta_url,
        ),
        text_body=f"{heading}: {product.name}, totale {order.amount_cents / 100:.2f} EUR.",
    )


# --- Evasione nel negozio Shopify --------------------------------------------------------------
#
# A paid order becomes an order of the Shopify store: a draft order with the
# variant, the customer's address and our tag, completed as paid (the
# customer paid us; the store's dropshipping app then buys from the supplier).
#
# Never two orders in the store, whatever fails when:
# - one sender at a time: a conditional UPDATE claims the order (-> SENDING);
# - the draft's id is saved (committed) before completing it, so a retry
#   completes that same draft, or reads its order if it was completed already;
# - before creating a new draft, the store is searched for an order carrying
#   our tag, created by an attempt whose answer was lost.
# The worst a lost answer can leave behind is an unused draft, never an order.


def _schedule_retry(order: ShopifyOrder, kind: str) -> None:
    order.last_error_kind = kind
    if kind in ("TEMPORARY", "AUTHENTICATION") and order.attempt_count < MAX_ATTEMPTS:
        minutes = min(5 * 2 ** max(order.attempt_count - 1, 0), 360)
        order.next_retry_at = utcnow() + timedelta(minutes=minutes)
    else:
        order.next_retry_at = None


async def _staff_alert(db: AsyncSession, *, order: ShopifyOrder, type_: str, title: str, body: str) -> None:
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_=type_, entity_type="shopify_order", entity_id=order.id, title=title[:255], body=body[:1000],
    )


async def _draft_input(db: AsyncSession, order: ShopifyOrder) -> dict:
    variant = await db.get(ShopifyVariant, order.shopify_variant_id)
    user = await db.get(User, order.customer_user_id)
    first, _, last = order.recipient_name.partition(" ")
    address = {
        "firstName": first[:60],
        "lastName": (last or first)[:60],
        "address1": order.address_line1[:255],
        "address2": (order.address_line2 or "")[:255],
        "city": order.city[:100],
        "province": order.province[:60],
        "zip": order.postal_code,
        "countryCode": order.country_code,
        "phone": (order.recipient_phone or "")[:20] or None,
    }
    return {
        "lineItems": [{"variantId": variant.shopify_variant_id, "quantity": order.quantity}],
        "shippingAddress": address,
        "billingAddress": address,
        "email": user.email if user else None,
        "note": f"Ordine Lial Energy {order_number(order)} (id {order.id})",
        "tags": ["lialenergy", order_tag(order)],
    }


def _record_store_order(order: ShopifyOrder, store_order: dict) -> None:
    order.shopify_order_id = store_order["id"]
    order.shopify_order_name = (store_order.get("name") or "")[:64] or None


async def forward_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> ShopifyOrder:
    """Creates the paid order in the Shopify store, once. Safe to call any
    number of times, by the automatic flow, the retry job or an administrator;
    a failure is recorded on the order, not raised."""
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise ShopifyNotFoundError("Ordine non trovato.")
    if order.status != "PAID":
        raise ShopifyValidationError("Si invia al negozio solo un ordine già pagato dal cliente.")
    if order.shopify_order_id:
        raise ShopifyValidationError("Questo ordine è già nel negozio Shopify.")
    now = utcnow()
    claimed = await db.execute(
        update(ShopifyOrder)
        .where(
            ShopifyOrder.id == order.id,
            ShopifyOrder.shopify_order_id.is_(None),
            or_(
                ShopifyOrder.fulfillment_status.in_(("NOT_SENT", "ERROR")),
                and_(
                    ShopifyOrder.fulfillment_status == "SENDING",
                    ShopifyOrder.last_attempt_at < now - timedelta(minutes=10),
                ),
            ),
        )
        .values(fulfillment_status="SENDING", last_attempt_at=now, attempt_count=ShopifyOrder.attempt_count + 1)
    )
    await db.commit()
    if claimed.rowcount != 1:
        await db.refresh(order)
        raise ShopifyValidationError("Questo ordine è già in lavorazione proprio ora.")
    await db.refresh(order)
    row = await get_settings_row(db, organization_id=organization_id)
    try:
        store_order = None
        if order.shopify_draft_order_id:
            draft = await shopify.get_draft_order(row, draft_id=order.shopify_draft_order_id)
            if draft and draft.get("order"):
                store_order = draft["order"]
            elif draft:
                store_order = await shopify.complete_draft_order(row, draft_id=order.shopify_draft_order_id)
        if store_order is None:
            found = await shopify.find_orders_by_tag(row, tag=order_tag(order))
            if found:
                store_order = found[0]
                logger.info("Shopify order %s already in the store as %s: picked up", order.id, store_order["id"])
        if store_order is None:
            draft = await shopify.create_draft_order(row, draft_input=await _draft_input(db, order))
            order.shopify_draft_order_id = draft["id"]
            await db.commit()  # before completing: a retry completes this draft, never a new one
            store_order = await shopify.complete_draft_order(row, draft_id=draft["id"])
        _record_store_order(order, store_order)
        order.fulfillment_status = "SENT"
        order.forwarded_at = order.forwarded_at or utcnow()
        order.forwarded_by_user_id = actor_user_id
        order.forward_error = None
        order.last_error_kind = None
        order.next_retry_at = None
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=actor_user_id,
            action="shopify.order_created", entity_type="shopify_order", entity_id=str(order.id),
            new_value={"shopify_order_id": order.shopify_order_id, "name": order.shopify_order_name},
        )
        await db.commit()
    except shopify.ShopifyApiError as exc:
        logger.warning("Shopify forwarding failed for order %s (%s): %s", order.id, exc.kind, exc)
        order.fulfillment_status = "ERROR"
        order.forward_error = str(exc)[:500]
        _schedule_retry(order, exc.kind)
        if order.next_retry_at is None:
            await _staff_alert(
                db, order=order, type_="SHOPIFY_ORDER_FAILED",
                title=f"Ordine #{str(order.id)[:8].upper()}: serve un controllo sul negozio Shopify",
                body=f"{exc}. Il cliente ha pagato e vede \"Ordine ricevuto\". Marketplace Shopify → Ordini.",
            )
        await db.commit()
    await db.refresh(order)
    return order


def _fulfillment_from_remote(item: dict) -> tuple[str | None, dict | None, object]:
    """(our fulfillment status or None when unchanged, tracking info, delivered at)."""
    if item.get("cancelledAt"):
        return "CANCELLED", None, None
    fulfillments = item.get("fulfillments") or []
    tracking = None
    delivered_at = None
    for f in fulfillments:
        for info in f.get("trackingInfo") or []:
            if info.get("number") or info.get("url"):
                tracking = info
        if f.get("deliveredAt") or (f.get("displayStatus") or "").upper() == "DELIVERED":
            delivered_at = f.get("deliveredAt") or True
    display = (item.get("displayFulfillmentStatus") or "").upper()
    if delivered_at:
        return "DELIVERED", tracking, delivered_at
    if fulfillments or display in ("FULFILLED", "PARTIALLY_FULFILLED", "IN_PROGRESS"):
        return "SHIPPED", tracking, None
    return None, tracking, None


async def sync_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, orders: list[ShopifyOrder] | None = None
) -> int:
    """Asks the store about every order still moving: fulfilment, tracking,
    delivery, cancellation. Tells the customer when their parcel leaves and
    when it arrives. Returns how many orders changed."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not (row.shop_domain and row.access_token):
        return 0
    if orders is None:
        orders = list(
            (
                await db.execute(
                    select(ShopifyOrder).where(
                        ShopifyOrder.organization_id == organization_id,
                        ShopifyOrder.shopify_order_id.is_not(None),
                        ShopifyOrder.fulfillment_status.in_(FOLLOWED_FULFILLMENT),
                    )
                )
            ).scalars()
        )
    changed = 0
    for order in orders:
        if not order.shopify_order_id:
            continue
        item = await shopify.get_order(row, order_id=order.shopify_order_id)
        order.last_sync_at = utcnow()
        if not item:
            continue
        order.shopify_fulfillment_status = (item.get("displayFulfillmentStatus") or "")[:32] or None
        new_status, tracking, _delivered = _fulfillment_from_remote(item)
        previous = order.fulfillment_status
        previous_tracking = order.tracking_number
        if tracking:
            order.tracking_number = (tracking.get("number") or "")[:128] or order.tracking_number
            order.tracking_url = (tracking.get("url") or "")[:1000] or order.tracking_url
            order.tracking_company = (tracking.get("company") or "")[:128] or order.tracking_company
        if new_status and order.fulfillment_status != "SENDING":
            order.fulfillment_status = new_status
        if order.fulfillment_status == previous and order.tracking_number == previous_tracking:
            continue
        changed += 1
        if order.fulfillment_status == "SHIPPED" and previous != "SHIPPED":
            order.shipped_at = utcnow()
            await _notify_customer_shipping(db, order=order, delivered=False)
        elif order.fulfillment_status == "DELIVERED" and previous != "DELIVERED":
            order.delivered_at = utcnow()
            order.shipped_at = order.shipped_at or utcnow()
            await _notify_customer_shipping(db, order=order, delivered=True)
        elif order.fulfillment_status == "CANCELLED" and previous != "CANCELLED":
            await _staff_alert(
                db, order=order, type_="SHOPIFY_ORDER_FAILED",
                title=f"Il negozio Shopify ha annullato l'ordine {str(order.id)[:8].upper()}",
                body="Il cliente ha già pagato: valuta rimborso o nuovo invio.",
            )
    await db.commit()
    return changed


async def retry_due_orders(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """The safety net of the automatic flow: paid orders never sent, and
    temporary failures whose retry time has come (bounded attempts)."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not (row.shop_domain and row.access_token) or not row.auto_forward:
        return 0
    now = utcnow()
    due = list(
        (
            await db.execute(
                select(ShopifyOrder)
                .where(
                    ShopifyOrder.organization_id == organization_id,
                    ShopifyOrder.status == "PAID",
                    ShopifyOrder.shopify_order_id.is_(None),
                    or_(
                        and_(ShopifyOrder.fulfillment_status == "NOT_SENT", ShopifyOrder.paid_at < now - timedelta(minutes=2)),
                        and_(
                            ShopifyOrder.fulfillment_status == "ERROR",
                            ShopifyOrder.next_retry_at.is_not(None),
                            ShopifyOrder.next_retry_at <= now,
                        ),
                        and_(
                            ShopifyOrder.fulfillment_status == "SENDING",
                            ShopifyOrder.last_attempt_at < now - timedelta(minutes=10),
                        ),
                    ),
                )
                .order_by(ShopifyOrder.paid_at)
            )
        ).scalars()
    )
    handled = 0
    for order in due:
        try:
            await forward_order(db, organization_id=organization_id, order_id=order.id, actor_user_id=None)
            handled += 1
        except ShopifyError:
            continue
    return handled


async def _notify_customer_shipping(db: AsyncSession, *, order: ShopifyOrder, delivered: bool) -> None:
    product = await db.get(ShopifyProduct, order.shopify_product_id)
    name = product.name if product else "il tuo ordine"
    title = f"{name} è stato consegnato" if delivered else f"{name} è stato spedito"
    body = None if delivered else (f"Numero di tracking: {order.tracking_number}" if order.tracking_number else None)
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_SHIPPED",
        entity_type="shopify_order", entity_id=order.id, title=title, body=body,
    )
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    link = tracking_link(order)
    body_html = (
        f"<p>Numero ordine: <strong>#{str(order.id)[:8].upper()}</strong></p>"
        f"<p><strong>{html.escape(name)}</strong> {'è stato consegnato' if delivered else 'è in viaggio verso di te'}.</p>"
    )
    if not delivered and order.tracking_number:
        body_html += f"<p>Numero di tracking: <strong>{html.escape(order.tracking_number)}</strong></p>"
    send_html_email_best_effort(
        context=f"Shopify order shipping email (order={order.id}, delivered={delivered})",
        to=user.email,
        subject=f"{'Consegnato' if delivered else 'Spedito'}: {name} - Lial Energy",
        html_body=render_email(
            preheader=title, heading=title, body_html=body_html,
            cta_label=None if delivered or not link else "Segui la spedizione",
            cta_url=None if delivered else link,
        ),
        text_body=title + (f" Tracking: {order.tracking_number}" if order.tracking_number and not delivered else ""),
    )
