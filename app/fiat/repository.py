# app/fiat/repository.py
"""
Fiat Ledger — Repository Layer.

Design rules (from ARCHITECTURE.md):
- Every method receives an asyncpg.Connection (never the pool).
- Transaction boundaries are owned by the Service layer.
- Raw SQL only — no ORM.
- Money is stored as BIGINT (minor units). No floats, ever.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import asyncpg

# ─── Dataclasses ──────────────────────────────────────────────────────────


@dataclass
class WalletRecord:
    id: UUID
    user_id: UUID
    currency: str
    balance_minor: int
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "WalletRecord":
        return cls(**dict(row))


@dataclass
class TransactionRecord:
    id: UUID
    idempotency_key: str
    type: str
    status: str
    amount_minor: int
    currency: str
    metadata: Optional[dict[str, Any]]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "TransactionRecord":
        d = dict(row)
        if isinstance(d.get("metadata"), str):
            d["metadata"] = json.loads(d["metadata"])
        return cls(**d)


@dataclass
class LedgerEntryRecord:
    id: UUID
    transaction_id: UUID
    wallet_id: UUID
    amount_minor: int
    direction: str
    balance_after: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "LedgerEntryRecord":
        return cls(**dict(row))


# ─── WalletRepository ─────────────────────────────────────────────────────


class WalletRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn

    async def create(self, user_id: UUID, currency: str) -> WalletRecord:
        row = await self.conn.fetchrow(
            """
            INSERT INTO wallets (user_id, currency)
            VALUES ($1, $2)
            RETURNING *
            """,
            user_id,
            currency,
        )
        assert row is not None, (
            "INSERT RETURNING returned None — this should never happen"
        )
        return WalletRecord.from_row(row)

    async def get_by_id(self, wallet_id: UUID) -> Optional[WalletRecord]:
        row = await self.conn.fetchrow("SELECT * FROM wallets WHERE id = $1", wallet_id)
        return WalletRecord.from_row(row) if row else None

    async def get_by_user(self, user_id: UUID) -> list[WalletRecord]:
        rows = await self.conn.fetch(
            "SELECT * FROM wallets WHERE user_id = $1 ORDER BY created_at", user_id
        )
        return [WalletRecord.from_row(r) for r in rows]

    async def get_and_lock(self, wallet_id: UUID) -> Optional[WalletRecord]:
        """Acquire a row-level lock (SELECT FOR UPDATE) for safe mutation."""
        row = await self.conn.fetchrow(
            "SELECT * FROM wallets WHERE id = $1 FOR UPDATE", wallet_id
        )
        return WalletRecord.from_row(row) if row else None

    async def get_and_lock_multiple(self, wallet_ids: list[UUID]) -> list[WalletRecord]:
        """
        Lock multiple wallets in ascending UUID order to prevent deadlocks.
        Both sides of a transfer must always acquire locks in the same order.
        """
        sorted_ids = sorted(wallet_ids)
        rows = await self.conn.fetch(
            "SELECT * FROM wallets WHERE id = ANY($1::uuid[]) ORDER BY id FOR UPDATE",
            sorted_ids,
        )
        return [WalletRecord.from_row(r) for r in rows]

    async def update_balance(self, wallet_id: UUID, new_balance: int) -> WalletRecord:
        row = await self.conn.fetchrow(
            """
            UPDATE wallets
            SET balance_minor = $1, updated_at = now()
            WHERE id = $2
            RETURNING *
            """,
            new_balance,
            wallet_id,
        )
        assert row is not None, "UPDATE RETURNING returned None — wallet_id not found"
        return WalletRecord.from_row(row)


# ─── TransactionRepository ────────────────────────────────────────────────


class TransactionRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn

    async def create(
        self,
        idempotency_key: str,
        tx_type: str,
        amount_minor: int,
        currency: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[TransactionRecord]:
        """
        INSERT ... ON CONFLICT DO NOTHING — returns None when the key already exists.
        The caller should check for None and re-fetch via get_by_idempotency_key.
        """
        metadata_json = json.dumps(metadata) if metadata else None
        row = await self.conn.fetchrow(
            """
            INSERT INTO transactions (idempotency_key, type, amount_minor, currency, metadata)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING *
            """,
            idempotency_key,
            tx_type,
            amount_minor,
            currency,
            metadata_json,
        )
        return TransactionRecord.from_row(row) if row else None

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[TransactionRecord]:
        row = await self.conn.fetchrow(
            "SELECT * FROM transactions WHERE idempotency_key = $1", idempotency_key
        )
        return TransactionRecord.from_row(row) if row else None

    async def list_for_wallet(
        self, wallet_id: UUID, limit: int = 50, offset: int = 0
    ) -> list[TransactionRecord]:
        rows = await self.conn.fetch(
            """
            SELECT DISTINCT t.*
            FROM transactions t
            JOIN ledger_entries le ON t.id = le.transaction_id
            WHERE le.wallet_id = $1
            ORDER BY t.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            wallet_id,
            limit,
            offset,
        )
        return [TransactionRecord.from_row(r) for r in rows]

    async def count_for_wallet(self, wallet_id: UUID) -> int:
        row = await self.conn.fetchrow(
            """
            SELECT COUNT(DISTINCT t.id)
            FROM transactions t
            JOIN ledger_entries le ON t.id = le.transaction_id
            WHERE le.wallet_id = $1
            """,
            wallet_id,
        )
        return row[0] if row else 0


# ─── LedgerEntryRepository ────────────────────────────────────────────────


class LedgerEntryRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn

    async def create(
        self,
        transaction_id: UUID,
        wallet_id: UUID,
        amount_minor: int,
        direction: str,
        balance_after: int,
    ) -> LedgerEntryRecord:
        row = await self.conn.fetchrow(
            """
            INSERT INTO ledger_entries (transaction_id, wallet_id, amount_minor, direction, balance_after)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            transaction_id,
            wallet_id,
            amount_minor,
            direction,
            balance_after,
        )
        assert row is not None, (
            "INSERT RETURNING returned None — this should never happen"
        )
        return LedgerEntryRecord.from_row(row)

    async def sum_for_wallet(self, wallet_id: UUID) -> int:
        """Used by the reconciliation job to verify balance integrity."""
        row = await self.conn.fetchrow(
            "SELECT COALESCE(SUM(amount_minor), 0) AS total FROM ledger_entries WHERE wallet_id = $1",
            wallet_id,
        )
        return int(row["total"]) if row else 0

    async def list_for_wallet(
        self, wallet_id: UUID, limit: int = 50, offset: int = 0
    ) -> list[LedgerEntryRecord]:
        rows = await self.conn.fetch(
            """
            SELECT * FROM ledger_entries
            WHERE wallet_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            wallet_id,
            limit,
            offset,
        )
        return [LedgerEntryRecord.from_row(r) for r in rows]
