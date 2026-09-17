"""Shop Lial Partner (CJ Dropshipping): settings, catalog, checkout, fulfillment.

See models.py for why this is a domain of its own. The checkout deliberately
mirrors imported_products/service.py step by step (credit cap, OTP before
spending LialCash, bank transfer or card for the rest, Stripe webhook as the
only proof of a card payment), so a customer finds exactly the same
experience in every shop; what is added is what a real dropshipping order
needs -- a delivery address, a shipping cost quoted live by CJ, and sending
the paid order to CJ and following it until delivery.
"""

import html
import json
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
from app.domains.cj_dropshipping import client as cj
from app.domains.cj_dropshipping import pricing
from app.domains.cj_dropshipping.models import (
    CJ_ORDER_PAYMENT_METHODS,
    PRICE_ROUNDINGS,
    SHIPPING_MODES,
    CjOrder,
    CjProduct,
    CjSettings,
    CjVariant,
)
from app.domains.notifications import service as notifications_service
from app.domains.organizations import service as organizations_service
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service

logger = logging.getLogger(__name__)

#: Where stock is looked for first, when a product can ship from several
#: warehouses: the destination itself, then the rest of the EU (no customs,
#: faster), then the US, then China.
ORIGIN_PREFERENCE = ["IT", "DE", "FR", "ES", "NL", "BE", "PL", "CZ", "GB", "US", "CN"]
EU_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT",
    "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
}
COUNTRY_NAMES = {"IT": "Italy", "DE": "Germany", "FR": "France", "ES": "Spain"}
MAX_QUANTITY = 10
FREIGHT_CACHE_SECONDS = 1800

CJ_STATUS_TO_FULFILLMENT = {
    "CREATED": "SENT",
    "IN_CART": "SENT",
    "UNPAID": "SENT",
    "UNSHIPPED": "PROCESSING",
    "PENDING": "PROCESSING",
    "PROCESSING": "PROCESSING",
    "SHIPPED": "SHIPPED",
    "DELIVERED": "DELIVERED",
    "CANCELLED": "CJ_CANCELLED",
}
#: The order is on CJ and still moving: worth asking CJ about.
FOLLOWED_FULFILLMENT = ("SENT", "PROCESSING", "SHIPPED")


class CjError(Exception):
    pass


class CjValidationError(CjError):
    pass


class CjNotFoundError(CjError):
    pass


class InvalidOtpError(CjError):
    pass


def order_number(order: CjOrder) -> str:
    """The order's id on CJ's side too: deterministic, so a send retried
    after a timeout finds the order CJ may already have created."""
    return f"LIAL-{order.id}"


def tracking_url(tracking_number: str | None) -> str | None:
    return f"https://t.17track.net/it#nums={tracking_number}" if tracking_number else None


def html_to_text(value: str | None, limit: int = 8000) -> str:
    """CJ descriptions are HTML written for another shop. Kept as plain text
    with line breaks: nothing from a third party is ever rendered as markup
    on our pages."""
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


def _decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal(0)
    text = str(value).split("--")[0].strip()
    try:
        return Decimal(text)
    except Exception:  # noqa: BLE001 -- CJ sometimes sends ranges or blanks
        return Decimal(0)


# --- Impostazioni -------------------------------------------------------------------------------


async def get_settings_row(db: AsyncSession, *, organization_id: uuid.UUID) -> CjSettings:
    row = (
        await db.execute(select(CjSettings).where(CjSettings.organization_id == organization_id))
    ).scalar_one_or_none()
    if row is None:
        row = CjSettings(organization_id=organization_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def settings_read_dict(row: CjSettings) -> dict:
    return {
        "api_key_configured": bool(row.api_key),
        "api_key_hint": f"…{row.api_key[-4:]}" if row.api_key else None,
        "connected": bool(row.access_token),
        "token_expires_at": row.access_token_expires_at,
        "enabled": row.enabled,
        "sandbox": row.sandbox,
        "usd_eur_rate": float(row.usd_eur_rate),
        "markup_percentage": row.markup_percentage,
        "markup_fixed_cents": row.markup_fixed_cents,
        "price_rounding": row.price_rounding,
        "shipping_mode": row.shipping_mode,
        "default_credit_percentage": row.default_credit_percentage,
        "destination_country": row.destination_country,
        "auto_forward": row.auto_forward,
        "last_balance_usd": float(row.last_balance_usd) if row.last_balance_usd is not None else None,
        "last_balance_at": row.last_balance_at,
    }


async def update_settings(db: AsyncSession, *, row: CjSettings, updates: dict, actor_user_id: uuid.UUID) -> CjSettings:
    """Saves the settings; a changed pricing rule re-prices every variant from
    its stored CJ cost straight away (no call to CJ needed)."""
    if "price_rounding" in updates and updates["price_rounding"] not in PRICE_ROUNDINGS:
        raise CjValidationError("Arrotondamento non valido.")
    if "shipping_mode" in updates and updates["shipping_mode"] not in SHIPPING_MODES:
        raise CjValidationError("Modalità di spedizione non valida.")
    if "api_key" in updates:
        key = (updates["api_key"] or "").strip() or None
        if key != row.api_key:
            row.api_key = key
            row.access_token = row.refresh_token = None
            row.access_token_expires_at = row.refresh_token_expires_at = None
        updates.pop("api_key")
    if updates.get("enabled") and not row.api_key:
        raise CjValidationError("Per attivare lo shop serve prima la chiave API di CJ.")
    reprice = any(
        k in updates and updates[k] != getattr(row, k)
        for k in ("usd_eur_rate", "markup_percentage", "markup_fixed_cents", "price_rounding", "shipping_mode")
    )
    for key, value in updates.items():
        setattr(row, key, value)
    row.updated_at = utcnow()
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="cj.settings_updated", entity_type="cj_settings", entity_id=str(row.id),
        new_value={k: (str(v) if isinstance(v, Decimal) else v) for k, v in updates.items()},
    )
    await db.commit()
    await db.refresh(row)
    if reprice:
        await reprice_all(db, settings=row)
    return row


async def test_connection(db: AsyncSession, *, row: CjSettings) -> dict:
    balance = await cj.get_balance(db, row)
    row.last_balance_usd = _decimal(balance.get("amount"))
    row.last_balance_at = utcnow()
    await db.commit()
    await db.refresh(row)
    return settings_read_dict(row)


async def reprice_all(db: AsyncSession, *, settings: CjSettings) -> int:
    products = list(
        (await db.execute(select(CjProduct).where(CjProduct.organization_id == settings.organization_id))).scalars()
    )
    count = 0
    for product in products:
        for variant in await _variants(db, product.id):
            variant.price_cents = pricing.sale_price_cents(
                cost_usd=variant.cost_usd, settings=settings, markup_percentage=product.markup_percentage,
                shipping_estimate_usd=product.shipping_estimate_usd,
            )
            count += 1
    await db.commit()
    return count


# --- Catalogo CJ (ricerca e anteprima) ---------------------------------------------------------------


async def _cache_get(key: str):
    try:
        raw = await cj._get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001 -- a cache miss, never an error
        return None


async def _cache_set(key: str, value, seconds: int) -> None:
    try:
        await cj._get_redis().set(key, json.dumps(value), ex=seconds)
    except Exception:  # noqa: BLE001 -- without cache CJ is just asked again
        logger.debug("CJ cache write skipped for %s", key)


async def categories(db: AsyncSession, *, row: CjSettings) -> list[dict]:
    """First and second level CJ categories, for the admin search filter.
    Cached a day: they change rarely and every call costs a rate-limit slot."""
    key = f"cj:categories:{row.organization_id}"
    cached = await _cache_get(key)
    if cached is not None:
        return cached
    out = []
    for first in await cj.get_categories(db, row):
        for second in first.get("categoryFirstList") or []:
            for third in second.get("categorySecondList") or []:
                out.append({
                    "id": third.get("categoryId"),
                    "name": f"{first.get('categoryFirstName')} › {second.get('categorySecondName')} › {third.get('categoryName')}",
                })
    await _cache_set(key, out, 86400)
    return out


