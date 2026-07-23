# app/fiat/service.py
"""
Fiat Ledger — Service Layer.

Each service method:
  1. Checks idempotency first (outside transaction — cheap read).
  2. Opens a transaction via `async with conn.transaction()`.
  3. Acquires row-level locks (SELECT FOR UPDATE) to prevent races.
  4. Enforces business invariants (balance check, currency match, etc.).
  5. Writes to transactions + ledger_entries + updates wallet balance atomically.
  6. Logs to audit_logs within the same transaction.

Design rules (ARCHITECTURE.md):
  - Single connection per transaction.
  - Deterministic lock ordering for transfers (lower UUID first).
  - Integer minor units only — no floats.
  - Append-only ledger — never update/delete entries.
"""

from __future__ import annotations

from typing import ClassVar
from uuid import UUID

import asyncpg

from app.core.audit import log_audit_event
from app.fiat.repository import (
    LedgerEntryRepository,
    TransactionRecord,
    TransactionRepository,
    WalletRecord,
    WalletRepository,
)
from app.users.exception import AppError

# ─── Fiat Domain Exceptions ───────────────────────────────────────────────


class FiatError(AppError):
    error_code: ClassVar[str] = "fiat_error"
    http_status: ClassVar[int] = 400


class WalletNotFoundError(FiatError):
    error_code: ClassVar[str] = "wallet_not_found"
    http_status: ClassVar[int] = 404

    def __init__(self) -> None:
        super().__init__("Wallet not found.")


class WalletAlreadyExistsError(FiatError):
    error_code: ClassVar[str] = "wallet_already_exists"
    http_status: ClassVar[int] = 409

    def __init__(self, currency: str) -> None:
        super().__init__(
            f"A wallet for '{currency}' already exists.",
            details={"currency": currency},
        )


class InsufficientFundsError(FiatError):
    error_code: ClassVar[str] = "insufficient_funds"
    http_status: ClassVar[int] = 422

    def __init__(self, available: int, requested: int) -> None:
        super().__init__(
            "Insufficient funds.",
            details={"available_minor": available, "requested_minor": requested},
        )


class CurrencyMismatchError(FiatError):
    error_code: ClassVar[str] = "currency_mismatch"
    http_status: ClassVar[int] = 422

    def __init__(self, from_currency: str, to_currency: str) -> None:
        super().__init__(
            "Cross-currency transfers are not supported.",
            details={"from_currency": from_currency, "to_currency": to_currency},
        )


class SameWalletTransferError(FiatError):
    error_code: ClassVar[str] = "same_wallet_transfer"
    http_status: ClassVar[int] = 422

    def __init__(self) -> None:
        super().__init__("Cannot transfer to the same wallet.")


# ─── WalletService ────────────────────────────────────────────────────────


class WalletService:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn
        self.repo = WalletRepository(conn)

    async def create_wallet(self, user_id: UUID, currency: str) -> WalletRecord:
        currency = currency.upper()
        existing = await self.conn.fetchval(
            "SELECT id FROM wallets WHERE user_id = $1 AND currency = $2",
            user_id,
            currency,
        )
        if existing:
            raise WalletAlreadyExistsError(currency)

        async with self.conn.transaction():
            wallet = await self.repo.create(user_id, currency)
            await log_audit_event(
                conn=self.conn,
                user_id=user_id,
                event_type="wallet_created",
                ip_address=None,
                user_agent=None,
                metadata={"wallet_id": str(wallet.id), "currency": currency},
            )
        return wallet

    async def list_wallets(self, user_id: UUID) -> list[WalletRecord]:
        return await self.repo.get_by_user(user_id)

    async def get_wallet(self, wallet_id: UUID, user_id: UUID) -> WalletRecord:
        wallet = await self.repo.get_by_id(wallet_id)
        if not wallet or wallet.user_id != user_id:
            raise WalletNotFoundError()
        return wallet


# ─── DepositService ───────────────────────────────────────────────────────


class DepositService:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn
        self.wallet_repo = WalletRepository(conn)
        self.tx_repo = TransactionRepository(conn)
        self.ledger_repo = LedgerEntryRepository(conn)

    async def deposit(
        self,
        wallet_id: UUID,
        user_id: UUID,
        amount_minor: int,
        idempotency_key: str,
    ) -> TransactionRecord:
        # Idempotency — cheap check before acquiring any lock
        existing = await self.tx_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        async with self.conn.transaction():
            wallet = await self.wallet_repo.get_and_lock(wallet_id)
            if not wallet or wallet.user_id != user_id:
                raise WalletNotFoundError()

            new_balance = wallet.balance_minor + amount_minor

            tx = await self.tx_repo.create(
                idempotency_key=idempotency_key,
                tx_type="deposit",
                amount_minor=amount_minor,
                currency=wallet.currency,
            )
            # ON CONFLICT returned None → someone else just inserted with same key
            if tx is None:
                tx = await self.tx_repo.get_by_idempotency_key(idempotency_key)
                return tx  # type: ignore[return-value]

            await self.wallet_repo.update_balance(wallet_id, new_balance)
            await self.ledger_repo.create(
                transaction_id=tx.id,
                wallet_id=wallet_id,
                amount_minor=amount_minor,
                direction="credit",
                balance_after=new_balance,
            )
            await log_audit_event(
                conn=self.conn,
                user_id=user_id,
                event_type="wallet_deposit",
                ip_address=None,
                user_agent=None,
                metadata={
                    "wallet_id": str(wallet_id),
                    "amount_minor": amount_minor,
                    "currency": wallet.currency,
                    "idempotency_key": idempotency_key,
                },
            )

        return tx


