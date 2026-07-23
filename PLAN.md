# 🗺️ SuperWallet — Implementation Plan

> Each phase is designed to be completed, tested, and hardened before moving to the next.

---

## Phase 0A: Stage 0 Cleanup (Current Sprint)

**Goal:** Tie off all loose ends in Identity & Auth before starting the ledger.

### 0A-1. Exception Architecture
- [ ] Move `AppError` base class from `users/exception.py` to `core/exceptions.py`
- [ ] Keep domain-specific exceptions (AuthError, ProfileError) in `users/exception.py`, importing AppError from core
- [ ] Register `app.add_exception_handler(AppError, app_error_handler)` in `main.py`
- [ ] Verify all routes return structured JSON errors, never raw 500s

### 0A-2. Dependency Cleanup
- [ ] Remove from `pyproject.toml`: `celery`, `kombu`, `billiard`, `amqp`, `vine`, `passlib`, `SQLAlchemy` (keep only as Alembic transitive dep)
- [ ] Delete `requirements.txt` — use `pyproject.toml` as single source
- [ ] Update `Dockerfile` to install from `pyproject.toml` (`pip install .`)

### 0A-3. Security Hardening
- [ ] Add `.env` to `.gitignore`, create `.env.example` with placeholder values
- [ ] Add CORS middleware in `main.py` with configurable origins
- [ ] Implement rate limiting on auth endpoints using Redis (token bucket or sliding window)
- [ ] Add password denylist check (top 10,000 common passwords)

### 0A-4. 2FA Endpoints
- [ ] `POST /auth/2fa/enable` — generate secret, return provisioning URI + backup codes
- [ ] `POST /auth/2fa/verify-setup` — confirm the user can generate a valid code before enabling
- [ ] `POST /auth/2fa/disable` — require valid TOTP code
- [ ] `POST /auth/2fa/backup-verify` — consume one backup code (for login when phone is lost)

### 0A-5. Testing Foundation
- [ ] Set up `conftest.py` with test database (separate `superwallet_test` DB)
- [ ] Create fixtures: test user, authenticated client, test database cleanup
- [ ] Write tests for: register, login, login with lockout, refresh rotation, reuse detection
- [ ] Write tests for: email verification, password reset, profile CRUD

**Acceptance criteria:** All auth endpoints return structured errors. No unused dependencies. Rate limiting active on `/login`. Test suite passes with >80% service coverage.

---

## Phase 1A: Fiat Ledger — Schema & Foundation

**Goal:** Build the database schema and repository layer for the wallet system.

### 1A-1. Database Schema

```sql
-- Migration: create_wallets_table
CREATE TABLE wallets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    balance_minor BIGINT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wallets_user_currency UNIQUE (user_id, currency),
    CONSTRAINT chk_balance_non_negative CHECK (balance_minor >= 0)
);

-- Migration: create_transactions_table
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key VARCHAR(255) NOT NULL UNIQUE,
    type VARCHAR(20) NOT NULL,          -- 'deposit' | 'withdrawal' | 'transfer'
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    amount_minor BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Migration: create_ledger_entries_table
CREATE TABLE ledger_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID NOT NULL REFERENCES transactions(id),
    wallet_id UUID NOT NULL REFERENCES wallets(id),
    amount_minor BIGINT NOT NULL,       -- positive for credit, negative for debit
    direction VARCHAR(6) NOT NULL,      -- 'credit' | 'debit'
    balance_after BIGINT NOT NULL,      -- snapshot for audit trail
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_ledger_wallet_id ON ledger_entries(wallet_id);
CREATE INDEX ix_ledger_transaction_id ON ledger_entries(transaction_id);
```

### 1A-2. Repository Layer
- [ ] `WalletRepository` — `create()`, `get_by_id()`, `get_by_user()`, `get_and_lock(wallet_id)` (SELECT FOR UPDATE)
- [ ] `TransactionRepository` — `create()`, `get_by_idempotency_key()`, `list_for_wallet()`
- [ ] `LedgerEntryRepository` — `create()`, `list_for_wallet()`, `sum_for_wallet()` (reconciliation)

### 1A-3. Dataclasses
- [ ] `WalletRecord`, `TransactionRecord`, `LedgerEntryRecord`

**Acceptance criteria:** Tables created via Alembic. Repository methods tested against real DB. `get_and_lock()` acquires row-level lock.

---

## Phase 1B: Fiat Ledger — Business Logic

**Goal:** Implement deposit, withdrawal, and transfer with full invariant enforcement.

### 1B-1. Deposit Flow
```
POST /api/v1/wallets/{id}/deposit
  Body: { amount_minor: 10050, idempotency_key: "dep-abc-123" }

Service:
  1. Check idempotency_key → if exists, return cached result
  2. BEGIN transaction
  3. Lock wallet (SELECT FOR UPDATE)
  4. Create transaction record
  5. Create ledger entry (direction='credit', amount_minor=+10050)
  6. Update wallet.balance_minor += 10050
  7. Audit log
  8. COMMIT
```

### 1B-2. Withdrawal Flow
```
POST /api/v1/wallets/{id}/withdraw
  Body: { amount_minor: 5000, idempotency_key: "wd-xyz-456" }

Service:
  1. Check idempotency_key
  2. BEGIN transaction
  3. Lock wallet
  4. Verify balance_minor >= amount (else raise InsufficientFundsError)
  5. Create transaction + ledger entry (direction='debit', amount_minor=-5000)
  6. Update wallet.balance_minor -= 5000
  7. Audit log
  8. COMMIT
```