async def search_catalog(
    db: AsyncSession, *, row: CjSettings, keyword: str | None, page: int, category_id: str | None,
    min_price: float | None, max_price: float | None, free_shipping: bool,
) -> dict:
    data = await cj.search_products(
        db, row, keyword=keyword, page=page, size=24, category_id=category_id, min_price=min_price,
        max_price=max_price, free_shipping=free_shipping,
    )
    imported = set(
        (
            await db.execute(select(CjProduct.cj_pid).where(CjProduct.organization_id == row.organization_id))
        ).scalars()
    )
    items = []
    for content in data.get("content") or []:
        for p in content.get("productList") or []:
            cost = _decimal(p.get("nowPrice") or p.get("sellPrice"))
            items.append({
                "pid": p.get("id"),
                "name_en": p.get("nameEn"),
                "sku": p.get("sku"),
                "image_url": p.get("bigImage"),
                "sell_price_usd": str(p.get("sellPrice") or ""),
                "estimated_price_cents": pricing.sale_price_cents(cost_usd=cost, settings=row) if cost else None,
                "inventory": p.get("warehouseInventoryNum"),
                "category_name": p.get("threeCategoryName") or p.get("oneCategoryName"),
                "free_shipping": p.get("addMarkStatus") == 1,
                "already_imported": p.get("id") in imported,
            })
    return {
        "page": data.get("pageNumber") or page,
        "total_pages": data.get("totalPages") or 0,
        "total_records": data.get("totalRecords") or 0,
        "items": items,
    }


def _stock_by_variant(detail: dict, inventory: dict | None) -> dict[str, dict[str, int]]:
    """{vid: {country: pieces}}. Stock comes from getInventoryByPid: the
    product detail's own `inventories` is null for most products (seen live
    in Session 62, which had made an in-stock product look sold out). The
    detail is only a fallback."""
    out: dict[str, dict[str, int]] = {}
    for item in (inventory or {}).get("variantInventories") or []:
        per_country = out.setdefault(str(item.get("vid")), {})
        for inv in item.get("inventory") or []:
            code = inv.get("countryCode")
            if code:
                per_country[code] = per_country.get(code, 0) + int(inv.get("totalInventory") or 0)
    for v in detail.get("variants") or []:
        vid = str(v.get("vid"))
        if vid in out:
            continue
        per_country = out.setdefault(vid, {})
        for inv in v.get("inventories") or []:
            code = inv.get("countryCode")
            if code:
                per_country[code] = per_country.get(code, 0) + int(
                    inv.get("totalInventory") or inv.get("totalInventoryNum") or 0
                )
    return out


def _choose_origin(stock: dict[str, dict[str, int]], inventory: dict | None) -> str:
    """The warehouse an order ships from: the one where the most variants are
    in stock (a product ships from one place, so a closer warehouse holding a
    single colour must not make the others look sold out); nearest first on
    a tie."""
    coverage: dict[str, int] = {}
    for per_country in stock.values():
        for code, n in per_country.items():
            if n > 0:
                coverage[code] = coverage.get(code, 0) + 1
    if coverage:
        best = max(coverage.values())
        countries = {code for code, n in coverage.items() if n == best}
    else:
        countries = set()
    if not countries:
        countries = {
            inv.get("countryCode")
            for inv in (inventory or {}).get("inventories") or []
            if int(inv.get("totalInventoryNum") or 0) > 0
        }
    for code in ORIGIN_PREFERENCE:
        if code in countries:
            return code
    return next(iter(sorted(c for c in countries if c)), "CN")


def postage_usd(option: dict) -> Decimal:
    """What CJ really charges for a shipping option. `logisticPrice` is only
    the carrier's base price: `totalPostageFee` adds customs clearance and
    the other fees, and is what a created order costs (verified live in
    Session 63: CJPacket Ordinary quoted 9.39, order charged 12.89 = its
    totalPostageFee; YunExpress quoted 8.74, total 14.64)."""
    total = option.get("totalPostageFee")
    return _decimal(total if total not in (None, "", 0) else option.get("logisticPrice"))


def _cheapest(options: list[dict]) -> dict | None:
    priced = [o for o in options if o.get("totalPostageFee") is not None or o.get("logisticPrice") is not None]
    return min(priced, key=postage_usd) if priced else None


def estimated_ioss_usd(*, product_usd: Decimal, origin: str, destination: str) -> Decimal:
    """Import VAT CJ adds through its IOSS when goods enter the EU from
    outside (22%, Italian rate; about 3.09 on 13.64 in the live order). An
    estimate for margins only: the real amount comes back on the CJ order."""
    if destination in EU_COUNTRIES and origin not in EU_COUNTRIES:
        return (product_usd * Decimal("0.22")).quantize(Decimal("0.01"))
    return Decimal(0)


async def preview_product(db: AsyncSession, *, row: CjSettings, pid: str) -> dict:
    """What importing this product would give: Italian-ready text, variants
    with CJ cost and our price, where it ships from and the cheapest
    shipping to the destination -- before anything is saved."""
    detail = await cj.get_product(db, row, pid=pid)
    try:
        inventory = await cj.get_product_inventory(db, row, pid=pid)
    except cj.CjApiError:
        inventory = None
    stock = _stock_by_variant(detail, inventory)
    origin = _choose_origin(stock, inventory)
    variants = detail.get("variants") or []
    heaviest = max(variants, key=lambda v: float(v.get("variantWeight") or 0), default=None)
    shipping = None
    if heaviest is not None:
        try:
            shipping = _cheapest(await cj.freight(
                db, row, vid=heaviest["vid"], quantity=1, origin=origin, destination=row.destination_country
            ))
        except cj.CjApiError:
            shipping = None
    shipping_usd = postage_usd(shipping) if shipping else None
    images = list(dict.fromkeys([detail.get("bigImage"), *(detail.get("productImageSet") or [])]))
    return {
        "pid": detail.get("pid"),
        "sku": detail.get("productSku"),
        "name_en": detail.get("productNameEn"),
        "description_text": html_to_text(detail.get("description")),
        "category_name": detail.get("categoryName"),
        "images": [i for i in images if i][:10],
        "origin_country": origin,
        "shipping_estimate_usd": float(shipping_usd) if shipping_usd is not None else None,
        "shipping_estimate_cents": pricing.usd_to_eur_cents(shipping_usd, Decimal(row.usd_eur_rate)) if shipping_usd else None,
        "shipping_days": shipping.get("logisticAging") if shipping else None,
        "shipping_carrier": shipping.get("logisticName") if shipping else None,
        "ships_to_destination": shipping is not None,
        "variants": [
            {
                "vid": v.get("vid"),
                "sku": v.get("variantSku"),
                "label": v.get("variantKey") or v.get("variantNameEn") or "Standard",
                "image_url": v.get("variantImage"),
                "cost_usd": float(_decimal(v.get("variantSellPrice"))),
                "weight_g": int(float(v.get("variantWeight") or 0)),
                "inventory": stock.get(str(v.get("vid")), {}).get(origin, 0),
                "price_cents": pricing.sale_price_cents(
                    cost_usd=_decimal(v.get("variantSellPrice")), settings=row, shipping_estimate_usd=shipping_usd
                ),
            }
            for v in variants
        ],
    }


# --- Prodotti importati ---------------------------------------------------------------------


async def _variants(db: AsyncSession, product_id: uuid.UUID) -> list[CjVariant]:
    return list(
        (
            await db.execute(select(CjVariant).where(CjVariant.product_id == product_id).order_by(CjVariant.created_at))
        ).scalars()
    )


async def get_product(db: AsyncSession, *, organization_id: uuid.UUID, product_id: uuid.UUID) -> CjProduct:
    product = await db.get(CjProduct, product_id)
    if product is None or product.organization_id != organization_id:
        raise CjNotFoundError("Prodotto non trovato.")
    return product


