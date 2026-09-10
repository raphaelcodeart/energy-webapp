import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.catalog.models import ProductVersion
from app.domains.imported_products import service as imported_products_service
from app.domains.imported_products.models import ImportedProduct
from app.domains.invoice_redemptions import service as invoice_redemptions_service
from app.domains.invoice_redemptions.models import InvoiceRedemption
from app.domains.orders import service as orders_service
from app.domains.orders.models import Order
from app.domains.partners.models import Partner
from app.domains.wallets import service as wallets_service


async def _product_name_lookups(db: AsyncSession, wallet_txns: list[dict]) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, str]]:
    """Batched (not N+1) resolution of "what this WALLET row is about", for
    both list_my_movements and list_all_movements: (product_name_by_order_id,
    partner_name_by_redemption_id). order_id covers both regular orders and
    imported-products orders -- two tables internally, one merged lookup
    (see FinancialMovementRead's docstring)."""
    order_ids = {t["reference_order_id"] for t in wallet_txns if t["reference_order_id"] is not None}
    product_name_by_order_id: dict[uuid.UUID, str] = {}
    if order_ids:
        orders = (await db.execute(select(Order).where(Order.id.in_(order_ids)))).scalars().all()
        version_ids = {o.product_version_id for o in orders}
        versions = {
            v.id: v
            for v in (
                await db.execute(select(ProductVersion).where(ProductVersion.id.in_(version_ids)))
            ).scalars()
        }
        for order in orders:
            version = versions.get(order.product_version_id)
            if version is not None:
                product_name_by_order_id[order.id] = version.name

    imported_order_ids = {
        t["reference_imported_order_id"] for t in wallet_txns if t["reference_imported_order_id"] is not None
    }
    if imported_order_ids:
        imported_orders = (
            await db.execute(
                select(imported_products_service.ImportedProductOrder).where(
                    imported_products_service.ImportedProductOrder.id.in_(imported_order_ids)
                )
            )
        ).scalars().all()
        imported_product_ids = {o.imported_product_id for o in imported_orders}
        imported_products = {
            p.id: p
            for p in (
                await db.execute(select(ImportedProduct).where(ImportedProduct.id.in_(imported_product_ids)))
            ).scalars()
        }
        for imported_order in imported_orders:
            product = imported_products.get(imported_order.imported_product_id)
            if product is not None:
                product_name_by_order_id[imported_order.id] = product.name

    redemption_ids = {
        t["reference_invoice_redemption_id"] for t in wallet_txns if t["reference_invoice_redemption_id"] is not None
    }
    partner_name_by_redemption_id: dict[uuid.UUID, str] = {}
    if redemption_ids:
        redemptions = (
            await db.execute(select(InvoiceRedemption).where(InvoiceRedemption.id.in_(redemption_ids)))
        ).scalars().all()
        partner_ids = {r.partner_id for r in redemptions}
        partners = {
            p.id: p for p in (await db.execute(select(Partner).where(Partner.id.in_(partner_ids)))).scalars()
        }
        for redemption in redemptions:
            partner = partners.get(redemption.partner_id)
            if partner is not None:
                partner_name_by_redemption_id[redemption.id] = partner.name

    return product_name_by_order_id, partner_name_by_redemption_id


def _order_payment_row(row: dict) -> dict | None:
    """The real-money leg of a PAID order (regular or imported-products,
    see FinancialMovementRead's docstring) -- what was actually charged via
    Stripe/bonifico, excluding any LialCash applied (shown separately as
    its own PURCHASE_DEBIT WALLET row) and, for a regular order, any
    cashback surcharge added back in (it's part of what was genuinely
    charged). None when credit alone covered the whole price -- nothing
    real-money to show."""
    paid_amount_cents = row["amount_cents"] - row["credit_applied_cents"] + row.get("cashback_surcharge_cents", 0)
    if paid_amount_cents <= 0:
        return None
    return {
        "id": f"order-{row['id']}",
        "kind": "ORDER_PAYMENT",
        "type": None,
        "source": None,
        "payment_method": row["payment_method"],
        "amount_cents": paid_amount_cents,
        "currency": "EUR",
        "product_name": row["product_name"],
        "order_id": row["id"],
        "invoice_redemption_id": None,
        "note": None,
        "customer_user_id": row["customer_user_id"],
        "customer_display_name": row["customer_display_name"],
        "created_at": row["paid_at"] or row["created_at"],
    }