### 1B-3. Transfer Flow (Deadlock-Safe)
```
POST /api/v1/transfers
  Body: { from_wallet_id, to_wallet_id, amount_minor, idempotency_key }

Service:
  1. Check idempotency_key
  2. BEGIN transaction
  3. Lock BOTH wallets in deterministic order (lower UUID first)
     → SELECT ... FROM wallets WHERE id IN ($1, $2) ORDER BY id FOR UPDATE
  4. Verify sender balance >= amount
  5. Create ONE transaction record
  6. Create TWO ledger entries:
     - Debit from sender (amount_minor = -N)
     - Credit to receiver (amount_minor = +N)
  7. Update both wallet balances
  8. Audit log
  9. COMMIT
```

### 1B-4. Reconciliation Job
- [ ] Background task: for each wallet, verify `balance_minor == SUM(ledger_entries.amount_minor)`
- [ ] Log discrepancies to audit_logs with `event_type = 'balance_drift_detected'`
- [ ] Run as a scheduled cron (every hour in prod, every 5 min in dev)

**Acceptance criteria:** Deposit/withdraw/transfer work atomically. Idempotency keys prevent double-processing. Concurrent opposite-direction transfers never deadlock. Reconciliation job catches zero drift.

---

## Phase 1C: Fiat Ledger — API & Testing

### 1C-1. Router Layer
- [ ] `POST /api/v1/wallets` — create wallet (one per currency per user)
- [ ] `GET /api/v1/wallets` — list user's wallets
- [ ] `GET /api/v1/wallets/{id}` — wallet details
- [ ] `POST /api/v1/wallets/{id}/deposit`
- [ ] `POST /api/v1/wallets/{id}/withdraw`
- [ ] `POST /api/v1/transfers`
- [ ] `GET /api/v1/wallets/{id}/transactions` — paginated history

### 1C-2. Schemas
- [ ] `CreateWalletRequest`, `WalletResponse`
- [ ] `DepositRequest`, `WithdrawRequest`, `TransferRequest`
- [ ] `TransactionResponse` (with pagination metadata)

### 1C-3. Tests
- [ ] Happy path: deposit → check balance → withdraw → check balance
- [ ] Idempotency: same key twice → same result, balance unchanged
- [ ] Insufficient funds: withdrawal > balance → 400 error, balance unchanged
- [ ] Concurrent transfers: 100 parallel opposite-direction transfers → no deadlocks, final balances consistent
- [ ] Double-entry invariant: SUM(all entries) = 0 for every transfer
- [ ] Reconciliation: manually corrupt balance → job detects drift

**Acceptance criteria:** Full CRUD API with pagination. All ledger invariants tested under concurrency. Zero balance drift in stress tests.

---

## Phase 2: Card Vault (Stripe)

**Goal:** PCI-scope-free card storage and card-funded deposits.

### Steps
1. Integrate Stripe SDK (`stripe` Python package)
2. Create `cards` table: `id, user_id, stripe_payment_method_id, last4, brand, exp_month, exp_year, is_default`
3. `POST /api/v1/cards` — create Stripe PaymentMethod, store tokenized reference
4. `GET /api/v1/cards` — list user's cards
5. `DELETE /api/v1/cards/{id}` — detach from Stripe + soft delete
6. `POST /api/v1/wallets/{id}/deposit/card` — charge card via Stripe → credit wallet via ledger
7. Webhook handler for async Stripe events (payment_intent.succeeded, payment_intent.failed)

**Acceptance criteria:** No raw card numbers stored. Stripe handles PCI compliance. Card-funded deposits produce proper ledger entries.

---

## Phase 3: Crypto Wallets

**Goal:** HD wallet derivation, address generation, and on-chain balance tracking.

### Steps
1. BIP39 mnemonic generation (master seed per user, encrypted at rest)
2. BIP32/44 HD key derivation (`m/44'/0'/0'/0/n` for Bitcoin, `m/44'/60'/0'/0/n` for Ethereum)
3. Address generation and storage
4. `POST /api/v1/crypto/wallets` — derive next address for user
5. `GET /api/v1/crypto/wallets` — list crypto addresses + on-chain balances
6. On-chain balance sync worker (poll blockchain nodes or use indexer API)
7. Deposit detection (monitor addresses for incoming transactions)
8. Withdrawal flow (sign + broadcast transaction)

**Acceptance criteria:** Deterministic address derivation from master seed. On-chain balance matches within 1 block. Withdrawal requires user confirmation.

---

## Cross-Cutting Concerns (Ongoing)

| Concern | When | How |
|---|---|---|
| CI/CD | Phase 0A | GitHub Actions: lint (ruff), type-check (mypy), test (pytest) |
| Logging | Phase 0A | `structlog` with JSON output, request ID correlation |
| Monitoring | Phase 1B | Prometheus metrics, health endpoint with DB/Redis checks |
| API Docs | Phase 1C | OpenAPI descriptions, Postman collection |
| Load Testing | Phase 1C | `locust` or `k6` for concurrent transfer stress tests |
| Deployment | Phase 2 | Docker multi-stage build, env-specific configs, secrets management |
