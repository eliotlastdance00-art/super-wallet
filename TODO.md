# 📋 SuperWallet — TODO

> Organized by priority. Check items off as completed.

---

## 🔴 Critical (Fix Before Stage 1)

### Identity & Auth
- [ ] **Move `AppError` to `app/core/exceptions.py`** — the shared base class currently lives in `app/users/exception.py`. Other domains (fiat, cards) will need to raise domain exceptions that extend `AppError`. The empty `core/exceptions.py` is confusing.
- [ ] **Register global exception handler in `main.py`** — `app_error_handler` exists in `users/exception.py` but there's no `app.add_exception_handler(AppError, app_error_handler)` call in `main.py`. Unhandled `AppError` subclasses will return 500 instead of structured JSON.
- [ ] **Wire `get_current_user` consistently** — `core/dependencies.py` returns `UserRecord` in some routes but `UUID` in others (session_auth.py does `user_id: UUID = Depends(get_current_user)`). Standardize return type.
- [ ] **Add password strength validation** — `PasswordTooWeakError` exception exists but no actual denylist or validation logic is implemented in the service layer.

### Infrastructure
- [ ] **Consolidate dependency management** — `pyproject.toml` and `requirements.txt` both list dependencies. Pick `pyproject.toml` as source of truth. Generate `requirements.txt` from it or drop it.
- [ ] **Remove unused Celery dependency** — `celery`, `kombu`, `billiard`, `amqp`, `vine` are in `pyproject.toml` but the notification worker is a plain `asyncio` loop. Remove them.
- [ ] **Remove unused SQLAlchemy dependency** — `SQLAlchemy` is in `pyproject.toml` but all queries use raw asyncpg. Only Alembic needs it (and imports it internally).
- [ ] **Remove `passlib` dependency** — listed in `pyproject.toml` but password hashing uses `argon2-cffi` directly.

---

## 🟡 Important (Stage 0 Completion)

### Profile Endpoints
- [ ] **Complete `GET /users/me`** — service and schema exist, verify full integration
- [ ] **Complete `PATCH /users/me`** — partial update semantics (exclude_unset), handle uniqueness violations on email/username change
- [ ] **Complete `PATCH /users/me/password`** — verify current password, enforce no-reuse, revoke all sessions
- [ ] **Complete `DELETE /users/me`** — soft delete (set `is_active=false, deleted_at=now()`), revoke all sessions, require password re-confirmation

### 2FA Endpoints
- [ ] **Add `POST /auth/2fa/enable`** — generate TOTP secret, return provisioning URI + backup codes
- [ ] **Add `POST /auth/2fa/disable`** — require TOTP code or backup code to disable
- [ ] **Implement backup code consumption** — `verify_backup_code()` exists in security.py but no service method consumes it

### Security Hardening
- [ ] **Add rate limiting** — Redis is provisioned but unused. Add rate limits on `/login`, `/forgot-password`, `/resend-verification`
- [ ] **Validate email change flow** — changing email should require re-verification (send verification to new email, don't update until confirmed)
- [ ] **Add CORS middleware** — no CORS configuration in `main.py`
- [ ] **Remove hardcoded secrets from `.env`** — `TOKEN_SIGNING_KEY` and `ENCRYPTION_KEY` are committed to git. Add `.env` to `.gitignore` and provide `.env.example` instead

---

## 🟢 Stage 1 — Fiat Ledger

### Schema & Migrations
- [ ] Create `wallets` table migration (user_id FK, currency, balance_minor, status)
- [ ] Create `transactions` table migration (idempotency_key UNIQUE, type, status, metadata)
- [ ] Create `ledger_entries` table migration (transaction_id FK, wallet_id FK, amount_minor, direction)
- [ ] Add `CHECK` constraint: `balance_minor >= 0` (no negative balances)

### Repository Layer
- [ ] `WalletRepository` — CRUD, `get_and_lock(wallet_id)` with `SELECT ... FOR UPDATE`
- [ ] `TransactionRepository` — create with idempotency key check, status transitions
- [ ] `LedgerEntryRepository` — append-only inserts, balance reconciliation query

### Service Layer
- [ ] `WalletService` — create wallet, get balance, list user wallets
- [ ] `DepositService` — atomic: create transaction + ledger entry + update balance
- [ ] `WithdrawalService` — atomic: balance check → lock → debit entry → update balance
- [ ] `TransferService` — atomic: deterministic lock ordering (lower ID first) → debit + credit entries → update both balances
- [ ] **Idempotency enforcement** — `idempotency_key` UNIQUE constraint + service-level check before processing

### Router Layer
- [ ] `POST /api/v1/wallets` — create wallet for authenticated user
- [ ] `GET /api/v1/wallets` — list user's wallets
- [ ] `GET /api/v1/wallets/{id}` — get wallet details + balance
- [ ] `POST /api/v1/wallets/{id}/deposit` — deposit funds
- [ ] `POST /api/v1/wallets/{id}/withdraw` — withdraw funds
- [ ] `POST /api/v1/transfers` — transfer between wallets
- [ ] `GET /api/v1/wallets/{id}/transactions` — transaction history with pagination

### Invariants to Enforce
- [ ] Double-entry: every debit has a matching credit (sum of all entries = 0 for transfers)
- [ ] Balance = SUM(ledger_entries) for wallet — reconciliation job
- [ ] No partial transactions — `BEGIN...COMMIT` wraps all mutations
- [ ] Idempotency key uniqueness at DB level

---

## 🔵 Stage 2 — Card Vault

- [ ] Stripe SDK integration
- [ ] PCI-DSS scope-free tokenization (Stripe handles card data)
- [ ] `POST /api/v1/cards` — save card (tokenize via Stripe)
- [ ] `POST /api/v1/wallets/{id}/deposit/card` — card-funded deposit
- [ ] Card listing and deletion endpoints

---

## 🟣 Stage 3 — Crypto Wallets

- [ ] BIP32/39/44 HD wallet derivation
- [ ] Address generation per user
- [ ] On-chain balance synchronization
- [ ] Deposit address generation
- [ ] Withdrawal to external addresses

---

## 🛠️ Tech Debt & DevOps

### Testing
- [ ] Set up `conftest.py` with test database, fixtures, and cleanup
- [ ] Unit tests for all services (auth, session_auth, profile)
- [ ] Integration tests for API endpoints (TestClient)
- [ ] Fiat ledger invariant tests (double-entry, idempotency, concurrent transfers)

### CI/CD
- [ ] Add GitHub Actions workflow (lint, type-check, test on push/PR)
- [ ] Add `mypy` or `pyright` for type checking
- [ ] Add `ruff` or `flake8` for linting
- [ ] Add `pre-commit` hooks

### Observability
- [ ] Structured logging with `structlog` or `python-json-logger`
- [ ] Request ID middleware (correlation ID propagation)
- [ ] Health check endpoint that verifies DB and Redis connectivity
- [ ] Metrics endpoint (Prometheus) or APM integration

### Documentation
- [ ] OpenAPI schema customization (descriptions, examples, tags)
- [ ] Postman/Insomnia collection export
- [ ] API versioning strategy documentation