async def import_product(
    db: AsyncSession, *, row: CjSettings, actor_user_id: uuid.UUID, pid: str, name: str, description: str | None,
    credit_discount_percentage: int | None, markup_percentage: int | None, vids: list[str] | None, activate: bool,
) -> CjProduct:
    existing = (
        await db.execute(
            select(CjProduct).where(CjProduct.organization_id == row.organization_id, CjProduct.cj_pid == pid)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise CjValidationError("Questo prodotto è già stato importato: lo trovi in Prodotti.")
    preview = await preview_product(db, row=row, pid=pid)
    if not preview["ships_to_destination"]:
        raise CjValidationError(
            "CJ non propone nessuna spedizione per questo prodotto verso il paese di destinazione: non si può vendere."
        )
    chosen = [v for v in preview["variants"] if not vids or v["vid"] in vids]
    if not chosen:
        raise CjValidationError("Scegli almeno una variante da vendere.")

    product = CjProduct(
        organization_id=row.organization_id,
        cj_pid=pid,
        cj_sku=preview["sku"],
        name=name.strip() or (preview["name_en"] or "Prodotto")[:255],
        name_en=preview["name_en"],
        description=(description if description is not None else preview["description_text"])[:8000],
        image_url=preview["images"][0] if preview["images"] else None,
        images=preview["images"],
        category_name=preview["category_name"],
        origin_country=preview["origin_country"],
        shipping_estimate_usd=Decimal(str(preview["shipping_estimate_usd"])) if preview["shipping_estimate_usd"] is not None else None,
        shipping_days=preview["shipping_days"],
        status="ACTIVE" if activate else "INACTIVE",
        credit_discount_percentage=(
            row.default_credit_percentage if credit_discount_percentage is None else credit_discount_percentage
        ),
        markup_percentage=markup_percentage,
        last_synced_at=utcnow(),
        created_by_user_id=actor_user_id,
        updated_at=utcnow(),
    )
    db.add(product)
    await db.flush()
    for v in chosen:
        db.add(CjVariant(
            product_id=product.id,
            cj_vid=v["vid"],
            cj_sku=v["sku"],
            label=(v["label"] or "Standard")[:255],
            image_url=v["image_url"],
            cost_usd=Decimal(str(v["cost_usd"])),
            weight_g=v["weight_g"],
            price_cents=pricing.sale_price_cents(
                cost_usd=v["cost_usd"], settings=row, markup_percentage=markup_percentage,
                shipping_estimate_usd=product.shipping_estimate_usd,
            ),
            inventory=v["inventory"],
            last_synced_at=utcnow(),
        ))
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="cj.product_imported", entity_type="cj_product", entity_id=str(product.id),
        new_value={"cj_pid": pid, "variants": len(chosen)},
    )
    await db.commit()
    await db.refresh(product)
    return product


async def update_product(
    db: AsyncSession, *, row: CjSettings, product: CjProduct, updates: dict, actor_user_id: uuid.UUID
) -> CjProduct:
    reprice = "markup_percentage" in updates and updates["markup_percentage"] != product.markup_percentage
    for key, value in updates.items():
        setattr(product, key, value)
    product.updated_at = utcnow()
    if reprice:
        for variant in await _variants(db, product.id):
            variant.price_cents = pricing.sale_price_cents(
                cost_usd=variant.cost_usd, settings=row, markup_percentage=product.markup_percentage,
                shipping_estimate_usd=product.shipping_estimate_usd,
            )
    await audit_service.record(
        db, organization_id=row.organization_id, actor_user_id=actor_user_id,
        action="cj.product_updated", entity_type="cj_product", entity_id=str(product.id),
        new_value={k: v for k, v in updates.items() if k != "description"},
    )
    await db.commit()
    await db.refresh(product)
    return product


async def update_variant(
    db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID, updates: dict
) -> CjVariant:
    variant = await db.get(CjVariant, variant_id)
    product = await db.get(CjProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id:
        raise CjNotFoundError("Variante non trovata.")
    for key, value in updates.items():
        setattr(variant, key, value)
    await db.commit()
    await db.refresh(variant)
    return variant


async def sync_product(db: AsyncSession, *, row: CjSettings, product: CjProduct) -> CjProduct:
    """Refreshes cost, stock and availability from CJ and re-prices. A variant
    CJ no longer offers is kept (orders point at it) but stops being sold."""
    try:
        preview = await preview_product(db, row=row, pid=product.cj_pid)
    except cj.CjApiError as exc:
        product.sync_error = str(exc)[:500]
        product.last_synced_at = utcnow()
        await db.commit()
        await db.refresh(product)
        return product
    by_vid = {v["vid"]: v for v in preview["variants"]}
    if preview["shipping_estimate_usd"] is not None:
        product.shipping_estimate_usd = Decimal(str(preview["shipping_estimate_usd"]))
        product.shipping_days = preview["shipping_days"]
    product.origin_country = preview["origin_country"]
    product.name_en = preview["name_en"]
    product.images = preview["images"] or product.images
    for variant in await _variants(db, product.id):
        fresh = by_vid.get(variant.cj_vid)
        variant.available_on_cj = fresh is not None
        if fresh is not None:
            variant.cost_usd = Decimal(str(fresh["cost_usd"]))
            variant.inventory = fresh["inventory"]
            variant.weight_g = fresh["weight_g"]
        variant.price_cents = pricing.sale_price_cents(
            cost_usd=variant.cost_usd, settings=row, markup_percentage=product.markup_percentage,
            shipping_estimate_usd=product.shipping_estimate_usd,
        )
        variant.last_synced_at = utcnow()
    product.sync_error = None if preview["ships_to_destination"] else "CJ non spedisce più questo prodotto a destinazione."
    product.last_synced_at = utcnow()
    product.updated_at = utcnow()
    await db.commit()
    await db.refresh(product)
    return product


def variant_price(variant: CjVariant) -> int:
    return variant.price_override_cents or variant.price_cents


def variant_sellable(variant: CjVariant) -> bool:
    return variant.active and variant.available_on_cj and variant.inventory > 0


async def product_admin_dict(db: AsyncSession, product: CjProduct) -> dict:
    variants = await _variants(db, product.id)
    sold = await db.execute(select(CjOrder.id).where(CjOrder.cj_product_id == product.id, CjOrder.status == "PAID"))
    return {
        "id": product.id,
        "cj_pid": product.cj_pid,
        "cj_sku": product.cj_sku,
        "name": product.name,
        "name_en": product.name_en,
        "description": product.description,
        "image_url": product.image_url,
        "images": product.images or [],
        "category_name": product.category_name,
        "origin_country": product.origin_country,
        "shipping_estimate_usd": float(product.shipping_estimate_usd) if product.shipping_estimate_usd is not None else None,
        "shipping_days": product.shipping_days,
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
                "cj_vid": v.cj_vid,
                "cj_sku": v.cj_sku,
                "label": v.label,
                "image_url": v.image_url,
                "cost_usd": float(v.cost_usd),
                "weight_g": v.weight_g,
                "price_cents": v.price_cents,
                "price_override_cents": v.price_override_cents,
                "effective_price_cents": variant_price(v),
                "inventory": v.inventory,
                "active": v.active,
                "available_on_cj": v.available_on_cj,
            }
            for v in variants
        ],
    }


async def list_products(db: AsyncSession, *, organization_id: uuid.UUID, active_only: bool) -> list[CjProduct]:
    stmt = select(CjProduct).where(CjProduct.organization_id == organization_id)
    if active_only:
        stmt = stmt.where(CjProduct.status == "ACTIVE")
    return list((await db.execute(stmt.order_by(CjProduct.created_at.desc()))).scalars())


async def product_customer_dict(db: AsyncSession, product: CjProduct, *, settings: CjSettings) -> dict | None:
    variants = [v for v in await _variants(db, product.id) if v.active and v.available_on_cj]
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
        "shipping_days": product.shipping_days,
        "shipping_included": settings.shipping_mode == "INCLUDED",
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


async def _sellable(db: AsyncSession, *, organization_id: uuid.UUID, variant_id: uuid.UUID) -> tuple[CjProduct, CjVariant]:
    variant = await db.get(CjVariant, variant_id)
    product = await db.get(CjProduct, variant.product_id) if variant else None
    if variant is None or product is None or product.organization_id != organization_id or product.status != "ACTIVE":
        raise CjValidationError("Prodotto non disponibile.")
    if not variant_sellable(variant):
        raise CjValidationError("Questa variante al momento non è disponibile.")
    return product, variant


