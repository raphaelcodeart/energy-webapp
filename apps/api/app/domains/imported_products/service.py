import logging
import uuid

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.email import EmailNotConfiguredError, send_html_email
from app.core.email_templates import render_email
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.imported_products.models import (
    IMPORTED_ORDER_PAYMENT_METHODS,
    ImportedProduct,
    ImportedProductOrder,
    ImportProvider,
)
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.organizations import service as organizations_service
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service

logger = logging.getLogger(__name__)


class ImportedProductsError(Exception):
    pass


class ProviderNotFoundError(ImportedProductsError):
    pass


class ProductNotEligibleError(ImportedProductsError):
    pass


class InvalidCreditAmountError(ImportedProductsError):
    pass


class InvalidOrderStateError(ImportedProductsError):
    pass


class InvalidPaymentMethodError(ImportedProductsError):
    pass


class PaymentMethodNotAvailableError(ImportedProductsError):
    pass


class PaymentProofError(ImportedProductsError):
    pass


class InvalidOtpError(ImportedProductsError):
    """Same purpose as orders/service.py's own -- self-checkout spending
    existing wallet LialCash needs a fresh, still-valid OTP. Reuses
    auth/service.py's WALLET_CREDIT_SPEND_OTP_PURPOSE, the same purpose code
    the normal orders flow already uses -- there is no reason for these to
    be distinguishable OTP purposes, both confirm the exact same thing
    ("spend my wallet LialCash right now")."""


def max_creditable_cents(*, amount_cents: int, credit_discount_percentage: int) -> int:
    return round(amount_cents * credit_discount_percentage / 100)


# --- Providers ---------------------------------------------------------

