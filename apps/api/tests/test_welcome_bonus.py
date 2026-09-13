"""Session 37: the one-off "omaggio di benvenuto" every account can claim
exactly once, ever. The whole "only once" guarantee rests on
wallet_transactions' UNIQUE idempotency_key rather than a separate claimed
flag, so these tests lean hard on double-claim attempts."""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.users.models import User
from app.domains.wallets import service as wallet_service
from app.domains.wallets.models import WalletTransaction


async def _make_user(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"bonus-{uuid.uuid4().hex[:8]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_a_fresh_account_has_the_bonus_available_and_claiming_credits_the_wallet(db, organization_id):
    user = await _make_user(db, organization_id)
    assert await wallet_service.has_claimed_welcome_bonus(db, user_id=user.id) is False

    txn, newly_claimed = await wallet_service.claim_welcome_bonus(
        db, organization_id=organization_id, user_id=user.id
    )

    assert newly_claimed is True
    assert txn.amount_cents == wallet_service.WELCOME_BONUS_CENTS == 2000
    assert txn.source == "WELCOME_BONUS"
    assert txn.type == "ADMIN_CREDIT"
    # Credited FROM nothing TO the claimer's own wallet.
    assert txn.from_wallet_id is None
    wallet = await wallet_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=user.id
    )
    assert wallet.balance_cents == 2000
    assert txn.to_wallet_id == wallet.id


@pytest.mark.asyncio
async def test_claiming_twice_never_credits_twice(db, organization_id):
    """The double-click / retry case -- must be a harmless no-op, not an
    error and definitely not a second 20 LialCash."""
    user = await _make_user(db, organization_id)
    first, first_new = await wallet_service.claim_welcome_bonus(
        db, organization_id=organization_id, user_id=user.id
    )
    second, second_new = await wallet_service.claim_welcome_bonus(
        db, organization_id=organization_id, user_id=user.id
    )

    assert first_new is True
    assert second_new is False
    assert second.id == first.id  # same row returned, no new one minted

    wallet = await wallet_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=user.id
    )
    assert wallet.balance_cents == 2000

    rows = (
        await db.execute(
            select(WalletTransaction).where(WalletTransaction.source == "WELCOME_BONUS")
        )
    ).scalars().all()
    assert len([r for r in rows if r.to_wallet_id == wallet.id]) == 1


@pytest.mark.asyncio
async def test_after_claiming_it_is_no_longer_available(db, organization_id):
    """What makes the button disappear "per sempre"."""
    user = await _make_user(db, organization_id)
    await wallet_service.claim_welcome_bonus(db, organization_id=organization_id, user_id=user.id)
    assert await wallet_service.has_claimed_welcome_bonus(db, user_id=user.id) is True


@pytest.mark.asyncio
async def test_one_users_claim_does_not_consume_anothers(db, organization_id):
    """The idempotency key is per-user, so claims must be independent."""
    a = await _make_user(db, organization_id)
    b = await _make_user(db, organization_id)

    await wallet_service.claim_welcome_bonus(db, organization_id=organization_id, user_id=a.id)

    assert await wallet_service.has_claimed_welcome_bonus(db, user_id=b.id) is False
    _txn, newly_claimed = await wallet_service.claim_welcome_bonus(
        db, organization_id=organization_id, user_id=b.id
    )
    assert newly_claimed is True

    wallet_a = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=a.id)
    wallet_b = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=b.id)
    assert wallet_a.balance_cents == 2000
    assert wallet_b.balance_cents == 2000


@pytest.mark.asyncio
async def test_the_bonus_shows_up_in_the_wallet_history(db, organization_id):
    """It's an ordinary ledger row, not a hidden side-pot -- so it appears in
    the user's own wallet history (and therefore in Contabilità) labelled by
    its source, like every other credit."""
    user = await _make_user(db, organization_id)
    await wallet_service.claim_welcome_bonus(db, organization_id=organization_id, user_id=user.id)
    wallet = await wallet_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=user.id
    )

    rows = await wallet_service.list_transactions_for_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "WELCOME_BONUS"
    assert rows[0]["amount_cents"] == 2000
    # Not tied to an order or a redemption -- it comes from nothing.
    assert rows[0]["reference_order_id"] is None
    assert rows[0]["reference_invoice_redemption_id"] is None
