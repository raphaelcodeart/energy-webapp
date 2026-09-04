import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Sanity ceiling against fat-finger/overflow input -- 10,000,000.00 EUR.
MAX_AMOUNT_CENTS = 10_000_000_00


class WalletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    address: str
    balance_cents: int
    currency: str
    created_at: datetime


class WalletAdminListItemRead(WalletRead):
    """Admin list view -- adds the owner's display info so the panel doesn't
    need a second round trip per row, same shape choice as
    CommissionMovementDetailRead."""

    owner_display_name: str
    owner_email: str
    owner_roles: list[str]


class WalletTransactionRead(BaseModel):
    """Resolved counterparty info, not raw wallet ids -- built from a service
    dict row (see wallets/service.py::_to_transaction_dict), not
    model_validate(orm_obj) directly."""

    id: uuid.UUID
    from_wallet_id: uuid.UUID | None
    from_address: str | None
    from_display_name: str | None
    # NULL only for a REVERSAL of an ADMIN_CREDIT -- the money exits back to
    # admin/system, symmetric to how an ADMIN_CREDIT's from_wallet_id is NULL.
    to_wallet_id: uuid.UUID | None
    to_address: str | None
    to_display_name: str | None
    amount_cents: int
    currency: str
    type: str
    reference_contract_id: uuid.UUID | None
    reverses_transaction_id: uuid.UUID | None
    note: str | None
    actor_user_id: uuid.UUID | None
    created_at: datetime


class WalletTopUpRequest(BaseModel):
    """Admin credits a user's wallet -- 'bonifica'/cashback. Identifies the
    target by user_id (resolved by the admin UI from the customer/promoter
    picker), not by wallet address, since an admin operating on a customer
    record may not know/care about the wallet's address yet --
    get_or_create_wallet() creates it lazily if this is the first credit."""

    user_id: uuid.UUID
    amount_cents: int = Field(gt=0, le=MAX_AMOUNT_CENTS)
    reference_contract_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)


class WalletTransferRequest(BaseModel):
    to_address: str = Field(min_length=1, max_length=42)
    amount_cents: int = Field(gt=0, le=MAX_AMOUNT_CENTS)
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)


class WalletTransactionReverseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)