# ─── WithdrawalService ────────────────────────────────────────────────────


class WithdrawalService:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn
        self.wallet_repo = WalletRepository(conn)
        self.tx_repo = TransactionRepository(conn)
        self.ledger_repo = LedgerEntryRepository(conn)

    async def withdraw(
        self,
        wallet_id: UUID,
        user_id: UUID,
        amount_minor: int,
        idempotency_key: str,
    ) -> TransactionRecord:
        existing = await self.tx_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        async with self.conn.transaction():
            wallet = await self.wallet_repo.get_and_lock(wallet_id)
            if not wallet or wallet.user_id != user_id:
                raise WalletNotFoundError()

            if wallet.balance_minor < amount_minor:
                raise InsufficientFundsError(
                    available=wallet.balance_minor, requested=amount_minor
                )

            new_balance = wallet.balance_minor - amount_minor

            tx = await self.tx_repo.create(
                idempotency_key=idempotency_key,
                tx_type="withdrawal",
                amount_minor=amount_minor,
                currency=wallet.currency,
            )
            if tx is None:
                tx = await self.tx_repo.get_by_idempotency_key(idempotency_key)
                return tx  # type: ignore[return-value]

            await self.wallet_repo.update_balance(wallet_id, new_balance)
            await self.ledger_repo.create(
                transaction_id=tx.id,
                wallet_id=wallet_id,
                amount_minor=-amount_minor,  # debit → negative in the ledger
                direction="debit",
                balance_after=new_balance,
            )
            await log_audit_event(
                conn=self.conn,
                user_id=user_id,
                event_type="wallet_withdrawal",
                ip_address=None,
                user_agent=None,
                metadata={
                    "wallet_id": str(wallet_id),
                    "amount_minor": amount_minor,
                    "currency": wallet.currency,
                    "idempotency_key": idempotency_key,
                },
            )

        return tx


# ─── TransferService ──────────────────────────────────────────────────────


class TransferService:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn
        self.wallet_repo = WalletRepository(conn)
        self.tx_repo = TransactionRepository(conn)
        self.ledger_repo = LedgerEntryRepository(conn)

    async def transfer(
        self,
        from_wallet_id: UUID,
        to_wallet_id: UUID,
        user_id: UUID,
        amount_minor: int,
        idempotency_key: str,
    ) -> TransactionRecord:
        if from_wallet_id == to_wallet_id:
            raise SameWalletTransferError()

        existing = await self.tx_repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        async with self.conn.transaction():
            # CRITICAL: Lock both wallets in deterministic (ascending UUID) order
            # to prevent deadlocks when concurrent opposite-direction transfers run.
            wallets = await self.wallet_repo.get_and_lock_multiple(
                [from_wallet_id, to_wallet_id]
            )
            wallet_map = {w.id: w for w in wallets}

            if from_wallet_id not in wallet_map or to_wallet_id not in wallet_map:
                raise WalletNotFoundError()

            sender = wallet_map[from_wallet_id]
            receiver = wallet_map[to_wallet_id]

            # Only sender ownership is checked — receiver can belong to any user
            if sender.user_id != user_id:
                raise WalletNotFoundError()

            if sender.currency != receiver.currency:
                raise CurrencyMismatchError(sender.currency, receiver.currency)

            if sender.balance_minor < amount_minor:
                raise InsufficientFundsError(
                    available=sender.balance_minor, requested=amount_minor
                )

            sender_new_balance = sender.balance_minor - amount_minor
            receiver_new_balance = receiver.balance_minor + amount_minor

            tx = await self.tx_repo.create(
                idempotency_key=idempotency_key,
                tx_type="transfer",
                amount_minor=amount_minor,
                currency=sender.currency,
                metadata={
                    "from_wallet_id": str(from_wallet_id),
                    "to_wallet_id": str(to_wallet_id),
                },
            )
            if tx is None:
                tx = await self.tx_repo.get_by_idempotency_key(idempotency_key)
                return tx  # type: ignore[return-value]

            # Two ledger entries — double-entry bookkeeping
            await self.wallet_repo.update_balance(from_wallet_id, sender_new_balance)
            await self.ledger_repo.create(
                transaction_id=tx.id,
                wallet_id=from_wallet_id,
                amount_minor=-amount_minor,
                direction="debit",
                balance_after=sender_new_balance,
            )

            await self.wallet_repo.update_balance(to_wallet_id, receiver_new_balance)
            await self.ledger_repo.create(
                transaction_id=tx.id,
                wallet_id=to_wallet_id,
                amount_minor=amount_minor,
                direction="credit",
                balance_after=receiver_new_balance,
            )

            await log_audit_event(
                conn=self.conn,
                user_id=user_id,
                event_type="wallet_transfer",
                ip_address=None,
                user_agent=None,
                metadata={
                    "from_wallet_id": str(from_wallet_id),
                    "to_wallet_id": str(to_wallet_id),
                    "amount_minor": amount_minor,
                    "currency": sender.currency,
                    "idempotency_key": idempotency_key,
                },
            )

        return tx