async def shipping_quote(
    db: AsyncSession, *, row: CjSettings, product: CjProduct, variant: CjVariant, quantity: int
) -> dict:
    """The cheapest CJ shipping for this variant and quantity to the
    destination, cached half an hour: a customer changing the quantity back
    and forth must not spend a CJ call every time."""
    key = f"cj:freight2:{row.organization_id}:{variant.cj_vid}:{quantity}:{product.origin_country}:{row.destination_country}"
    option = await _cache_get(key)
    if option is None:
        options = await cj.freight(
            db, row, vid=variant.cj_vid, quantity=quantity, origin=product.origin_country,
            destination=row.destination_country,
        )
        option = _cheapest(options)
        if option is None:
            raise CjValidationError("La spedizione di questo prodotto non è disponibile in questo momento.")
        option = {k: option.get(k) for k in ("logisticName", "logisticPrice", "totalPostageFee", "logisticAging")}
        await _cache_set(key, option, FREIGHT_CACHE_SECONDS)
    shipping_usd = postage_usd(option)
    return {
        "logistic_name": option["logisticName"],
        "shipping_days": option.get("logisticAging"),
        "shipping_usd": shipping_usd,
        "shipping_cents": pricing.shipping_price_cents(shipping_usd=shipping_usd, settings=row),
    }


def max_creditable_cents(*, amount_cents: int, credit_discount_percentage: int) -> int:
    return round(amount_cents * credit_discount_percentage / 100)


async def payment_methods(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    return {
        "bank_transfer": await organizations_service.is_bank_transfer_configured(db, organization_id=organization_id),
        "card": await organizations_service.is_stripe_configured(db, organization_id=organization_id),
    }


async def get_quote(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, variant_id: uuid.UUID, quantity: int
) -> dict:
    if quantity < 1 or quantity > MAX_QUANTITY:
        raise CjValidationError(f"Quantità da 1 a {MAX_QUANTITY}.")
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.enabled:
        raise CjValidationError("Lo shop non è disponibile al momento.")
    product, variant = await _sellable(db, organization_id=organization_id, variant_id=variant_id)
    if variant.inventory < quantity:
        raise CjValidationError(f"Disponibili solo {variant.inventory} pezzi.")
    try:
        shipping = await shipping_quote(db, row=row, product=product, variant=variant, quantity=quantity)
    except cj.CjApiError as exc:
        raise CjValidationError("Non riusciamo a calcolare la spedizione in questo momento. Riprova tra poco.") from exc
    unit = variant_price(variant)
    amount = unit * quantity + shipping["shipping_cents"]
    wallet = await wallets_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer_user_id)
    methods = await payment_methods(db, organization_id=organization_id)
    user = await db.get(User, customer_user_id)
    return {
        "variant_id": variant.id,
        "product_name": product.name,
        "variant_label": variant.label,
        "quantity": quantity,
        "unit_price_cents": unit,
        "items_cents": unit * quantity,
        "shipping_cents": shipping["shipping_cents"],
        "shipping_included": row.shipping_mode == "INCLUDED",
        "shipping_days": shipping["shipping_days"],
        "amount_cents": amount,
        "credit_discount_percentage": product.credit_discount_percentage,
        "max_creditable_cents": max_creditable_cents(
            amount_cents=amount, credit_discount_percentage=product.credit_discount_percentage
        ),
        "customer_wallet_balance_cents": wallet.balance_cents if wallet else 0,
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
) -> CjOrder:
    """Places the order with every amount computed here, never taken from the
    browser: price of the variant now, shipping quoted by CJ now."""
    quote = await get_quote(
        db, organization_id=organization_id, customer_user_id=customer_user_id, variant_id=variant_id, quantity=quantity
    )
    row = await get_settings_row(db, organization_id=organization_id)
    product, variant = await _sellable(db, organization_id=organization_id, variant_id=variant_id)
    amount = quote["amount_cents"]
    if credit_applied_cents < 0 or credit_applied_cents > quote["max_creditable_cents"]:
        raise CjValidationError(
            f"Puoi usare al massimo {quote['max_creditable_cents'] / 100:.2f} LialCash per questo ordine."
        )
    if credit_applied_cents > 0:
        from app.domains.auth import service as auth_service

        if not otp_code or not await auth_service.verify_otp(
            db, user_id=customer_user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code=otp_code
        ):
            raise InvalidOtpError("Codice di conferma mancante, non valido o scaduto.")
    residual = amount - credit_applied_cents
    if residual > 0:
        if payment_method not in CJ_ORDER_PAYMENT_METHODS:
            raise CjValidationError("Metodo di pagamento non valido.")
        methods = await payment_methods(db, organization_id=organization_id)
        if payment_method == "BANK_TRANSFER" and not methods["bank_transfer"]:
            raise CjValidationError("Il pagamento con bonifico non è configurato.")
        if payment_method == "CARD" and not methods["card"]:
            raise CjValidationError("Il pagamento con carta non è configurato.")

    wallet = None
    if credit_applied_cents > 0:
        wallet = await wallets_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer_user_id)
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Saldo LialCash insufficiente.")

    shipping = await shipping_quote(db, row=row, product=product, variant=variant, quantity=quantity)
    order = CjOrder(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        cj_product_id=product.id,
        cj_variant_id=variant.id,
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
        country_code=row.destination_country,
        logistic_name=shipping["logistic_name"],
        origin_country=product.origin_country,
        shipping_days=shipping["shipping_days"],
        unit_cost_usd=variant.cost_usd,
        shipping_cost_usd=shipping["shipping_usd"],
        usd_eur_rate=row.usd_eur_rate,
        sandbox=row.sandbox,
    )
    db.add(order)
    await db.flush()
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CJ_ORDER_CREATED", entity_type="cj_order", entity_id=order.id,
        title=f"Nuovo ordine Shop Lial Partner: {product.name}",
        body=f"{amount / 100:.2f} EUR -- {quantity} × {variant.label}",
        exclude_user_id=actor_user_id,
    )
    if credit_applied_cents > 0:
        assert wallet is not None
        if residual == 0:
            order.status = "PAID"
            order.paid_by_user_id = actor_user_id
            order.paid_at = utcnow()
        debit = await wallets_service.debit_wallet_for_cj_purchase(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=credit_applied_cents,
            reference_cj_order_id=order.id, actor_user_id=actor_user_id,
            note=f"Acquisto {product.name}", idempotency_key=f"cj-order:{order.id}:credit",
        )
        order.credit_debit_transaction_id = debit.id
    await db.commit()
    await db.refresh(order)
    await _send_order_email(db, order=order, product=product, variant=variant)
    if order.status == "PAID":
        await after_paid(db, order=order)
    return order


async def after_paid(db: AsyncSession, *, order: CjOrder) -> None:
    """A paid order goes to CJ by itself when the administrator chose so;
    otherwise it waits in "Shop Lial Partner → Ordini" for "Invia a CJ"."""
    row = await get_settings_row(db, organization_id=order.organization_id)
    if not row.auto_forward:
        return
    try:
        from app.celery_app import celery_app

        celery_app.send_task("app.celery_app.cj_forward_order_task", args=[str(order.id)])
    except Exception:
        logger.exception("Could not queue CJ forwarding of order %s", order.id)


# --- Ordini: letture ----------------------------------------------------------------------------------


async def get_org_scoped(db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID) -> CjOrder | None:
    order = await db.get(CjOrder, order_id)
    return order if order is not None and order.organization_id == organization_id else None


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, order_id: uuid.UUID
) -> CjOrder | None:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    return order if order is not None and order.customer_user_id == customer_user_id else None


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID | None = None,
    status_filter: str | None = None,
) -> list[CjOrder]:
    stmt = select(CjOrder).where(CjOrder.organization_id == organization_id)
    if customer_user_id is not None:
        stmt = stmt.where(CjOrder.customer_user_id == customer_user_id)
    if status_filter:
        stmt = stmt.where(CjOrder.status == status_filter)
    return list((await db.execute(stmt.order_by(CjOrder.created_at.desc()))).scalars())