def _redemption_payment_row(row: dict) -> dict | None:
    """The real-money leg of a CREDITED invoice redemption -- the
    CASHBACK_PERCENTAGE% fee actually paid via Stripe/bonifico to redeem
    the invoice. Previously entirely missing from Contabilità: only the two
    LialCash credit rows (base + bonus, tagged reference_invoice_redemption_id)
    ever showed, with no trace of the real money that unlocked them. Same
    "what was genuinely charged" principle as _order_payment_row."""
    due_cents = row["payment_due_cents"]
    if not due_cents or due_cents <= 0:
        return None
    return {
        "id": f"redemption-{row['id']}",
        "kind": "REDEMPTION_PAYMENT",
        "type": None,
        "source": None,
        "payment_method": row["payment_method"],
        "amount_cents": due_cents,
        "currency": "EUR",
        "product_name": row["partner_name"],
        "order_id": None,
        "invoice_redemption_id": row["id"],
        "note": None,
        "customer_user_id": row["customer_user_id"],
        "customer_display_name": row["customer_display_name"],
        "created_at": row["credited_at"] or row["created_at"],
    }


async def list_my_movements(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
    """Merges this user's own WalletTransaction rows (LialCash -- every
    movement in/out of their internal wallet) with their own PAID orders'
    and CREDITED invoice redemptions' real-money payments (EUR, whichever
    residual/fee they actually paid via Stripe or bonifico), newest first.
    "Orders" here means both regular orders (orders.id) and imported-products
    orders (imported_product_orders.id) -- two tables internally, presented
    as one continuous history (see FinancialMovementRead's docstring).
    Read-only, computed fresh on every call -- no new table, every
    underlying source stays each domain's own single source of truth."""
    wallet = await wallets_service.get_or_create_wallet(db, organization_id=organization_id, user_id=user_id)
    wallet_txns = await wallets_service.list_transactions_for_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, limit=500
    )
    product_name_by_order_id, partner_name_by_redemption_id = await _product_name_lookups(db, wallet_txns)

    movements = []
    for t in wallet_txns:
        is_outgoing = t["from_wallet_id"] == wallet.id
        # Unified order_id: either reference id resolves to the same
        # product_name_by_order_id dict and is presented identically from
        # here on -- see FinancialMovementRead's docstring for why.
        unified_order_id = t["reference_order_id"] or t["reference_imported_order_id"]
        product_name = None
        if unified_order_id:
            product_name = product_name_by_order_id.get(unified_order_id)
        elif t["reference_invoice_redemption_id"]:
            product_name = partner_name_by_redemption_id.get(t["reference_invoice_redemption_id"])
        movements.append(
            {
                "id": str(t["id"]),
                "kind": "WALLET",
                "type": t["type"],
                "source": t["source"],
                "payment_method": None,
                "amount_cents": -t["amount_cents"] if is_outgoing else t["amount_cents"],
                "currency": "LIALCASH",
                "product_name": product_name,
                "order_id": unified_order_id,
                "invoice_redemption_id": t["reference_invoice_redemption_id"],
                "note": t["note"],
                "customer_user_id": user_id,
                "customer_display_name": None,
                "created_at": t["created_at"],
            }
        )

    orders_mine = await orders_service.list_orders_for_customer(
        db, organization_id=organization_id, customer_user_id=user_id
    )
    paid_orders = [o for o in orders_mine if o.status == "PAID"]
    order_rows = await orders_service.hydrate(db, paid_orders)
    for row in order_rows:
        movement = _order_payment_row(row)
        if movement is not None:
            movements.append(movement)

    imported_orders_mine = await imported_products_service.list_orders_for_customer(
        db, organization_id=organization_id, customer_user_id=user_id
    )
    paid_imported_orders = [o for o in imported_orders_mine if o.status == "PAID"]
    imported_order_rows = await imported_products_service.hydrate(db, paid_imported_orders)
    for row in imported_order_rows:
        movement = _order_payment_row(row)
        if movement is not None:
            movements.append(movement)

    redemptions_mine = await invoice_redemptions_service.list_mine(db, organization_id=organization_id, user_id=user_id)
    credited_redemptions = [r for r in redemptions_mine if r.status == "CREDITED"]
    redemption_rows = await invoice_redemptions_service.hydrate(db, credited_redemptions)
    for row in redemption_rows:
        movement = _redemption_payment_row(row)
        if movement is not None:
            movements.append(movement)

    movements.sort(key=lambda m: m["created_at"], reverse=True)
    return movements


