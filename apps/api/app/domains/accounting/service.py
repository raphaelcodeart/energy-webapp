import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.catalog.models import ProductVersion
from app.domains.orders import service as orders_service
from app.domains.orders.models import Order
from app.domains.wallets import service as wallets_service


async def list_my_movements(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
    """Merges this user's own WalletTransaction rows (LialCash -- every
    movement in/out of their internal wallet) with their own PAID orders'
    real-money payments (EUR, whichever residual they actually paid via
    Stripe or bonifico), newest first. Read-only, computed fresh on every
    call -- no new table, both underlying sources stay each domain's own
    single source of truth (see FinancialMovementRead's docstring)."""
    wallet = await wallets_service.get_or_create_wallet(db, organization_id=organization_id, user_id=user_id)
    wallet_txns = await wallets_service.list_transactions_for_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, limit=500
    )

    # Resolve a product name for wallet rows tied to an order (a
    # PURCHASE_DEBIT paying part of an order in LialCash, or an
    # ORDER_CASHBACK_BASE/BONUS credit) -- one batched lookup, not N+1.
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

    movements = []
    for t in wallet_txns:
        is_outgoing = t["from_wallet_id"] == wallet.id
        movements.append(
            {
                "id": str(t["id"]),
                "kind": "WALLET",
                "type": t["type"],
                "source": t["source"],
                "payment_method": None,
                "amount_cents": -t["amount_cents"] if is_outgoing else t["amount_cents"],
                "currency": "LIALCASH",
                "product_name": product_name_by_order_id.get(t["reference_order_id"]) if t["reference_order_id"] else None,
                "order_id": t["reference_order_id"],
                "note": t["note"],
                "created_at": t["created_at"],
            }
        )

    orders_mine = await orders_service.list_orders_for_customer(
        db, organization_id=organization_id, customer_user_id=user_id
    )
    paid_orders = [o for o in orders_mine if o.status == "PAID"]
    order_rows = await orders_service.hydrate(db, paid_orders)
    for row in order_rows:
        # What was actually paid in real money for this order -- excludes
        # any LialCash applied (already shown as its own PURCHASE_DEBIT
        # movement above) and any cashback bonus (shown as its own
        # ORDER_CASHBACK_BONUS credit). A 100%-LialCash order has nothing
        # real-money to show here at all.
        paid_amount_cents = row["amount_cents"] - row["credit_applied_cents"] + row["cashback_surcharge_cents"]
        if paid_amount_cents <= 0:
            continue
        movements.append(
            {
                "id": f"order-{row['id']}",
                "kind": "ORDER_PAYMENT",
                "type": None,
                "source": None,
                "payment_method": row["payment_method"],
                "amount_cents": paid_amount_cents,
                "currency": "EUR",
                "product_name": row["product_name"],
                "order_id": row["id"],
                "note": None,
                "created_at": row["paid_at"] or row["created_at"],
            }
        )

    movements.sort(key=lambda m: m["created_at"], reverse=True)
    return movements