async def create_provider(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID,
    provider_type: str, name: str, base_url: str | None, api_key: str | None, enabled: bool,
) -> ImportProvider:
    provider = ImportProvider(
        organization_id=organization_id, provider_type=provider_type, name=name,
        base_url=base_url, api_key=api_key, enabled=enabled, created_by_user_id=actor_user_id,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider


async def get_provider(db: AsyncSession, *, organization_id: uuid.UUID, provider_id: uuid.UUID) -> ImportProvider | None:
    provider = await db.get(ImportProvider, provider_id)
    if provider is None or provider.organization_id != organization_id:
        return None
    return provider


async def update_provider(
    db: AsyncSession, *, provider: ImportProvider,
    name: str | None, base_url: str | None, api_key: str | None, enabled: bool | None,
    fields_set: set[str],
) -> ImportProvider:
    """fields_set (Pydantic's model_fields_set) is what makes a PATCH that
    omits api_key leave the stored one untouched -- an explicit api_key=None
    (clearing it) is only honored when the caller actually sent that key."""
    if "name" in fields_set and name is not None:
        provider.name = name
    if "base_url" in fields_set:
        provider.base_url = base_url
    if "api_key" in fields_set:
        provider.api_key = api_key
    if "enabled" in fields_set and enabled is not None:
        provider.enabled = enabled
    await db.commit()
    await db.refresh(provider)
    return provider


async def list_providers(db: AsyncSession, *, organization_id: uuid.UUID) -> list[ImportProvider]:
    stmt = select(ImportProvider).where(ImportProvider.organization_id == organization_id).order_by(ImportProvider.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


def to_provider_read_dict(provider: ImportProvider) -> dict:
    return {
        "id": provider.id,
        "provider_type": provider.provider_type,
        "name": provider.name,
        "base_url": provider.base_url,
        "api_key_configured": bool(provider.api_key),
        "api_key_last4": provider.api_key[-4:] if provider.api_key else None,
        "enabled": provider.enabled,
        "created_at": provider.created_at,
    }


# --- Products ------------------------------------------------------------

async def create_imported_product(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID, provider_id: uuid.UUID,
    external_id: str | None, external_url: str | None, name: str, description: str, image_url: str | None,
    price_cents: int, credit_discount_percentage: int, status: str,
) -> ImportedProduct:
    provider = await get_provider(db, organization_id=organization_id, provider_id=provider_id)
    if provider is None:
        raise ProviderNotFoundError("Provider not found")
    product = ImportedProduct(
        organization_id=organization_id, provider_id=provider_id, external_id=external_id,
        external_url=external_url, name=name, description=description, image_url=image_url,
        price_cents=price_cents, credit_discount_percentage=credit_discount_percentage,
        status=status, created_by_user_id=actor_user_id,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def get_imported_product(
    db: AsyncSession, *, organization_id: uuid.UUID, imported_product_id: uuid.UUID
) -> ImportedProduct | None:
    product = await db.get(ImportedProduct, imported_product_id)
    if product is None or product.organization_id != organization_id:
        return None
    return product


async def update_imported_product(db: AsyncSession, *, product: ImportedProduct, updates: dict) -> ImportedProduct:
    for key, value in updates.items():
        setattr(product, key, value)
    await db.commit()
    await db.refresh(product)
    return product


async def list_imported_products(
    db: AsyncSession, *, organization_id: uuid.UUID, active_only: bool = False
) -> list[ImportedProduct]:
    stmt = select(ImportedProduct).where(ImportedProduct.organization_id == organization_id)
    if active_only:
        stmt = stmt.where(ImportedProduct.status == "ACTIVE")
    stmt = stmt.order_by(ImportedProduct.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def to_admin_product_read_dict(db: AsyncSession, product: ImportedProduct) -> dict:
    provider = await db.get(ImportProvider, product.provider_id)
    return {
        "id": product.id,
        "provider_id": product.provider_id,
        "provider_name": provider.name if provider else "—",
        "external_id": product.external_id,
        "external_url": product.external_url,
        "name": product.name,
        "description": product.description,
        "image_url": product.image_url,
        "price_cents": product.price_cents,
        "credit_discount_percentage": product.credit_discount_percentage,
        "status": product.status,
        "created_at": product.created_at,
    }


# --- Orders ----------------------------------------------------------------

async def _get_sellable_product(
    db: AsyncSession, *, organization_id: uuid.UUID, imported_product_id: uuid.UUID
) -> ImportedProduct:
    product = await get_imported_product(db, organization_id=organization_id, imported_product_id=imported_product_id)
    if product is None or product.status != "ACTIVE":
        raise ProductNotEligibleError("Product not found")
    return product


async def get_available_payment_methods(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    return {
        "bank_transfer": await organizations_service.is_bank_transfer_configured(db, organization_id=organization_id),
        "card": await organizations_service.is_stripe_configured(db, organization_id=organization_id),
    }


async def get_quote(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, imported_product_id: uuid.UUID
) -> dict:
    product = await _get_sellable_product(db, organization_id=organization_id, imported_product_id=imported_product_id)
    wallet = await wallets_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=customer_user_id)
    methods = await get_available_payment_methods(db, organization_id=organization_id)
    return {
        "imported_product_id": product.id,
        "product_name": product.name,
        "amount_cents": product.price_cents,
        "credit_discount_percentage": product.credit_discount_percentage,
        "max_creditable_cents": max_creditable_cents(
            amount_cents=product.price_cents, credit_discount_percentage=product.credit_discount_percentage
        ),
        "customer_wallet_balance_cents": wallet.balance_cents if wallet else 0,
        "bank_transfer_available": methods["bank_transfer"],
        "card_available": methods["card"],
    }


async def _resolve_display_name(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Duplicated from orders/service.py's identical private helper on
    purpose -- see this domain's "zero import coupling to `orders`" design
    note in models.py."""
    agent = (
        await db.execute(
            select(AgentProfile.display_name).where(
                AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if agent:
        return agent

    customer = (
        await db.execute(
            select(Customer).where(Customer.organization_id == organization_id, Customer.user_id == user_id)
        )
    ).scalar_one_or_none()
    if customer is not None:
        profile = await db.get(CustomerProfile, customer.id)
        company = await db.get(Company, customer.id)
        name = display_name_for(customer.kind, profile, company)
        if name != "—":
            return name

    user = await db.get(User, user_id)
    return user.email if user else "—"


async def to_read_dict(db: AsyncSession, order: ImportedProductOrder) -> dict:
    product = await db.get(ImportedProduct, order.imported_product_id)
    customer_name = await _resolve_display_name(db, organization_id=order.organization_id, user_id=order.customer_user_id)
    return {
        "id": order.id,
        "customer_user_id": order.customer_user_id,
        "customer_display_name": customer_name,
        "imported_product_id": order.imported_product_id,
        "product_name": product.name if product else "—",
        "product_image_url": product.image_url if product else None,
        "created_by_user_id": order.created_by_user_id,
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
    }


async def hydrate(db: AsyncSession, orders: list[ImportedProductOrder]) -> list[dict]:
    return [await to_read_dict(db, o) for o in orders]


async def create_order(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    imported_product_id: uuid.UUID,
    credit_applied_cents: int,
    actor_user_id: uuid.UUID,
    payment_method: str = "BANK_TRANSFER",
    note: str | None = None,
    otp_code: str | None = None,
    require_otp_for_credit_spend: bool = True,
) -> ImportedProductOrder:
    product = await _get_sellable_product(db, organization_id=organization_id, imported_product_id=imported_product_id)
    amount_cents = product.price_cents
    cap = max_creditable_cents(amount_cents=amount_cents, credit_discount_percentage=product.credit_discount_percentage)
    if credit_applied_cents < 0 or credit_applied_cents > cap:
        raise InvalidCreditAmountError(
            f"credit_applied_cents must be between 0 and {cap} for this product ({product.credit_discount_percentage}% of {amount_cents})"
        )

    if credit_applied_cents > 0 and require_otp_for_credit_spend:
        from app.domains.auth import service as auth_service

        if not otp_code or not await auth_service.verify_otp(
            db, user_id=customer_user_id, purpose=auth_service.WALLET_CREDIT_SPEND_OTP_PURPOSE, code=otp_code
        ):
            raise InvalidOtpError("Codice di conferma mancante, non valido o scaduto.")

    residual_cents = amount_cents - credit_applied_cents

    if residual_cents > 0:
        if payment_method not in IMPORTED_ORDER_PAYMENT_METHODS:
            raise InvalidPaymentMethodError(f"payment_method must be one of {IMPORTED_ORDER_PAYMENT_METHODS}")
        available = await get_available_payment_methods(db, organization_id=organization_id)
        if payment_method == "BANK_TRANSFER" and not available["bank_transfer"]:
            raise PaymentMethodNotAvailableError("Il pagamento con bonifico non è configurato.")
        if payment_method == "CARD" and not available["card"]:
            raise PaymentMethodNotAvailableError("Il pagamento con carta non è configurato.")

    wallet = None
    if credit_applied_cents > 0:
        wallet = await wallets_service.get_or_create_wallet(db, organization_id=organization_id, user_id=customer_user_id)
        if wallet.balance_cents < credit_applied_cents:
            raise wallets_service.InsufficientBalanceError("Insufficient balance")

    order = ImportedProductOrder(
        organization_id=organization_id,
        customer_user_id=customer_user_id,
        imported_product_id=imported_product_id,
        created_by_user_id=actor_user_id,
        amount_cents=amount_cents,
        credit_applied_cents=credit_applied_cents,
        status="AWAITING_PAYMENT",
        payment_method=payment_method,
        note=note,
    )
    db.add(order)
    await db.flush()

    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="IMPORTED_ORDER_CREATED", entity_type="imported_product_order", entity_id=order.id,
        title=f"Nuovo ordine Acquisti LialEnergy: {product.name}", body=f"{amount_cents / 100:.2f} EUR -- {payment_method}",
        exclude_user_id=actor_user_id,
    )

    if credit_applied_cents > 0:
        assert wallet is not None
        if residual_cents == 0:
            order.status = "PAID"
            order.paid_by_user_id = actor_user_id
            order.paid_at = utcnow()
        debit_txn = await wallets_service.debit_wallet_for_imported_purchase(
            db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=credit_applied_cents,
            reference_imported_order_id=order.id, actor_user_id=actor_user_id,
            note=f"Acquisto {product.name}", idempotency_key=f"imported-order:{order.id}:credit",
        )
        order.credit_debit_transaction_id = debit_txn.id
        await db.commit()
        await db.refresh(order)
    else:
        await db.commit()
        await db.refresh(order)

    await _send_order_confirmation_email(db, organization_id=organization_id, order=order, product=product)
    return order


async def _send_order_confirmation_email(
    db: AsyncSession, *, organization_id: uuid.UUID, order: ImportedProductOrder, product: ImportedProduct
) -> None:
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return

    settings = get_settings()
    residual_cents = order.amount_cents - order.credit_applied_cents
    order_code = str(order.id)[:8].upper()
    order_code_line = f"<p>Numero ordine: <strong>#{order_code}</strong></p>"
    cta_label: str | None = None
    cta_url: str | None = None

    if order.status == "PAID":
        heading = "Ordine confermato"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{product.name}</strong> è confermato.</p>"
            f"<p>Totale: {order.amount_cents / 100:.2f} &euro;"
            + (f" (di cui {order.credit_applied_cents / 100:.2f} LialCash)" if order.credit_applied_cents else "")
            + "</p><p>Non è richiesto alcun pagamento aggiuntivo.</p>"
        )
    elif order.payment_method == "CARD":
        from app.domains.payments import service as payments_service

        heading = "Completa il pagamento del tuo ordine"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{product.name}</strong> è stato registrato.</p>"
            f"<p>Da pagare: <strong>{residual_cents / 100:.2f} &euro;</strong>"
            + (f" (dopo {order.credit_applied_cents / 100:.2f} LialCash già applicati)" if order.credit_applied_cents else "")
            + "</p><p>Completa il pagamento con carta cliccando il pulsante qui sotto.</p>"
        )
        try:
            cta_url = await payments_service.create_checkout_session_for_imported_order(
                db, organization_id=organization_id, order=order,
                success_url=f"{settings.public_app_base_url}/customer",
                cancel_url=f"{settings.public_app_base_url}/customer",
            )
            cta_label = "Paga con carta"
        except payments_service.StripeNotConfiguredError:
            logger.warning("Imported order %s confirmation email sent without a Stripe link (Stripe not configured)", order.id)
        except stripe.error.StripeError:
            logger.exception("Imported order %s confirmation email sent without a Stripe link (Stripe API error)", order.id)
    else:
        bank_settings = await organizations_service.get_settings(db, organization_id=organization_id)
        iban = bank_settings.get("bank_iban")
        heading = "Completa il pagamento del tuo ordine"
        body_html = (
            order_code_line
            + f"<p>Il tuo ordine per <strong>{product.name}</strong> è stato registrato.</p>"
            f"<p>Da pagare tramite bonifico: <strong>{residual_cents / 100:.2f} &euro;</strong>"
            + (f" (dopo {order.credit_applied_cents / 100:.2f} LialCash già applicati)" if order.credit_applied_cents else "")
            + "</p>"
        )
        if iban:
            body_html += (
                f"<p><strong>IBAN:</strong> {iban}<br>"
                f"<strong>Intestatario:</strong> {bank_settings.get('bank_account_holder') or 'Lial Energy'}<br>"
                f"<strong>Causale:</strong> Ordine {order_code}</p>"
            )
            if bank_settings.get("bank_transfer_instructions"):
                body_html += f"<p>{bank_settings['bank_transfer_instructions']}</p>"
        else:
            body_html += "<p>Contatta l'amministrazione per le coordinate bancarie.</p>"

    html = render_email(
        preheader=f"Riepilogo del tuo ordine -- {product.name}",
        heading=heading,
        body_html=body_html,
        cta_label=cta_label,
        cta_url=cta_url,
    )
    try:
        send_html_email(
            to=user.email,
            subject=f"Conferma ordine - {product.name} - Lial Energy",
            html_body=html,
            text_body=f"{heading}: {product.name}, totale {order.amount_cents / 100:.2f} EUR.",
        )
    except EmailNotConfiguredError:
        logger.warning("Imported order confirmation email for %s not sent (SMTP not configured), order=%s", user.email, order.id)


async def _send_order_paid_email(db: AsyncSession, *, order: ImportedProductOrder, product: ImportedProduct | None) -> None:
    user = await db.get(User, order.customer_user_id)
    if user is None:
        return

    method_label = "Carta (Stripe)" if order.payment_method == "CARD" else "Bonifico bancario"
    product_name = product.name if product else "un prodotto"
    paid_at_label = order.paid_at.strftime("%d/%m/%Y %H:%M") if order.paid_at else "-"
    amount_paid_cents = order.amount_cents - order.credit_applied_cents
    body_html = (
        "<p>Il pagamento del tuo ordine &egrave; stato confermato.</p>"
        f"<p><strong>Numero ordine:</strong> #{str(order.id)[:8].upper()}<br>"
        f"<strong>Prodotto:</strong> {product_name}<br>"
        f"<strong>Importo pagato:</strong> {amount_paid_cents / 100:.2f} &euro;<br>"
        f"<strong>Metodo di pagamento:</strong> {method_label}<br>"
        "<strong>Stato:</strong> Pagato<br>"
        f"<strong>Data:</strong> {paid_at_label}</p>"
    )
    html = render_email(
        preheader="Pagamento completato con successo",
        heading="Pagamento completato con successo",
        body_html=body_html,
        cta_label="Vai ai miei ordini",
        cta_url=f"{get_settings().public_app_base_url}/customer?tab=orders",
    )
    try:
        send_html_email(
            to=user.email,
            subject=f"Pagamento confermato - Ordine {str(order.id)[:8]} - Lial Energy",
            html_body=html,
            text_body=(
                f"Pagamento completato con successo. Ordine {order.id}, {product_name}, "
                f"{order.amount_cents / 100:.2f} EUR, {method_label}."
            ),
        )
    except EmailNotConfiguredError:
        logger.warning("Imported-order-paid email for %s not sent (SMTP not configured), order=%s", user.email, order.id)


async def get_org_scoped(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID
) -> ImportedProductOrder | None:
    order = await db.get(ImportedProductOrder, order_id)
    if order is None or order.organization_id != organization_id:
        return None
    return order


async def get_owned(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID, order_id: uuid.UUID
) -> ImportedProductOrder | None:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None or order.customer_user_id != customer_user_id:
        return None
    return order


async def list_orders(
    db: AsyncSession, *, organization_id: uuid.UUID, status_filter: str | None = None
) -> list[ImportedProductOrder]:
    stmt = select(ImportedProductOrder).where(ImportedProductOrder.organization_id == organization_id)
    if status_filter:
        stmt = stmt.where(ImportedProductOrder.status == status_filter)
    stmt = stmt.order_by(ImportedProductOrder.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def list_orders_for_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_user_id: uuid.UUID
) -> list[ImportedProductOrder]:
    stmt = (
        select(ImportedProductOrder)
        .where(ImportedProductOrder.organization_id == organization_id, ImportedProductOrder.customer_user_id == customer_user_id)
        .order_by(ImportedProductOrder.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def confirm_payment(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, actor_user_id: uuid.UUID
) -> ImportedProductOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise ImportedProductsError("Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot confirm payment for an order in status {order.status}")
    if order.payment_method == "CARD":
        raise InvalidOrderStateError(
            "Questo ordine si paga con carta: la conferma arriva automaticamente da Stripe, "
            "non è richiesta (né consentita) un'azione manuale."
        )

    order.status = "PAID"
    order.paid_by_user_id = actor_user_id
    order.paid_at = utcnow()

    product = await db.get(ImportedProduct, order.imported_product_id)
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="imported_product_order", entity_id=order.id,
        title=f"Il tuo ordine per {product.name if product else 'un prodotto'} è confermato",
        body=None,
    )
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAID", entity_type="imported_product_order", entity_id=order.id,
        title=f"Bonifico confermato: {product.name if product else 'ordine'}",
        body=f"{order.amount_cents / 100:.2f} EUR", exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(order)
    await _send_order_paid_email(db, order=order, product=product)
    return order


async def cancel_order(
    db: AsyncSession, *, organization_id: uuid.UUID, order_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID
) -> ImportedProductOrder:
    order = await get_org_scoped(db, organization_id=organization_id, order_id=order_id)
    if order is None:
        raise ImportedProductsError("Order not found")
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot cancel an order in status {order.status}")

    if order.credit_debit_transaction_id is not None:
        await wallets_service.reverse_transaction(
            db, organization_id=organization_id, transaction_id=order.credit_debit_transaction_id,
            actor_user_id=actor_user_id, reason=f"Ordine annullato: {reason}",
            idempotency_key=f"imported-order:{order.id}:cancel-refund",
        )

    order.status = "CANCELLED"
    order.cancelled_by_user_id = actor_user_id
    order.cancelled_at = utcnow()
    order.cancellation_reason = reason
    await db.commit()
    await db.refresh(order)
    return order


async def change_payment_method(
    db: AsyncSession, *, organization_id: uuid.UUID, order: ImportedProductOrder, new_payment_method: str
) -> ImportedProductOrder:
    if order.status != "AWAITING_PAYMENT":
        raise InvalidOrderStateError(f"Cannot change payment method for an order in status {order.status}")
    if new_payment_method not in IMPORTED_ORDER_PAYMENT_METHODS:
        raise InvalidPaymentMethodError(f"payment_method must be one of {IMPORTED_ORDER_PAYMENT_METHODS}")

    if new_payment_method != order.payment_method:
        available = await get_available_payment_methods(db, organization_id=organization_id)
        if new_payment_method == "BANK_TRANSFER" and not available["bank_transfer"]:
            raise PaymentMethodNotAvailableError("Il pagamento con bonifico non è configurato.")
        if new_payment_method == "CARD" and not available["card"]:
            raise PaymentMethodNotAvailableError("Il pagamento con carta non è configurato.")
        if order.payment_method == "CARD":
            order.stripe_checkout_session_id = None
        order.payment_method = new_payment_method
        await db.commit()
        await db.refresh(order)
    return order


async def upload_payment_proof(
    db: AsyncSession, *, organization_id: uuid.UUID, order: ImportedProductOrder,
    file_bytes: bytes, content_type: str, original_filename: str, actor_user_id: uuid.UUID,
) -> ImportedProductOrder:
    from app.core.storage import UploadValidationError
    from app.core.storage import upload_document as storage_upload_document

    if order.status != "AWAITING_PAYMENT":
        raise PaymentProofError(f"Cannot attach a payment proof to an order in status {order.status}")
    if order.payment_method != "BANK_TRANSFER":
        raise PaymentProofError("La prova di pagamento è prevista solo per gli ordini pagati con bonifico.")

    try:
        storage_key = storage_upload_document(
            file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"imported-order-payment-proofs/{order.customer_user_id}",
        )
    except UploadValidationError as exc:
        raise PaymentProofError(str(exc)) from exc

    order.payment_proof_storage_key = storage_key
    order.payment_proof_original_filename = original_filename
    order.payment_proof_uploaded_at = utcnow()

    product = await db.get(ImportedProduct, order.imported_product_id)
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAYMENT_PROOF_UPLOADED", entity_type="imported_product_order", entity_id=order.id,
        title=f"Prova di pagamento caricata: {product.name if product else 'ordine'}",
        body=None, exclude_user_id=actor_user_id,
    )
    await db.commit()
    await db.refresh(order)
    return order


PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS = 300


def presigned_payment_proof_url(order: ImportedProductOrder) -> str:
    from app.core.storage import generate_presigned_document_url as storage_presign_document

    assert order.payment_proof_storage_key is not None
    return storage_presign_document(
        storage_key=order.payment_proof_storage_key, expires_in_seconds=PAYMENT_PROOF_PRESIGNED_URL_TTL_SECONDS
    )


async def attach_stripe_checkout_session(db: AsyncSession, *, order: ImportedProductOrder, session_id: str) -> ImportedProductOrder:
    order.payment_method = "CARD"
    order.stripe_checkout_session_id = session_id
    await db.commit()
    await db.refresh(order)
    return order


async def mark_paid_via_stripe(
    db: AsyncSession, *, organization_id: uuid.UUID, stripe_checkout_session_id: str
) -> ImportedProductOrder:
    stmt = select(ImportedProductOrder).where(
        ImportedProductOrder.organization_id == organization_id,
        ImportedProductOrder.stripe_checkout_session_id == stripe_checkout_session_id,
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise ImportedProductsError("Order not found for this Stripe checkout session")
    if order.status != "AWAITING_PAYMENT":
        return order

    order.status = "PAID"
    order.paid_at = utcnow()

    product = await db.get(ImportedProduct, order.imported_product_id)
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=order.customer_user_id, type_="ORDER_PAID",
        entity_type="imported_product_order", entity_id=order.id,
        title=f"Il tuo ordine per {product.name if product else 'un prodotto'} è confermato",
        body="Pagamento con carta ricevuto.",
    )
    await notifications_service.notify_roles(
        db, organization_id=organization_id, roles=notifications_service.STAFF_NOTIFY_ROLES,
        type_="ORDER_PAID", entity_type="imported_product_order", entity_id=order.id,
        title=f"Pagamento Stripe confermato: {product.name if product else 'ordine'}",
        body=f"{order.amount_cents / 100:.2f} EUR",
    )
    await db.commit()
    await db.refresh(order)
    await _send_order_paid_email(db, order=order, product=product)
    return order
