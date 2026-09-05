import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPKMixin

# What produced a WalletTransaction row. ADMIN_CREDIT = admin top-up/cashback
# (from_wallet_id is NULL -- money originates outside the wallet system, e.g.
# an admin crediting cashback after a product purchase). TRANSFER = peer-to-peer,
# both wallet ids set. REVERSAL = a correction that links back to the original
# row via reverses_transaction_id, mirroring CommissionReversal's "never mutate
# a settled row, insert a new linked row instead" pattern (see
# commissions/models.py CommissionReversal).
WALLET_TRANSACTION_TYPES = ["ADMIN_CREDIT", "TRANSFER", "REVERSAL"]


class Wallet(UUIDPKMixin, TimestampMixin, Base):
    """One per user (customer or promoter), lazily created on first access by
    wallets/service.py::get_or_create_wallet(). Not tied to Customer or
    AgentProfile specifically -- user_id is the only ownership key, since a
    person may hold both a customer and a promoter role against the same
    login (see network/service.py::apply_as_promoter). address is a global,
    Ethereum-style identifier (not org-scoped) so it reads like a real crypto
    address; organization_id still exists for tenant-scoped queries and the
    same-org transfer rule (see wallets/service.py::debit_and_transfer).
    balance_cents must never go negative -- enforced both at the application
    layer (atomic compare-and-swap UPDATE in debit_and_transfer()) and at the
    DB layer (CheckConstraint below) as defense in depth."""

    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_wallets_user_id"),
        UniqueConstraint("address", name="uq_wallets_address"),
        CheckConstraint("balance_cents >= 0", name="ck_wallets_balance_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    # f"0x{secrets.token_hex(20)}" -- 42 chars total, generated in
    # wallets/service.py::_generate_address(). Uniqueness is a DB constraint,
    # not guessed at generation time -- same division of responsibility as
    # network/service.py::_generate_promoter_code with uq_agent_promoter_code.
    address: Mapped[str] = mapped_column(String(42), index=True)
    balance_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    # Peer-to-peer sending (POST /wallets/transfer) is denied by default for
    # every wallet -- customer or promoter -- and enabled individually per
    # promoter by an admin (PATCH /wallets/admin/{user_id}/transfer-permission,
    # wallet.manage-gated). Deliberately per-wallet, not a role permission:
    # the business rule is "these specific two promoters today", not "all
    # promoters", so a role-based grant would be wrong the moment a second
    # promoter needs enabling without opening it for everyone. See
    # docs/business-rules.md#internal-wallet.
    can_transfer: Mapped[bool] = mapped_column(Boolean, default=False)


class WalletTransaction(UUIDPKMixin, TimestampMixin, Base):
    """Append-only ledger, ONE ROW per transaction (not double-entry with two
    rows) -- see docs/business-rules.md#internal-wallet. from_wallet_id NULL
    means the money originated from admin/system, not from another wallet
    (ADMIN_CREDIT); to_wallet_id NULL means the reverse -- money exited back
    to admin/system (only possible on a REVERSAL of an ADMIN_CREDIT, the
    symmetric case). A TRANSFER (and a REVERSAL of one) always has both set.
    At least one side must be set (ck_wallet_transactions_has_a_side below) --
    a row with neither would mean nothing happened. idempotency_key mirrors
    commission_movements.idempotency_key's UniqueConstraint exactly
    (client-generated UUID per submit, Stripe-style)."""

    __tablename__ = "wallet_transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_wallet_transactions_idempotency_key"),
        CheckConstraint(
            "from_wallet_id IS NOT NULL OR to_wallet_id IS NOT NULL",
            name="ck_wallet_transactions_has_a_side",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    from_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=True, index=True
    )
    to_wallet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=True, index=True
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    # ADMIN_CREDIT / TRANSFER / REVERSAL -- see WALLET_TRANSACTION_TYPES above.
    type: Mapped[str] = mapped_column(String(16), index=True)
    # Optional link to the contract that triggered an ADMIN_CREDIT (cashback
    # after a product purchase) -- NULL for a plain top-up with no purchase
    # behind it, and always NULL for TRANSFER/REVERSAL rows.
    reference_contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=True
    )
    # Self-FK: set only on a REVERSAL row, pointing back at the
    # ADMIN_CREDIT/TRANSFER row it corrects. The original row is never
    # mutated -- mirrors CommissionReversal.original_movement_id.
    reverses_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallet_transactions.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Who caused this row to be created -- the admin for ADMIN_CREDIT/REVERSAL,
    # the sending user themself for a self-service TRANSFER.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
