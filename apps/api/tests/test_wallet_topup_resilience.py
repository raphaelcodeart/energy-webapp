"""Una ricarica riuscita non deve MAI risultare fallita.

The bug this pins down, found while investigating "quando provo a ricaricare
il wallet appare 'Si è verificato un errore'":

`credit_wallet()` commits the money, then sends a courtesy email. That email
call used to be wrapped in `except EmailNotConfiguredError` only -- exactly
one of the many ways a real mail server fails. `send_html_email()` opens a
blocking smtplib connection with a 10-second timeout to an external host, so a
refused login, a timeout, a DNS blip or a TLS error all escaped instead and
became a 500 on an operation that had ALREADY succeeded and been audited.

The admin then saw "Si è verificato un errore imprevisto. Riprova più tardi."
on a top-up that had in fact gone through -- and clicking "Ricarica" again
credited the wallet a SECOND time, because the dashboard minted a fresh
idempotency key per click.

Both halves are covered here: the credit must survive any email failure, and
retrying with the same key must never double the balance.
"""

import smtplib
import uuid

import pytest

from app.core import email as email_module
from app.core.security import hash_password
from app.domains.users.models import User
from app.domains.wallets import service as wallets_service


def _break_smtp(monkeypatch, failure: Exception) -> None:
    """Breaks SMTP at the real boundary -- `smtplib.SMTP` itself -- rather than
    at whichever helper happens to call it today.

    This matters: patching a module-level `send_html_email` name only affects
    the module it was patched on, so a test written that way silently passes
    against the very code it is meant to catch (the buggy version imported
    `send_html_email` by value into its own module). Failing the socket is
    implementation-agnostic: any code path that genuinely tries to send mail
    hits it.

    smtp_host is empty in the test settings, which is its own early return, so
    it gets pointed at an address first -- otherwise every send would stop at
    EmailNotConfiguredError, the one exception the buggy version DID catch."""
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.invalid.test")

    def _explode(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(email_module.smtplib, "SMTP", _explode)


async def _make_user(db, organization_id) -> User:
    user = User(
        organization_id=organization_id, email=f"topup-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.parametrize(
    "failure",
    [
        smtplib.SMTPAuthenticationError(535, b"authentication failed"),
        smtplib.SMTPServerDisconnected("connection closed"),
        TimeoutError("timed out"),
        ConnectionRefusedError("connection refused"),
    ],
    ids=["auth-refused", "server-disconnected", "timeout", "connection-refused"],
)
@pytest.mark.asyncio
async def test_a_wallet_topup_survives_any_smtp_failure(db, organization_id, monkeypatch, failure):
    user = await _make_user(db, organization_id)
    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=user.id
    )

    _break_smtp(monkeypatch, failure)

    txn = await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=406_26,
        type_="ADMIN_CREDIT", actor_user_id=user.id, source="MANUAL_ADMIN",
        note="1a Tranche Corso", idempotency_key=f"topup-{uuid.uuid4()}",
    )

    assert txn.amount_cents == 406_26
    await db.refresh(wallet)
    assert wallet.balance_cents == 406_26


@pytest.mark.asyncio
async def test_retrying_the_same_topup_key_never_doubles_the_balance(db, organization_id, monkeypatch):
    """The dashboard now keeps one idempotency key per top-up being composed
    (rotated only after one succeeds) rather than minting a new one per click,
    so the admin pressing "Ricarica" again after any error is a no-op."""
    user = await _make_user(db, organization_id)
    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=user.id
    )

    _break_smtp(monkeypatch, smtplib.SMTPException("relay temporarily unavailable"))

    key = f"topup-{uuid.uuid4()}"
    first = await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=50_00,
        type_="ADMIN_CREDIT", actor_user_id=user.id, source="MANUAL_ADMIN",
        note="Ricarica", idempotency_key=key,
    )
    second = await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=50_00,
        type_="ADMIN_CREDIT", actor_user_id=user.id, source="MANUAL_ADMIN",
        note="Ricarica", idempotency_key=key,
    )

    assert second.id == first.id
    await db.refresh(wallet)
    assert wallet.balance_cents == 50_00


@pytest.mark.asyncio
async def test_the_welcome_bonus_also_survives_a_broken_mail_server(db, organization_id, monkeypatch):
    """Same code path, and the one an ordinary customer hits: claiming the
    omaggio must not report failure on a bonus that landed."""
    user = await _make_user(db, organization_id)

    _break_smtp(monkeypatch, smtplib.SMTPException("greylisted"))

    txn, newly_claimed = await wallets_service.claim_welcome_bonus(
        db, organization_id=organization_id, user_id=user.id
    )
    assert newly_claimed is True
    assert txn.amount_cents == wallets_service.WELCOME_BONUS_CENTS

    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=user.id
    )
    assert wallet.balance_cents == wallets_service.WELCOME_BONUS_CENTS