async def order_read_dict(db: AsyncSession, order: CjOrder, *, admin: bool) -> dict:
    from app.domains.imported_products.service import _resolve_display_name

    product = await db.get(CjProduct, order.cj_product_id)
    variant = await db.get(CjVariant, order.cj_variant_id)
    out = {
        "id": order.id,
        "customer_user_id": order.customer_user_id,
        "customer_display_name": await _resolve_display_name(
            db, organization_id=order.organization_id, user_id=order.customer_user_id
        ),
        "cj_product_id": order.cj_product_id,
        "cj_variant_id": order.cj_variant_id,
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
        "tracking_url": tracking_url(order.tracking_number),
        "shipped_at": order.shipped_at,
        "delivered_at": order.delivered_at,
    }
    if admin:
        cost_usd = cj_cost_usd(order)
        cost_cents = pricing.usd_to_eur_cents(cost_usd, Decimal(order.usd_eur_rate))
        out.update({
            "fulfillment_status": order.fulfillment_status,
            "cj_payment_status": order.cj_payment_status,
            "cj_cost_usd": float(cost_usd),
            "cj_cost_is_actual": order.cj_amount_usd is not None,
            "cj_cost_cents": cost_cents,
            "cj_order_code": order.cj_order_code,
            "cj_pay_url": order.cj_pay_url,
            "cj_product_amount_usd": _float(order.cj_product_amount_usd),
            "cj_postage_amount_usd": _float(order.cj_postage_amount_usd),
            "cj_ioss_amount_usd": _float(order.cj_ioss_amount_usd),
            "cj_paid_at": order.cj_paid_at,
            "attempt_count": order.attempt_count,
            "last_attempt_at": order.last_attempt_at,
            "next_retry_at": order.next_retry_at,
            "last_error_kind": order.last_error_kind,
            "cj_order_id": order.cj_order_id,
            "cj_order_status": order.cj_order_status,
            "cj_amount_usd": float(order.cj_amount_usd) if order.cj_amount_usd is not None else None,
            "sandbox": order.sandbox,
            "logistic_name": order.logistic_name,
            "origin_country": order.origin_country,
            "unit_cost_usd": float(order.unit_cost_usd),
            "shipping_cost_usd": float(order.shipping_cost_usd),
            "usd_eur_rate": float(order.usd_eur_rate),
            "estimated_margin_cents": order.amount_cents - cost_cents,
            "forwarded_at": order.forwarded_at,
            "forward_error": order.forward_error,
            "last_cj_sync_at": order.last_cj_sync_at,
        })
    return out


# --- Ordini: pagamento (identico agli altri negozi) ---------------------------------------------------


async def confirm_payment(db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID) -> CjOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise CjNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise CjValidationError("Questo ordine non è in attesa di pagamento.")
    if order.payment_method == "CARD":
        raise CjValidationError("Un ordine pagato con carta viene confermato automaticamente da Stripe.")
    order.status = "PAID"
    order.paid_by_user_id = actor_user_id
    order.paid_at = utcnow()
    await _notify_paid(db, order=order, by_card=False)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


async def mark_paid_via_stripe(db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str) -> CjOrder | None:
    order = (
        await db.execute(
            select(CjOrder).where(
                CjOrder.organization_id == organization_id,
                CjOrder.stripe_checkout_session_id == stripe_checkout_session_id,
            )
        )
    ).scalar_one_or_none()
    if order is None or order.status != "AWAITING_PAYMENT":
        return order
    order.status = "PAID"
    order.paid_at = utcnow()
    await _notify_paid(db, order=order, by_card=True)
    await db.commit()
    await db.refresh(order)
    await after_paid(db, order=order)
    return order


async def _notify_paid(db: AsyncSession, *, order: CjOrder, by_card: bool) -> None:
    product = await db.get(CjProduct, order.cj_product_id)
    name = product.name if product else "un prodotto"
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="cj_order", entity_id=order.id, title=f"Il tuo ordine per {name} è confermato",
        body="Ti avvisiamo appena viene spedito.",
    )
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="CJ_ORDER_PAID", entity_type="cj_order", entity_id=order.id,
        title=f"{'Pagamento Stripe' if by_card else 'Bonifico'} confermato: {name}",
        body=f"{order.amount_cents / 100:.2f} EUR -- da inviare a CJ",
    )


async def cancel_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> CjOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise CjNotFoundError("Ordine non trovato.")
    if order.status != "AWAITING_PAYMENT":
        raise CjValidationError("Si può annullare solo un ordine non ancora pagato.")
    if order.credit_debit_transaction_id is not None:
        await wallets_service.reverse_transaction(
            db, organization_id=organization_id, transaction_id=order.credit_debit_transaction_id,
            actor_user_id=actor_user_id, reason=f"Ordine annullato: {reason}",
            idempotency_key=f"cj-order:{order.id}:cancel-refund",
        )
    order.status = "CANCELLED"
    order.cancelled_by_user_id = actor_user_id
    order.cancelled_at = utcnow()
    order.cancellation_reason = reason
    await db.commit()
    await db.refresh(order)
    return order


async def change_payment_method(db: AsyncSession, *, organization_id: uuid.UUID, order: CjOrder, new_payment_method: str) -> CjOrder:
    if order.status != "AWAITING_PAYMENT":
        raise CjValidationError("Il metodo di pagamento si cambia solo prima di pagare.")
    if new_payment_method not in CJ_ORDER_PAYMENT_METHODS:
        raise CjValidationError("Metodo di pagamento non valido.")
    if new_payment_method != order.payment_method:
        methods = await payment_methods(db, organization_id=organization_id)
        if new_payment_method == "BANK_TRANSFER" and not methods["bank_transfer"]:
            raise CjValidationError("Il pagamento con bonifico non è configurato.")
        if new_payment_method == "CARD" and not methods["card"]:
            raise CjValidationError("Il pagamento con carta non è configurato.")
        if order.payment_method == "CARD":
            order.stripe_checkout_session_id = None
        order.payment_method = new_payment_method
        await db.commit()
        await db.refresh(order)
    return order


async def upload_payment_proof(
    db: AsyncSession, *, organization_id: uuid.UUID, order: CjOrder, file_bytes: bytes, content_type: str,
    original_filename: str, actor_user_id: uuid.UUID,
) -> CjOrder:
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document

    if order.status != "AWAITING_PAYMENT" or order.payment_method != "BANK_TRANSFER":
        raise CjValidationError("La ricevuta si carica solo per un ordine da pagare con bonifico.")
    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type, key_prefix=f"cj-order-payment-proofs/{order.customer_user_id}"
        )
    except UploadValidationError as exc:
        raise CjValidationError(str(exc)) from exc
    order.payment_proof_storage_key = storage_key
    order.payment_proof_original_filename = original_filename
    order.payment_proof_uploaded_at = utcnow()
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAYMENT_PROOF_UPLOADED", entity_type="cj_order", entity_id=order.id,
        title="Ricevuta di bonifico caricata: ordine Shop Lial Partner", body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(order)
    return order


def presigned_payment_proof_url(order: CjOrder) -> str:
    from app.core.storage import generate_presigned_document_url

    assert order.payment_proof_storage_key is not None
    return generate_presigned_document_url(storage_key=order.payment_proof_storage_key, expires_in_seconds=300)


async def attach_stripe_checkout_session(db: AsyncSession, *, order: CjOrder, session_id: str) -> CjOrder:
    order.payment_method = "CARD"
    order.stripe_checkout_session_id = session_id
    await db.commit()
    await db.refresh(order)
    return order


async def _send_order_email(db: AsyncSession, *, order: CjOrder, product: CjProduct, variant: CjVariant) -> None:
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
    if order.status == "PAID":
        heading = "Ordine confermato"
        lines += "<p>Nessun altro pagamento richiesto: ti avvisiamo appena viene spedito.</p>"
    elif order.payment_method == "CARD":
        from app.domains.payments import service as payments_service

        heading = "Completa il pagamento del tuo ordine"
        lines += f"<p>Da pagare con carta: <strong>{residual / 100:.2f} &euro;</strong></p>"
        try:
            cta_url = await payments_service.create_checkout_session_for_cj_order(
                db, organization_id=order.organization_id, order=order,
                success_url=f"{settings.public_app_base_url}/customer?tab=orders",
                cancel_url=f"{settings.public_app_base_url}/customer?tab=orders",
            )
            cta_label = "Paga con carta"
        except (payments_service.StripeNotConfiguredError, stripe.error.StripeError):
            logger.exception("CJ order %s confirmation email sent without a Stripe link", order.id)
    else:
        bank = await organizations_service.get_settings(db, organization_id=order.organization_id)
        heading = "Completa il pagamento del tuo ordine"
        lines += f"<p>Da pagare con bonifico: <strong>{residual / 100:.2f} &euro;</strong></p>"
        if bank.get("bank_iban"):
            lines += (
                f"<p><strong>IBAN:</strong> {bank['bank_iban']}<br>"
                f"<strong>Intestatario:</strong> {bank.get('bank_account_holder') or 'Lial Energy'}<br>"
                f"<strong>Causale:</strong> Ordine {code}</p>"
            )
    send_html_email_best_effort(
        context=f"CJ order confirmation email (order={order.id})",
        to=user.email,
        subject=f"Conferma ordine - {product.name} - Lial Energy",
        html_body=render_email(
            preheader=f"Riepilogo del tuo ordine -- {product.name}", heading=heading, body_html=lines,
            cta_label=cta_label, cta_url=cta_url,
        ),
        text_body=f"{heading}: {product.name}, totale {order.amount_cents / 100:.2f} EUR.",
    )