async def list_all_movements(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID | None = None
) -> list[dict]:
    """Admin-wide "Contabilità" -- every customer's movements merged into
    one list, optionally filtered to a single customer (customer_user_id).
    Same sources and unification as list_my_movements, from an org-wide
    vantage point instead of one wallet's.

    Attribution for a WALLET row: the receiving wallet's owner when there
    is one (to_wallet_id set -- an incoming credit), otherwise the sending
    wallet's owner (an outgoing PURCHASE_DEBIT/REVERSAL-from). A
    peer-to-peer TRANSFER between two different customers is therefore
    shown once here, from the receiver's side only -- an accepted
    simplification for this higher-level summary; the admin Wallets tab
    (admin-wallets-panel.tsx) already shows the full two-sided raw ledger
    for that case."""
    wallet_txns = await wallets_service.list_all_transactions_for_org(
        db, organization_id=organization_id, user_id=customer_user_id, limit=2000
    )
    product_name_by_order_id, partner_name_by_redemption_id = await _product_name_lookups(db, wallet_txns)

    movements = []
    for t in wallet_txns:
        if t.get("to_wallet_id"):
            cust_id, cust_name, is_outgoing = t.get("to_user_id"), t.get("to_display_name"), False
        else:
            cust_id, cust_name, is_outgoing = t.get("from_user_id"), t.get("from_display_name"), True
        unified_order_id = t["reference_order_id"] or t["reference_imported_order_id"]
        product_name = None
        if unified_order_id:
            product_name = product_name_by_order_id.get(unified_order_id)
        elif t["reference_invoice_redemption_id"]:
            product_name = partner_name_by_redemption_id.get(t["reference_invoice_redemption_id"])
        movements.append(
            {
                "id": str(t["id"]),
                "kind": "WALLET",
                "type": t["type"],
                "source": t["source"],
                "payment_method": None,
                "amount_cents": -t["amount_cents"] if is_outgoing else t["amount_cents"],
                "currency": "LIALCASH",
                "product_name": product_name,
                "order_id": unified_order_id,
                "invoice_redemption_id": t["reference_invoice_redemption_id"],
                "note": t["note"],
                "customer_user_id": cust_id,
                "customer_display_name": cust_name,
                "created_at": t["created_at"],
            }
        )

    orders_all = await orders_service.list_orders(db, organization_id=organization_id, status_filter="PAID")
    if customer_user_id is not None:
        orders_all = [o for o in orders_all if o.customer_user_id == customer_user_id]
    order_rows = await orders_service.hydrate(db, orders_all)
    for row in order_rows:
        movement = _order_payment_row(row)
        if movement is not None:
            movements.append(movement)

    imported_orders_all = await imported_products_service.list_orders(db, organization_id=organization_id, status_filter="PAID")
    if customer_user_id is not None:
        imported_orders_all = [o for o in imported_orders_all if o.customer_user_id == customer_user_id]
    imported_order_rows = await imported_products_service.hydrate(db, imported_orders_all)
    for row in imported_order_rows:
        movement = _order_payment_row(row)
        if movement is not None:
            movements.append(movement)

    redemptions_all = await invoice_redemptions_service.list_admin_queue(
        db, organization_id=organization_id, status_filter="CREDITED"
    )
    if customer_user_id is not None:
        redemptions_all = [r for r in redemptions_all if r.customer_user_id == customer_user_id]
    redemption_rows = await invoice_redemptions_service.hydrate(db, redemptions_all)
    for row in redemption_rows:
        movement = _redemption_payment_row(row)
        if movement is not None:
            movements.append(movement)

    movements.sort(key=lambda m: m["created_at"], reverse=True)
    return movements
