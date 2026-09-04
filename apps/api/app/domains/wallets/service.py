import secrets
import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.audit import service as audit_service
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.customers.service import display_name_for
from app.domains.network.models import AgentProfile
from app.domains.notifications import service as notifications_service
from app.domains.rbac import service as rbac_service
from app.domains.users.models import User
from app.domains.wallets.models import Wallet, WalletTransaction


class WalletError(Exception):
    pass


class WalletNotFoundError(WalletError):
    pass


class InsufficientBalanceError(WalletError):
    pass


class SelfTransferError(WalletError):
    pass


def _generate_address() -> str:
    """Ethereum-style address. Uniqueness is enforced by uq_wallets_address,
    not guessed here -- same division of responsibility as
    network/service.py::_generate_promoter_code with uq_agent_promoter_code."""
    return f"0x{secrets.token_hex(20)}"


async def get_or_create_wallet(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> Wallet:
    """Every User (customer or promoter) gets exactly one wallet, created on
    first access rather than at signup -- avoids a wallet row for every
    never-transacting account. Race-safe: a lost INSERT race against
    uq_wallets_user_id falls back to re-reading the winner's row, same
    IntegrityError-then-reread pattern as commissions/services/run_calculation.py."""
    wallet = await get_wallet_by_user_id(db, organization_id=organization_id, user_id=user_id)
    if wallet is not None:
        return wallet

    wallet = Wallet(organization_id=organization_id, user_id=user_id, address=_generate_address())
    db.add(wallet)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        wallet = await get_wallet_by_user_id(db, organization_id=organization_id, user_id=user_id)
        if wallet is None:
            raise
        return wallet
    await db.commit()
    await db.refresh(wallet)
    return wallet


async def get_wallet_by_user_id(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> Wallet | None:
    stmt = select(Wallet).where(Wallet.organization_id == organization_id, Wallet.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_wallet_by_address(db: AsyncSession, *, organization_id: uuid.UUID, address: str) -> Wallet | None:
    # organization_id is always part of the filter -- a wallet address from
    # another org must be exactly as invisible as if it didn't exist, even
    # though addresses are globally unique (multi-tenancy rule).
    stmt = select(Wallet).where(Wallet.organization_id == organization_id, Wallet.address == address)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_by_idempotency_key(db: AsyncSession, *, idempotency_key: str) -> WalletTransaction | None:
    stmt = select(WalletTransaction).where(WalletTransaction.idempotency_key == idempotency_key)
    return (await db.execute(stmt)).scalar_one_or_none()


async def credit_wallet(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    wallet_id: uuid.UUID,
    amount_cents: int,
    type_: str,
    actor_user_id: uuid.UUID | None,
    reference_contract_id: uuid.UUID | None = None,
    note: str | None = None,
    idempotency_key: str,
) -> WalletTransaction:
    """Admin top-up/cashback (type_='ADMIN_CREDIT') or the credit leg of a
    peer transfer (type_='TRANSFER', called from debit_and_transfer after the
    debit succeeds). A plain additive UPDATE is safe with no CAS guard -- a
    credit can never make the balance negative, unlike the debit path.
    Idempotency: a retried request with the same idempotency_key short-circuits
    to the existing row instead of double-crediting."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    await db.execute(
        update(Wallet).where(Wallet.id == wallet_id).values(balance_cents=Wallet.balance_cents + amount_cents)
    )
    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=None,
        to_wallet_id=wallet_id,
        amount_cents=amount_cents,
        type=type_,
        reference_contract_id=reference_contract_id,
        note=note,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    await db.flush()

    wallet = await db.get(Wallet, wallet_id)
    assert wallet is not None  # just updated above by this same wallet_id
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.credited", entity_type="wallet_transaction", entity_id=str(txn.id),
        new_value={"to_wallet_id": str(wallet_id), "amount_cents": amount_cents, "type": type_},
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=wallet.user_id, type_="CASHBACK_RECEIVED",
        entity_type="wallet_transaction", entity_id=txn.id,
        title=f"Hai ricevuto {amount_cents / 100:.2f} EUR sul tuo wallet",
        body=note,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn


async def debit_and_transfer(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    from_wallet_id: uuid.UUID,
    to_address: str,
    amount_cents: int,
    actor_user_id: uuid.UUID,
    note: str | None = None,
    idempotency_key: str,
) -> WalletTransaction:
    """Peer-to-peer transfer, looked up by address, scoped to the same
    organization_id (multi-tenant rule). The debit uses an atomic
    compare-and-swap UPDATE (WHERE balance_cents >= :amount) and checks the
    affected row count -- not SELECT...FOR UPDATE, matching this codebase's
    sole existing concurrency pattern of DB constraint + IntegrityError catch
    rather than pessimistic locking (see commission_movements.idempotency_key)."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    to_wallet = await get_wallet_by_address(db, organization_id=organization_id, address=to_address)
    if to_wallet is None:
        raise WalletNotFoundError("Wallet not found")
    if to_wallet.id == from_wallet_id:
        raise SelfTransferError("Cannot send to your own wallet")

    result = await db.execute(
        update(Wallet)
        .where(Wallet.id == from_wallet_id, Wallet.balance_cents >= amount_cents)
        .values(balance_cents=Wallet.balance_cents - amount_cents)
    )
    if result.rowcount == 0:
        # No rollback needed -- the UPDATE matched zero rows and changed
        # nothing at the DB level (this is a business-logic check, not a DB
        # error), so there is nothing pending to undo. An explicit rollback()
        # here would also conflict with the SAVEPOINT-based session wrapping
        # used by the test suite's `db` fixture.
        raise InsufficientBalanceError("Insufficient balance")

    await db.execute(
        update(Wallet).where(Wallet.id == to_wallet.id).values(balance_cents=Wallet.balance_cents + amount_cents)
    )

    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=from_wallet_id,
        to_wallet_id=to_wallet.id,
        amount_cents=amount_cents,
        type="TRANSFER",
        note=note,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    await db.flush()

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.transferred", entity_type="wallet_transaction", entity_id=str(txn.id),
        new_value={
            "from_wallet_id": str(from_wallet_id), "to_wallet_id": str(to_wallet.id), "amount_cents": amount_cents,
        },
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=to_wallet.user_id, type_="WALLET_TRANSFER_RECEIVED",
        entity_type="wallet_transaction", entity_id=txn.id,
        title=f"Hai ricevuto {amount_cents / 100:.2f} EUR sul tuo wallet",
        body=note,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn


async def reverse_transaction(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    transaction_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    reason: str,
    idempotency_key: str,
) -> WalletTransaction:
    """Admin-only correction -- inserts a new REVERSAL row, never mutates the
    original (same discipline as CommissionReversal). Only ADMIN_CREDIT and
    TRANSFER rows may be reversed, not a REVERSAL itself (no correcting a
    correction). Reversing a TRANSFER re-debits the original recipient, which
    can itself raise InsufficientBalanceError if they've since spent the
    funds -- an accepted, documented outcome, not a bug: docs/business-rules.md
    #internal-wallet."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    original = await db.get(WalletTransaction, transaction_id)
    if original is None or original.organization_id != organization_id:
        raise WalletNotFoundError("Transaction not found")
    if original.type == "REVERSAL":
        raise WalletError("Cannot reverse a REVERSAL")

    # Claw back from whoever received the original amount, credit back
    # whoever it came from (or nobody, for an ADMIN_CREDIT -- the money just
    # ceases to exist again, mirroring how it was created from nothing).
    result = await db.execute(
        update(Wallet)
        .where(Wallet.id == original.to_wallet_id, Wallet.balance_cents >= original.amount_cents)
        .values(balance_cents=Wallet.balance_cents - original.amount_cents)
    )
    if result.rowcount == 0:
        # See the identical comment in debit_and_transfer() -- no rollback
        # needed, nothing was persisted.
        raise InsufficientBalanceError("Insufficient balance to reverse this transaction")

    if original.from_wallet_id is not None:
        await db.execute(
            update(Wallet)
            .where(Wallet.id == original.from_wallet_id)
            .values(balance_cents=Wallet.balance_cents + original.amount_cents)
        )

    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=original.to_wallet_id,
        # Mirrors the original: a TRANSFER reversal sends the money back to
        # its real source (original.from_wallet_id); an ADMIN_CREDIT reversal
        # has no source to return to, so to_wallet_id is NULL -- the money
        # exits the system the same way it entered it.
        to_wallet_id=original.from_wallet_id,
        amount_cents=original.amount_cents,
        type="REVERSAL",
        reverses_transaction_id=original.id,
        note=reason,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    await db.flush()

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.reversed", entity_type="wallet_transaction", entity_id=str(txn.id),
        previous_value={"reverses_transaction_id": str(original.id)},
        new_value={"amount_cents": original.amount_cents, "reason": reason},
        reason=reason,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn


async def _resolve_display_names(
    db: AsyncSession, *, organization_id: uuid.UUID, user_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Best-effort display name per user_id, regardless of whether they're a
    customer, a promoter, or both -- no existing utility does this (wallets
    are the first thing keyed directly on user_id rather than customer_id/
    agent_id). Checks AgentProfile.display_name (already a stored column)
    first, then Customer joined to CustomerProfile/Company via the existing
    customers.service.display_name_for() helper, falling back to User.email."""
    if not user_ids:
        return {}

    names: dict[uuid.UUID, str] = {}

    agents = (
        await db.execute(
            select(AgentProfile.user_id, AgentProfile.display_name).where(
                AgentProfile.organization_id == organization_id, AgentProfile.user_id.in_(user_ids)
            )
        )
    ).all()
    for user_id, display_name in agents:
        names[user_id] = display_name

    remaining = user_ids - names.keys()
    if remaining:
        customers = (
            await db.execute(
                select(Customer).where(Customer.organization_id == organization_id, Customer.user_id.in_(remaining))
            )
        ).scalars().all()
        if customers:
            customer_ids = [c.id for c in customers]
            profiles = {
                p.customer_id: p
                for p in (
                    await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(customer_ids)))
                ).scalars()
            }
            companies = {
                c.customer_id: c
                for c in (
                    await db.execute(select(Company).where(Company.customer_id.in_(customer_ids)))
                ).scalars()
            }
            for customer in customers:
                if customer.user_id is None:  # can't happen -- filtered by user_id.in_(remaining) above
                    continue
                names[customer.user_id] = display_name_for(
                    customer.kind, profiles.get(customer.id), companies.get(customer.id)
                )

    remaining = user_ids - names.keys()
    if remaining:
        users = (await db.execute(select(User.id, User.email).where(User.id.in_(remaining)))).all()
        for user_id, email in users:
            names[user_id] = email

    return names


def _to_transaction_dict(txn: WalletTransaction, wallets_by_id: dict[uuid.UUID, Wallet], names: dict[uuid.UUID, str]) -> dict:
    from_wallet = wallets_by_id.get(txn.from_wallet_id) if txn.from_wallet_id else None
    to_wallet = wallets_by_id.get(txn.to_wallet_id) if txn.to_wallet_id else None
    return {
        "id": txn.id,
        "from_wallet_id": txn.from_wallet_id,
        "from_address": from_wallet.address if from_wallet else None,
        "from_display_name": names.get(from_wallet.user_id) if from_wallet else None,
        "to_wallet_id": txn.to_wallet_id,
        "to_address": to_wallet.address if to_wallet else None,
        "to_display_name": names.get(to_wallet.user_id) if to_wallet else None,
        "amount_cents": txn.amount_cents,
        "currency": txn.currency,
        "type": txn.type,
        "reference_contract_id": txn.reference_contract_id,
        "reverses_transaction_id": txn.reverses_transaction_id,
        "note": txn.note,
        "actor_user_id": txn.actor_user_id,
        "created_at": txn.created_at,
    }


async def hydrate_transactions(db: AsyncSession, *, organization_id: uuid.UUID, transactions: list[WalletTransaction]) -> list[dict]:
    if not transactions:
        return []

    wallet_ids: set[uuid.UUID] = set()
    for txn in transactions:
        if txn.from_wallet_id:
            wallet_ids.add(txn.from_wallet_id)
        if txn.to_wallet_id:
            wallet_ids.add(txn.to_wallet_id)

    wallets = (await db.execute(select(Wallet).where(Wallet.id.in_(wallet_ids)))).scalars().all()
    wallets_by_id = {w.id: w for w in wallets}
    names = await _resolve_display_names(
        db, organization_id=organization_id, user_ids={w.user_id for w in wallets}
    )
    return [_to_transaction_dict(txn, wallets_by_id, names) for txn in transactions]


async def list_transactions_for_wallet(
    db: AsyncSession, *, organization_id: uuid.UUID, wallet_id: uuid.UUID, limit: int = 100
) -> list[dict]:
    stmt = (
        select(WalletTransaction)
        .where(
            WalletTransaction.organization_id == organization_id,
            (WalletTransaction.from_wallet_id == wallet_id) | (WalletTransaction.to_wallet_id == wallet_id),
        )
        .order_by(WalletTransaction.created_at.desc())
        .limit(limit)
    )
    transactions = (await db.execute(stmt)).scalars().all()
    return await hydrate_transactions(db, organization_id=organization_id, transactions=list(transactions))


async def list_all_transactions_for_org(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    type_: str | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = 500,
) -> list[dict]:
    stmt = select(WalletTransaction).where(WalletTransaction.organization_id == organization_id)
    if type_ is not None:
        stmt = stmt.where(WalletTransaction.type == type_)
    if user_id is not None:
        wallet = await get_wallet_by_user_id(db, organization_id=organization_id, user_id=user_id)
        wallet_id = wallet.id if wallet is not None else uuid.uuid4()  # no match, never equal to a real row
        stmt = stmt.where(
            (WalletTransaction.from_wallet_id == wallet_id) | (WalletTransaction.to_wallet_id == wallet_id)
        )
    stmt = stmt.order_by(WalletTransaction.created_at.desc()).limit(limit)
    transactions = (await db.execute(stmt)).scalars().all()
    return await hydrate_transactions(db, organization_id=organization_id, transactions=list(transactions))


async def list_all_wallets_for_org(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    wallets = (
        await db.execute(
            select(Wallet).where(Wallet.organization_id == organization_id).order_by(Wallet.created_at.desc())
        )
    ).scalars().all()
    if not wallets:
        return []

    names = await _resolve_display_names(db, organization_id=organization_id, user_ids={w.user_id for w in wallets})
    users = (
        await db.execute(select(User.id, User.email).where(User.id.in_([w.user_id for w in wallets])))
    ).all()
    emails: dict[uuid.UUID, str] = dict(users)  # type: ignore[arg-type]

    result = []
    for wallet in wallets:
        roles = await rbac_service.get_roles_for_user(db, user_id=wallet.user_id, organization_id=organization_id)
        result.append(
            {
                "id": wallet.id,
                "user_id": wallet.user_id,
                "address": wallet.address,
                "balance_cents": wallet.balance_cents,
                "currency": wallet.currency,
                "created_at": wallet.created_at,
                "owner_display_name": names.get(wallet.user_id, "—"),
                "owner_email": emails.get(wallet.user_id, "—"),
                "owner_roles": roles,
            }
        )
    return result