# --- Evasione su CJ ----------------------------------------------------------------------------------------
#
# Session 63, "hybrid": the order is created on CJ once, as soon as the
# customer has paid; it is paid from the CJ balance only when the balance
# covers it. Otherwise it waits as PAYMENT_REQUIRED -- payable on CJ's own
# page for that order, or from the balance once topped up -- and the customer
# keeps seeing "Ordine ricevuto". Nothing is ever shown as in preparation
# before CJ has the money, and a missing balance is never an error.
#
# Facts verified against the live API (sandbox order, Session 63):
# - getOrderDetail with our own number answers code 1600300 when the order
#   does not exist: only that answer allows creating it.
# - createOrderV2 returns CJ's "SD..." code as orderId and the amounts
#   (orderAmount = product + postage + IOSS VAT); payType=1 returns cjPayUrl
#   for real orders (sandbox orders are paid by CJ at creation instead).
# - payBalance on an order already paid answers "order status is not unpaid".

#: CJ order statuses meaning CJ has been paid.
CJ_PAID_STATUSES = {"UNSHIPPED", "PENDING", "PROCESSING", "SHIPPED", "DELIVERED"}
#: getOrderDetail's answer for an order that does not exist.
CJ_NOT_FOUND_CODES = {1600300, 803}
MAX_ATTEMPTS = 6
PAYMENT_RECHECK_MINUTES = 30


def _float(value) -> float | None:
    return float(value) if value is not None else None


def cj_cost_usd(order: CjOrder) -> Decimal:
    """What CJ charges for this order: the real amount once CJ has created
    it, until then the estimate frozen at checkout (with estimated IOSS)."""
    if order.cj_amount_usd is not None:
        return Decimal(order.cj_amount_usd)
    product = Decimal(order.unit_cost_usd) * order.quantity
    return product + Decimal(order.shipping_cost_usd) + estimated_ioss_usd(
        product_usd=product, origin=order.origin_country, destination=order.country_code
    )


def delivery_status(order: CjOrder) -> str | None:
    """The only shipping state a customer ever sees. "RECEIVED" covers
    everything before CJ is paid, whatever the reason."""
    if order.status != "PAID":
        return None
    if order.fulfillment_status == "CJ_CANCELLED":
        return "PROBLEM"
    if order.fulfillment_status == "DELIVERED":
        return "DELIVERED"
    if order.fulfillment_status == "SHIPPED":
        return "SHIPPED"
    if order.cj_payment_status == "PAID":
        return "PREPARING"
    return "RECEIVED"


