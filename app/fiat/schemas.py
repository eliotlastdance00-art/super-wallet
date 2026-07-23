# app/fiat/schemas.py
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ─── Wallet ────────────────────────────────────────────────────────────────


class CreateWalletRequest(BaseModel):
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code, e.g. 'USD'",
    )



class WalletResponse(BaseModel):
    id: UUID
    user_id: UUID
    currency: str
    balance_minor: int
    status: str
    created_at: datetime
    updated_at: datetime


# ─── Deposit / Withdraw ────────────────────────────────────────────────────


class DepositRequest(BaseModel):
    amount_minor: int = Field(gt=0, description="Amount in minor units (e.g. cents)")
    idempotency_key: str = Field(max_length=255)


class WithdrawRequest(BaseModel):
    amount_minor: int = Field(gt=0)
    idempotency_key: str = Field(max_length=255)


# ─── Transfer ─────────────────────────────────────────────────────────────


class TransferRequest(BaseModel):
    from_wallet_id: UUID
    to_wallet_id: UUID
    amount_minor: int = Field(gt=0)
    idempotency_key: str = Field(max_length=255)


# ─── Transaction ──────────────────────────────────────────────────────────


class TransactionResponse(BaseModel):
    id: UUID
    idempotency_key: str
    type: str
    status: str
    amount_minor: int
    currency: str
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime


# ─── Paginated list ───────────────────────────────────────────────────────


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    limit: int
    offset: int
