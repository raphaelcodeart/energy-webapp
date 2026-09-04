import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rate_limit import rate_limit
from app.domains.wallets import service as wallet_service
from app.domains.wallets.schemas import (
    WalletAdminListItemRead,
    WalletRead,
    WalletTopUpRequest,
    WalletTransactionRead,
    WalletTransactionReverseRequest,
    WalletTransferRequest,
)

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.get("/me", response_model=WalletRead)
async def get_my_wallet(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletRead:
    """Any authenticated user (customer or promoter) can read their own
    wallet, no permission check beyond authentication -- same pattern as
    GET /network/agents/me. Lazily creates the wallet on first access."""
    wallet = await wallet_service.get_or_create_wallet(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    return WalletRead.model_validate(wallet)


@router.get("/me/transactions", response_model=list[WalletTransactionRead])
async def get_my_transactions(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WalletTransactionRead]:
    wallet = await wallet_service.get_or_create_wallet(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    rows = await wallet_service.list_transactions_for_wallet(
        db, organization_id=current_user.organization_id, wallet_id=wallet.id
    )
    return [WalletTransactionRead(**row) for row in rows]


@router.post(
    "/transfer",
    response_model=WalletTransactionRead,
    dependencies=[Depends(rate_limit("wallet-transfer", max_requests=20, window_seconds=60))],
)
async def transfer(
    payload: WalletTransferRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WalletTransactionRead:
    """Self-service send -- the caller's own wallet is always the source,
    resolved from their own user_id, never taken from the request body. No
    permission beyond authentication is required: a user can only ever move
    money out of their own wallet, which is the entire safety property here."""
    from_wallet = await wallet_service.get_or_create_wallet(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    try:
        txn = await wallet_service.debit_and_transfer(
            db,
            organization_id=current_user.organization_id,
            from_wallet_id=from_wallet.id,
            to_address=payload.to_address,
            amount_cents=payload.amount_cents,
            actor_user_id=current_user.user_id,
            note=payload.note,
            idempotency_key=payload.idempotency_key,
        )
    except wallet_service.WalletNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (wallet_service.SelfTransferError, wallet_service.InsufficientBalanceError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await wallet_service.hydrate_transactions(
        db, organization_id=current_user.organization_id, transactions=[txn]
    )
    return WalletTransactionRead(**rows[0])


@router.get("/admin", response_model=list[WalletAdminListItemRead])
async def list_all_wallets(
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[WalletAdminListItemRead]:
    rows = await wallet_service.list_all_wallets_for_org(db, organization_id=current_user.organization_id)
    return [WalletAdminListItemRead(**row) for row in rows]


@router.get("/admin/transactions", response_model=list[WalletTransactionRead])
async def list_all_transactions(
    type: str | None = None,
    user_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[WalletTransactionRead]:
    rows = await wallet_service.list_all_transactions_for_org(
        db, organization_id=current_user.organization_id, type_=type, user_id=user_id
    )
    return [WalletTransactionRead(**row) for row in rows]


@router.get("/admin/{user_id}", response_model=WalletRead)
async def get_wallet_for_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> WalletRead:
    """Deliberately does NOT lazily create a wallet here (unlike GET
    /wallets/me) -- an admin looking at a user who has never transacted
    should see "no wallet yet", not silently mint one just by looking."""
    wallet = await wallet_service.get_wallet_by_user_id(
        db, organization_id=current_user.organization_id, user_id=user_id
    )
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
    return WalletRead.model_validate(wallet)


@router.get("/admin/{user_id}/transactions", response_model=list[WalletTransactionRead])
async def get_transactions_for_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[WalletTransactionRead]:
    wallet = await wallet_service.get_wallet_by_user_id(
        db, organization_id=current_user.organization_id, user_id=user_id
    )
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
    rows = await wallet_service.list_transactions_for_wallet(
        db, organization_id=current_user.organization_id, wallet_id=wallet.id
    )
    return [WalletTransactionRead(**row) for row in rows]


@router.post("/admin/topup", response_model=WalletTransactionRead, status_code=status.HTTP_201_CREATED)
async def top_up(
    payload: WalletTopUpRequest,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> WalletTransactionRead:
    """Admin credits cashback or a plain recharge to a user's wallet --
    creates the wallet lazily if this is its first credit."""
    wallet = await wallet_service.get_or_create_wallet(
        db, organization_id=current_user.organization_id, user_id=payload.user_id
    )
    txn = await wallet_service.credit_wallet(
        db,
        organization_id=current_user.organization_id,
        wallet_id=wallet.id,
        amount_cents=payload.amount_cents,
        type_="ADMIN_CREDIT",
        actor_user_id=current_user.user_id,
        reference_contract_id=payload.reference_contract_id,
        note=payload.note,
        idempotency_key=payload.idempotency_key,
    )
    rows = await wallet_service.hydrate_transactions(
        db, organization_id=current_user.organization_id, transactions=[txn]
    )
    return WalletTransactionRead(**rows[0])


@router.post("/admin/transactions/{transaction_id}/reverse", response_model=WalletTransactionRead)
async def reverse_transaction(
    transaction_id: uuid.UUID,
    payload: WalletTransactionReverseRequest,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> WalletTransactionRead:
    try:
        txn = await wallet_service.reverse_transaction(
            db,
            organization_id=current_user.organization_id,
            transaction_id=transaction_id,
            actor_user_id=current_user.user_id,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        )
    except wallet_service.WalletNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (wallet_service.InsufficientBalanceError, wallet_service.WalletError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await wallet_service.hydrate_transactions(
        db, organization_id=current_user.organization_id, transactions=[txn]
    )
    return WalletTransactionRead(**rows[0])