def classify_error(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    text = str(exc).lower()
    if "balance" in text or "insufficient" in text or "余额" in text:
        return "INSUFFICIENT_BALANCE"
    if code in cj.TOKEN_ERROR_CODES or isinstance(exc, cj.CjNotConfiguredError) or "chiave api" in text:
        return "AUTHENTICATION"
    if code in (None, 429, 1600000, 1600200) or "non risponde" in text or "occupato" in text or "troppe richieste" in text:
        return "TEMPORARY"
    if code in (1600100, 1600300, 1603001) or "param" in text or "address" in text or "non ha creato" in text:
        return "VALIDATION"
    return "FATAL"


def _schedule_retry(order: CjOrder, kind: str) -> None:
    order.last_error_kind = kind
    if kind in ("TEMPORARY", "AUTHENTICATION") and order.attempt_count < MAX_ATTEMPTS:
        minutes = min(5 * 2 ** max(order.attempt_count - 1, 0), 360)
        order.next_retry_at = utcnow() + timedelta(minutes=minutes)
    else:
        order.next_retry_at = None


async def _staff_alert(db: AsyncSession, *, order: CjOrder, type_: str, title: str, body: str) -> None:
    await notifications_service.notify_roles(
        db, organization_id=order.organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_=type_, entity_type="cj_order", entity_id=order.id, title=title[:255], body=body[:1000],
    )


def _apply_remote(order: CjOrder, item: dict) -> None:
    """Identifiers, amounts and status as CJ reports them."""
    code = item.get("cjOrderCode")
    if item.get("orderId"):
        order.cj_order_id = str(item["orderId"])
    if code:
        order.cj_order_code = str(code)
    if item.get("orderStatus"):
        order.cj_order_status = item["orderStatus"]
    if item.get("orderAmount") not in (None, ""):
        order.cj_amount_usd = _decimal(item["orderAmount"])
    if item.get("productAmount") not in (None, ""):
        order.cj_product_amount_usd = _decimal(item["productAmount"])
    if item.get("postageAmount") not in (None, ""):
        order.cj_postage_amount_usd = _decimal(item["postageAmount"])


def _mark_cj_paid(order: CjOrder) -> None:
    if order.cj_payment_status != "PAID":
        order.cj_payment_status = "PAID"
        order.cj_paid_at = utcnow()
    if order.fulfillment_status in ("SENDING", "SENT"):
        order.fulfillment_status = "PROCESSING"
    order.forward_error = None
    order.last_error_kind = None
    order.next_retry_at = None


async def _require_payment(
    db: AsyncSession, *, order: CjOrder, row: CjSettings, balance_usd: Decimal | None, reason: str | None = None
) -> None:
    """Waiting for money is a state, not an error: no customer message, one
    staff notification when the order starts waiting."""
    first_time = order.cj_payment_status != "PAYMENT_REQUIRED"
    order.cj_payment_status = "PAYMENT_REQUIRED"
    order.last_error_kind = "INSUFFICIENT_BALANCE"
    order.forward_error = reason
    order.next_retry_at = utcnow() + timedelta(minutes=PAYMENT_RECHECK_MINUTES)
    if first_time:
        cost = cj_cost_usd(order)
        euros = pricing.usd_to_eur_cents(cost, Decimal(row.usd_eur_rate)) / 100
        balance_line = (
            f"Saldo CJ ${balance_usd:.2f}: mancano ${max(cost - balance_usd, Decimal(0)):.2f}. "
            if balance_usd is not None else ""
        )
        await _staff_alert(
            db, order=order, type_="CJ_PAYMENT_REQUIRED",
            title=f"Ordine #{str(order.id)[:8].upper()} pagato dal cliente: CJ richiede ${cost:.2f} (≈ {euros:.2f} €)",
            body=balance_line + "Pagalo dalla pagina di pagamento CJ o ricarica il saldo: Shop Lial Partner → Ordini.",
        )


async def _create_body(db: AsyncSession, order: CjOrder) -> dict:
    variant = await db.get(CjVariant, order.cj_variant_id)
    user = await db.get(User, order.customer_user_id)
    body = {
        "orderNumber": order_number(order),
        "shippingCountryCode": order.country_code,
        "shippingCountry": COUNTRY_NAMES.get(order.country_code, order.country_code),
        "shippingProvince": order.province[:50],
        "shippingCity": order.city[:50],
        "shippingZip": order.postal_code,
        "shippingPhone": (order.recipient_phone or "")[:20],
        "shippingCustomerName": order.recipient_name[:50],
        "shippingAddress": order.address_line1,
        "shippingAddress2": order.address_line2 or "",
        "email": (user.email if user else "")[:50],
        "remark": f"Lial Energy {str(order.id)[:8].upper()}",
        "logisticName": order.logistic_name,
        "fromCountryCode": order.origin_country,
        # 1 = page payment: CJ confirms the order and returns a payment page
        # for it (cjPayUrl), so it can be paid without any balance. Paying
        # from the balance, when it is enough, is a separate call.
        "payType": 1,
        "isSandbox": 1 if order.sandbox else 0,
        "products": [{"vid": variant.cj_vid, "quantity": order.quantity, "storeLineItemId": str(order.id)}],
    }
    if order.country_code in EU_COUNTRIES and order.origin_country not in EU_COUNTRIES:
        # VAT on imports into the EU collected through CJ's IOSS.
        body["iossType"] = 3
    return body


async def forward_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID | None,
    balance_usd: Decimal | None = None,
) -> CjOrder:
    """Brings a paid order as far as it can go on CJ: created (once), then
    paid if the balance allows. Safe to call any number of times, by the
    automatic flow, the retry job or an administrator.

    - One process at a time: a conditional UPDATE claims the order
      (-> SENDING); a claim older than 10 minutes (worker died) is taken over.
    - Never two CJ orders: before creating, CJ is asked for our own order
      number; only CJ's "order not found" allows creating. Any other answer
      (timeout, busy) stops here and retries later.
    - Never two payments: before paying, CJ's own status is read; an order
      already paid on CJ (e.g. by hand on CJ's page) is only recorded as paid.
    """
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise CjNotFoundError("Ordine non trovato.")
    if order.status != "PAID":
        raise CjValidationError("Si invia a CJ solo un ordine già pagato dal cliente.")
    if order.cj_payment_status == "PAID" or order.fulfillment_status in ("PROCESSING", "SHIPPED", "DELIVERED", "CJ_CANCELLED"):
        raise CjValidationError("Questo ordine è già pagato su CJ.")
    now = utcnow()
    claimed = await db.execute(
        update(CjOrder)
        .where(
            CjOrder.id == order.id,
            CjOrder.cj_payment_status != "PAID",
            or_(
                CjOrder.fulfillment_status.in_(("NOT_SENT", "ERROR", "SENT")),
                and_(CjOrder.fulfillment_status == "SENDING", CjOrder.last_attempt_at < now - timedelta(minutes=10)),
            ),
        )
        .values(fulfillment_status="SENDING", last_attempt_at=now, attempt_count=CjOrder.attempt_count + 1)
    )
    await db.commit()
    if claimed.rowcount != 1:
        await db.refresh(order)
        raise CjValidationError("Questo ordine è già in lavorazione proprio ora.")
    await db.refresh(order)
    row = await get_settings_row(db, organization_id=organization_id)
    step = "create"
    try:
        if not order.cj_order_id:
            try:
                found = await cj.get_order(db, row, cj_order_id=order_number(order))
            except cj.CjApiError as exc:
                if exc.code not in CJ_NOT_FOUND_CODES:
                    raise  # unknown: never create blindly
                found = {}
            if found and (found.get("orderId") or found.get("cjOrderCode")):
                _apply_remote(order, found)
                logger.info("CJ order %s already on CJ as %s: picked up", order.id, order.cj_order_id)
            else:
                created = await cj.create_order(db, row, body=await _create_body(db, order))
                if not created.get("orderId"):
                    reasons = "; ".join(r.get("message", "") for r in created.get("interceptOrderReasons") or [])
                    raise cj.CjApiError(f"CJ non ha creato l'ordine. {reasons}".strip(), code=1600100)
                order.cj_order_code = str(created["orderId"])
                order.cj_order_id = str(created["orderId"])
                order.cj_shipment_order_id = created.get("shipmentOrderId") or None
                order.cj_pay_url = created.get("cjPayUrl") or None
                if created.get("orderStatus"):
                    order.cj_order_status = created["orderStatus"]
                for field, key in (
                    ("cj_amount_usd", "orderAmount"), ("cj_product_amount_usd", "productAmount"),
                    ("cj_postage_amount_usd", "postageAmount"), ("cj_ioss_amount_usd", "iossAmount"),
                ):
                    if created.get(key) not in (None, ""):
                        setattr(order, field, _decimal(created[key]))
                logger.info("CJ order %s created on CJ as %s", order.id, order.cj_order_id)
            order.fulfillment_status = "SENT"
            order.forwarded_at = order.forwarded_at or utcnow()
            order.forwarded_by_user_id = actor_user_id
            if order.cj_payment_status == "NOT_REQUIRED":
                order.cj_payment_status = "PENDING"
            order.forward_error = None
            await audit_service.record(
                db, organization_id=organization_id, actor_user_id=actor_user_id,
                action="cj.order_created", entity_type="cj_order", entity_id=str(order.id),
                new_value={"cj_order_id": order.cj_order_id, "sandbox": order.sandbox},
            )
            await db.commit()

        step = "pay"
        # What CJ says now: paid at creation (sandbox), paid by hand on CJ's
        # page, or still waiting.
        remote = await cj.get_order(db, row, cj_order_id=order_number(order))
        if remote:
            _apply_remote(order, remote)
        if order.cj_order_status in CJ_PAID_STATUSES:
            _mark_cj_paid(order)
        else:
            if balance_usd is None:
                balance = await cj.get_balance(db, row)
                balance_usd = _decimal(balance.get("amount"))
                row.last_balance_usd = balance_usd
                row.last_balance_at = utcnow()
            cost = cj_cost_usd(order)
            if balance_usd < cost:
                order.fulfillment_status = "SENT"
                await _require_payment(db, order=order, row=row, balance_usd=balance_usd)
            else:
                try:
                    await cj.pay_balance(db, row, cj_order_id=order.cj_order_code or order.cj_order_id)
                except cj.CjApiError as exc:
                    if "not unpaid" in str(exc).lower():
                        _mark_cj_paid(order)  # paid meanwhile: nothing to do
                    else:
                        raise
                else:
                    _mark_cj_paid(order)
                    order.cj_order_status = "UNSHIPPED"
                    logger.info("CJ order %s paid from the CJ balance ($%s)", order.id, cost)
        if order.fulfillment_status == "SENDING":
            order.fulfillment_status = "SENT"
        await db.commit()
    except cj.CjApiError as exc:
        kind = classify_error(exc)
        logger.warning("CJ %s failed for order %s (%s): %s", step, order.id, kind, exc)
        order.fulfillment_status = "SENT" if order.cj_order_id else "ERROR"
        if order.cj_order_id and kind == "INSUFFICIENT_BALANCE":
            await _require_payment(db, order=order, row=row, balance_usd=row.last_balance_usd, reason=str(exc)[:500])
        else:
            order.forward_error = str(exc)[:500]
            if order.cj_order_id:
                order.cj_payment_status = "FAILED"
            _schedule_retry(order, kind)
            if order.next_retry_at is None:
                await _staff_alert(
                    db, order=order, type_="CJ_ORDER_FAILED",
                    title=f"Ordine #{str(order.id)[:8].upper()}: serve un controllo su CJ",
                    body=f"{exc}. Il cliente ha pagato e vede \"Ordine ricevuto\". Shop Lial Partner → Ordini.",
                )
        await db.commit()
    await db.refresh(order)
    return order


