# app/fiat/router.py
"""
Fiat Ledger — Router Layer.

Pattern mirrors app/users/router/* exactly:
 / - Router receives conn via Depends(get_db).
  - Router instantiates Service with that conn.
  - Router never calls Repository directly.
  - All auth is via Depends(get_current_user) → returns UserRecord.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.fiat.repository import TransactionRepository
from app.fiat.schemas import (
    CreateWalletRequest,
    DepositRequest,
    TransactionListResponse,
    TransactionResponse,
    TransferRequest,
    WalletResponse,
    WithdrawRequest,
)
from app.fiat.service import (
    DepositService,
    TransferService,
    WalletService,
    WithdrawalService,
)
from app.users.repository import UserRecord

router = APIRouter()


# ─── Helpers ──────────────────────────────────────────────────────────────


def _wallet_to_response(w) -> WalletResponse:
    return WalletResponse(
        id=w.id,
        user_id=w.user_id,
        currency=w.currency,
        balance_minor=w.balance_minor,
        status=w.status,
        created_at=w.created_at,
        updated_at=w.updated_at,
    )


def _tx_to_response(t) -> TransactionResponse:
    return TransactionResponse(
        id=t.id,
        idempotency_key=t.idempotency_key,
        type=t.type,
        status=t.status,
        amount_minor=t.amount_minor,
        currency=t.currency,
        metadata=t.metadata,
        created_at=t.created_at,
    )


# ─── Wallet endpoints ─────────────────────────────────────────────────────


@router.post(
    "/wallets",
    response_model=WalletResponse,
    status_code=201,
    summary="Create a new fiat wallet",
)
async def create_wallet(
    body: CreateWalletRequest,
    current_user: UserRecord = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db),
) -> WalletResponse:
    svc = WalletService(conn)
    wallet = await svc.create_wallet(current_user.id, body.currency)
    return _wallet_to_response(wallet)


@router.get(
    "/wallets",
    response_model=list[WalletResponse],
    summary="List all wallets for the authenticated user",
)
async def list_wallets(
    current_user: UserRecord = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db),
) -> list[WalletResponse]:
    svc = WalletService(conn)
    wallets = await svc.list_wallets(current_user.id)
    return [_wallet_to_response(w) for w in wallets]


@router.get(
    "/wallets/{wallet_id}",
    response_model=WalletResponse,
    summary="Get a specific wallet by ID",
)
async def get_wallet(
    wallet_id: UUID,
    current_user: UserRecord = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db),
) -> WalletResponse:
    svc = WalletService(conn)
    wallet = await svc.get_wallet(wallet_id, current_user.id)
    return _wallet_to_response(wallet)


# ─── Deposit ──────────────────────────────────────────────────────────────


@router.post(
    "/wallets/{wallet_id}/deposit",
    response_model=TransactionResponse,
    status_code=201,
    summary="Deposit funds into a wallet",
)
async def deposit(
    wallet_id: UUID,
    body: DepositRequest,
    current_user: UserRecord = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db),
) -> TransactionResponse:
    svc = DepositService(conn)
    tx = await svc.deposit(
        wallet_id=wallet_id,
        user_id=current_user.id,
        amount_minor=body.amount_minor,
        idempotency_key=body.idempotency_key,
    )
    return _tx_to_response(tx)


# ─── Withdraw ─────────────────────────────────────────────────────────────


@router.post(
    "/wallets/{wallet_id}/withdraw",
    response_model=TransactionResponse,
    status_code=201,
    summary="Withdraw funds from a wallet",
)
async def withdraw(
    wallet_id: UUID,
    body: WithdrawRequest,
    current_user: UserRecord = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db),
) -> TransactionResponse:
    svc = WithdrawalService(conn)
    tx = await svc.withdraw(
        wallet_id=wallet_id,
        user_id=current_user.id,
        amount_minor=body.amount_minor,
        idempotency_key=body.idempotency_key,
    )
    return _tx_to_response(tx)


# ─── Transfer ─────────────────────────────────────────────────────────────


@router.post(
    "/transfers",
    response_model=TransactionResponse,
    status_code=201,
    summary="Transfer funds between two wallets",
)
async def transfer(
    body: TransferRequest,
    current_user: UserRecord = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db),
) -> TransactionResponse:
    svc = TransferService(conn)
    tx = await svc.transfer(
        from_wallet_id=body.from_wallet_id,
        to_wallet_id=body.to_wallet_id,
        user_id=current_user.id,
        amount_minor=body.amount_minor,
        idempotency_key=body.idempotency_key,
    )
    return _tx_to_response(tx)


# ─── Transaction history ──────────────────────────────────────────────────


@router.get(
    "/wallets/{wallet_id}/transactions",
    response_model=TransactionListResponse,
    summary="Paginated transaction history for a wallet",
)
async def list_transactions(
    wallet_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: UserRecord = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db),
) -> TransactionListResponse:
    # Ownership check
    svc = WalletService(conn)
    await svc.get_wallet(wallet_id, current_user.id)

    repo = TransactionRepository(conn)
    items = await repo.list_for_wallet(wallet_id, limit=limit, offset=offset)
    total = await repo.count_for_wallet(wallet_id)

    return TransactionListResponse(
        items=[_tx_to_response(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )
