# 🧠 SuperWallet — Skills & Knowledge Map

> Technical skills demonstrated, learned, and required across each stage of the project.

---

## Skills Demonstrated (Stage 0 — Identity & Auth)

### Backend Architecture
| Skill | Where Applied | Depth |
|---|---|---|
| **Modular monolith design** | `app/{users,fiat,cards,crypto}/` — domain-isolated vertical slices | Architecture decision: monolith because domains share transactional boundaries |
| **Layered architecture** | Router → Service → Repository pattern in every domain | Service layer owns transactions; repository layer is pure data access |
| **Dependency injection** | FastAPI `Depends()` for DB connections, auth, request context | Constructor injection for services; factory functions in routers |
| **Domain exception hierarchy** | `AppError → AuthError → 15+ specific exceptions` | Machine-readable `error_code`, HTTP-agnostic `http_status` hint, structured `details` for logging |

### Database & SQL
| Skill | Where Applied | Depth |
|---|---|---|
| **Raw async SQL** | All repository methods use `asyncpg` directly | No ORM — full control over query shape, locking, and transaction boundaries |
| **Connection pool management** | `DatabasePool` singleton in `core/database.py` | Lifespan-managed pool (2–20 connections), single-connection-per-transaction discipline |
| **Transaction composability** | Services open `async with conn.transaction()`, repositories receive the connection | Multiple repos participate in one atomic transaction |
| **Schema migrations** | 8 Alembic migrations with raw SQL (`op.execute()`) | Proper `down_revision` chain, `pgcrypto` extension, partial indexes |
| **UUID primary keys** | All tables use `gen_random_uuid()` | Avoids sequential ID enumeration attacks |

### Security & Cryptography
| Skill | Where Applied | Depth |
|---|---|---|
| **Argon2id password hashing** | `users/security.py` — `PasswordHasher` with OWASP params | Memory-hard, GPU-resistant; transparent rehash-on-login when params change |
| **Custom HMAC-SHA256 signed tokens** | `core/security.py` — `sign_token()` / `verify_token()` | Hand-built JWT-like tokens without library dependency; constant-time signature comparison |
| **Purpose-scoped tokens** | Access vs. email-verify vs. password-reset tokens | `purpose` claim prevents cross-use attacks (e.g., using a verify link as an access token) |
| **Opaque refresh tokens** | `secrets.token_urlsafe(32)` stored hashed (SHA-256) | Not JWT — no claims to decode; value is in server-side session lookup |
| **Refresh token rotation + reuse detection** | `SessionRepository.rotate()` + `get_by_used_token_hash()` | Old token kept with `revoked_reason='rotated'`; reuse triggers `revoke_all_for_user()` |
| **TOTP 2FA** | PyOTP (RFC 6238) with encrypted-at-rest secrets | Fernet (AES-128-CBC + HMAC-SHA256); `valid_window=1` for clock skew; backup codes hashed with Argon2 |
| **Account lockout** | Progressive: 6 fails → 15 min, 10 fails → 1 hour | Prevents brute-force without becoming a DoS vector (temporary, not permanent) |
| **HttpOnly secure cookies** | Refresh token delivered as `HttpOnly, Secure, SameSite=Strict` cookie | XSS cannot read; CSRF mitigated by SameSite; scoped to `/auth` path |

### Async Python & Patterns
| Skill | Where Applied | Depth |
|---|---|---|
| **asyncio event loop** | FastAPI async endpoints, asyncpg async queries | Full async stack — no sync database calls |
| **Transactional outbox pattern** | `OutboxRepository` — write side effect intent in same transaction | Eliminates dual-write bugs; worker polls with `FOR UPDATE SKIP LOCKED` |
| **Background worker** | `notifications/worker.py` — async polling loop | Retry logic with max attempts; handler dispatch by event type |
| **Dataclass records** | `UserRecord`, `SessionRecord`, `VerificationTokenRecord` | Typed return values from repositories instead of raw `dict` |

---

## Skills Required (Stage 1 — Fiat Ledger)

### Double-Entry Accounting
- **Concept:** Every money movement creates at least two entries that sum to zero
- **Application:** Transfer = 1 debit entry + 1 credit entry in `ledger_entries`
- **Invariant:** `SUM(amount_minor) = 0` for every transaction; wallet balance = `SUM(entries for wallet)`

### Concurrency Control
- **Row-level locking:** `SELECT ... FOR UPDATE` on wallet rows before balance mutation
- **Deadlock prevention:** Always lock wallets in ascending UUID order (deterministic lock ordering)
- **`SKIP LOCKED`:** Already used in outbox; may be useful for parallel deposit processing

### Idempotency
- **Concept:** Retrying the same request produces the same result without side effects
- **Implementation:** `UNIQUE` constraint on `transactions.idempotency_key`; service checks before processing
- **Why DB-level:** Application-level check has a TOCTOU race window; DB constraint closes it

### Balance Reconciliation
- **Cached balance:** `wallets.balance_minor` is a denormalized cache updated in every transaction
- **Source of truth:** `SUM(ledger_entries.amount_minor) WHERE wallet_id = ?`
- **Reconciliation job:** Periodic comparison; drift = critical alert

---

## Skills Required (Stage 2 — Card Vault)

### Payment Processing
- Stripe SDK integration (Python)
- PCI-DSS scope awareness (tokenization means we never see card numbers)
- Webhook signature verification
- Asynchronous payment flow (PaymentIntent → webhook → ledger credit)

### Error Handling in Payments
- Idempotency keys for Stripe API calls
- Handling declined cards gracefully
- Retry logic for transient Stripe failures
- Partial failure scenarios (charge succeeds, ledger write fails → compensation logic)

---

## Skills Required (Stage 3 — Crypto)

### HD Wallet Derivation
- BIP39: Mnemonic → seed
- BIP32: Seed → master key → child keys (derivation paths)
- BIP44: `m/44'/coin'/account'/change/index` standardized paths
- Key encryption at rest (Fernet or envelope encryption)

### Blockchain Integration
- Address generation per cryptocurrency
- Balance queries (RPC nodes or indexer APIs)
- Transaction broadcasting (signing + serialization)
- Confirmation tracking (block depth monitoring)

---

## Skills Practiced Throughout

| Skill | How |
|---|---|
| **First-principles reasoning** | Every table, lock, and constraint has a documented "why" — no copy-paste from tutorials |
| **NIST & OWASP compliance** | Password policy (800-63B), hashing (OWASP Argon2 params), token security |
| **Defensive programming** | Generic error messages to prevent enumeration, constant-time comparisons, encrypted secrets at rest |
| **Progressive complexity** | Each stage builds on the last — auth → ledger → payments → crypto |
| **Documentation-driven development** | README, ARCHITECTURE, PLAN, and TODO are maintained alongside code |

---

## Learning Resources Used

| Topic | Resource |
|---|---|
| Password hashing | OWASP Password Storage Cheat Sheet |
| Refresh token rotation | Auth0 "Refresh Token Rotation" whitepaper |
| Double-entry ledger | Martin Fowler — "Accounting Patterns" |
| Idempotency | Stripe — "Designing Robust and Predictable APIs" |
| Deadlock prevention | PostgreSQL docs — "Explicit Locking" chapter |
| HD wallets | BIP32/39/44 specification documents |
| Transactional outbox | Microservices.io — "Transactional Outbox Pattern" |
| TOTP 2FA | RFC 6238 — Time-Based One-Time Password Algorithm |