async def sync_orders(db: AsyncSession, *, organization_id: uuid.UUID, orders: list[CjOrder] | None = None) -> int:
    """Asks CJ about every order still open (waiting for payment on CJ, in
    preparation, shipped): payment seen on CJ, status, tracking, delivery.
    Tells the customer when their parcel leaves and when it arrives. Closed
    orders (delivered, cancelled) are never asked about. Returns how many
    orders changed."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.api_key:
        return 0
    if orders is None:
        orders = list(
            (
                await db.execute(
                    select(CjOrder).where(
                        CjOrder.organization_id == organization_id,
                        CjOrder.cj_order_id.is_not(None),
                        CjOrder.fulfillment_status.in_(FOLLOWED_FULFILLMENT),
                    )
                )
            ).scalars()
        )
    changed = 0
    for start in range(0, len(orders), 50):
        batch = orders[start:start + 50]
        data = await cj.get_orders(db, row, cj_order_ids=[o.cj_order_id for o in batch])
        by_id = {}
        for item in data if isinstance(data, list) else []:
            for key in ("orderId", "orderNum", "cjOrderCode"):
                if item.get(key):
                    by_id[str(item[key])] = item
        for order in batch:
            item = (
                by_id.get(order.cj_order_id or "") or by_id.get(order.cj_order_code or "")
                or by_id.get(order_number(order))
            )
            order.last_cj_sync_at = utcnow()
            if not item:
                continue
            status = item.get("orderStatus")
            previous = order.fulfillment_status
            previous_payment = order.cj_payment_status
            previous_tracking = order.tracking_number
            _apply_remote(order, item)
            if status in CJ_PAID_STATUSES:
                _mark_cj_paid(order)
            new_fulfillment = CJ_STATUS_TO_FULFILLMENT.get(status or "", order.fulfillment_status)
            if order.fulfillment_status != "SENDING":
                order.fulfillment_status = new_fulfillment
            tracking = item.get("trackNumber")
            if tracking:
                order.tracking_number = tracking
                order.tracking_provider = item.get("trackingProvider") or item.get("logisticName")
            if (
                order.fulfillment_status == previous and order.cj_payment_status == previous_payment
                and order.tracking_number == previous_tracking
            ):
                continue
            changed += 1
            if order.fulfillment_status == "SHIPPED" and previous != "SHIPPED":
                order.shipped_at = utcnow()
                await _notify_customer_shipping(db, order=order, delivered=False)
            elif order.fulfillment_status == "DELIVERED" and previous != "DELIVERED":
                order.delivered_at = utcnow()
                order.shipped_at = order.shipped_at or utcnow()
                await _notify_customer_shipping(db, order=order, delivered=True)
            elif order.fulfillment_status == "CJ_CANCELLED" and previous != "CJ_CANCELLED":
                await _staff_alert(
                    db, order=order, type_="CJ_ORDER_FAILED",
                    title=f"CJ ha annullato l'ordine {str(order.id)[:8].upper()}",
                    body="Il cliente ha già pagato: valuta rimborso o nuovo invio.",
                )
        await db.commit()
    return changed


async def retry_due_orders(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """The safety net of the automatic flow, run every few minutes:
    - paid orders never sent (the automatic send did not start);
    - temporary failures whose retry time has come (bounded attempts);
    - orders waiting for money, paid from the balance as soon as the balance
      covers them, oldest first. The balance is read once per run and spent
      locally, so one top-up is never "used" twice.
    Never tops up, never moves money other than paying CJ orders from the
    CJ balance that the administrator enabled."""
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.api_key or not row.auto_forward:
        return 0
    await sync_orders(db, organization_id=organization_id, orders=list(
        (await db.execute(select(CjOrder).where(
            CjOrder.organization_id == organization_id,
            CjOrder.cj_order_id.is_not(None),
            CjOrder.cj_payment_status.in_(("PENDING", "PAYMENT_REQUIRED", "FAILED")),
        ))).scalars()
    ))
    now = utcnow()
    due = list(
        (
            await db.execute(
                select(CjOrder)
                .where(
                    CjOrder.organization_id == organization_id,
                    CjOrder.status == "PAID",
                    CjOrder.cj_payment_status != "PAID",
                    or_(
                        and_(CjOrder.fulfillment_status == "NOT_SENT", CjOrder.paid_at < now - timedelta(minutes=2)),
                        and_(
                            CjOrder.fulfillment_status.in_(("ERROR", "SENT")),
                            CjOrder.next_retry_at.is_not(None),
                            CjOrder.next_retry_at <= now,
                        ),
                    ),
                )
                .order_by(CjOrder.paid_at)
            )
        ).scalars()
    )
    if not due:
        return 0
    balance_usd: Decimal | None = None
    handled = 0
    for order in due:
        available: Decimal | None = None
        if order.cj_order_id and order.cj_payment_status in ("PAYMENT_REQUIRED", "PENDING"):
            if balance_usd is None:
                try:
                    balance_usd = _decimal((await cj.get_balance(db, row)).get("amount"))
                except cj.CjApiError:
                    return handled
                row.last_balance_usd = balance_usd
                row.last_balance_at = utcnow()
                await db.commit()
            cost = cj_cost_usd(order)
            if balance_usd < cost:
                order.next_retry_at = utcnow() + timedelta(minutes=PAYMENT_RECHECK_MINUTES)
                await db.commit()
                continue
            available = balance_usd
            balance_usd -= cost
        try:
            await forward_order(
                db, organization_id=organization_id, order_id=order.id, actor_user_id=None, balance_usd=available
            )
            handled += 1
        except CjError:
            continue
    return handled


async def cash_requirement(db: AsyncSession, *, organization_id: uuid.UUID, refresh_balance: bool) -> dict:
    """How much money CJ needs to release every order customers have already
    paid: the sum of CJ's cost of those orders, the CJ balance, the gap."""
    row = await get_settings_row(db, organization_id=organization_id)
    if refresh_balance and row.api_key:
        try:
            balance = await cj.get_balance(db, row)
            row.last_balance_usd = _decimal(balance.get("amount"))
            row.last_balance_at = utcnow()
            await db.commit()
        except cj.CjApiError:
            pass
    orders = list(
        (
            await db.execute(
                select(CjOrder).where(
                    CjOrder.organization_id == organization_id,
                    CjOrder.status == "PAID",
                    CjOrder.cj_payment_status != "PAID",
                    CjOrder.fulfillment_status != "CJ_CANCELLED",
                )
            )
        ).scalars()
    )
    required = sum((cj_cost_usd(o) for o in orders), Decimal(0))
    balance = Decimal(row.last_balance_usd) if row.last_balance_usd is not None else None
    rate = Decimal(row.usd_eur_rate)
    shortfall = max(required - (balance or Decimal(0)), Decimal(0))
    return {
        "orders_to_pay": len(orders),
        "orders_payment_required": sum(1 for o in orders if o.cj_payment_status == "PAYMENT_REQUIRED"),
        "required_usd": float(required),
        "required_cents": pricing.usd_to_eur_cents(required, rate) if required else 0,
        "balance_usd": float(balance) if balance is not None else None,
        "balance_at": row.last_balance_at,
        "shortfall_usd": float(shortfall),
        "shortfall_cents": pricing.usd_to_eur_cents(shortfall, rate) if shortfall else 0,
        "sandbox": row.sandbox,
        "auto_forward": row.auto_forward,
    }


async def _notify_customer_shipping(db: AsyncSession, *, order: CjOrder, delivered: bool) -> None:
    product = await db.get(CjProduct, order.cj_product_id)
    name = product.name if product else "il tuo ordine"
    title = f"{name} è stato consegnato" if delivered else f"{name} è stato spedito"
    body = None if delivered else (f"Numero di tracking: {order.tracking_number}" if order.tracking_number else None)
    await notifications_service.notify_user(
        db, organization_id=order.organization_id, user_id=order.customer_user_id, type_="ORDER_SHIPPED",
        entity_type="cj_order", entity_id=order.id, title=title, body=body,
    )
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return
    link = tracking_url(order.tracking_number)
    body_html = (
        f"<p>Numero ordine: <strong>#{str(order.id)[:8].upper()}</strong></p>"
        f"<p><strong>{html.escape(name)}</strong> {'è stato consegnato' if delivered else 'è in viaggio verso di te'}.</p>"
    )
    if not delivered and order.tracking_number:
        body_html += f"<p>Numero di tracking: <strong>{html.escape(order.tracking_number)}</strong></p>"
    send_html_email_best_effort(
        context=f"CJ order shipping email (order={order.id}, delivered={delivered})",
        to=user.email,
        subject=f"{'Consegnato' if delivered else 'Spedito'}: {name} - Lial Energy",
        html_body=render_email(
            preheader=title, heading=title, body_html=body_html,
            cta_label=None if delivered or not link else "Segui la spedizione",
            cta_url=None if delivered else link,
        ),
        text_body=title + (f" Tracking: {order.tracking_number}" if order.tracking_number and not delivered else ""),
    )


async def sync_all_products(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    row = await get_settings_row(db, organization_id=organization_id)
    if not row.api_key:
        return 0
    products = await list_products(db, organization_id=organization_id, active_only=False)
    for product in products:
        await sync_product(db, row=row, product=product)
    return len(products)
