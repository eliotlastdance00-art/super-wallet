# 🏗️ SuperWallet — Architecture

> A modular-monolith fintech backend built from first principles.

---

## System Overview

SuperWallet is a **modular monolith** — a single deployable FastAPI service, internally organized by business domain (not by technical layer). Each domain owns its full vertical slice: router → service → repository → schemas.

```
                      ┌─────────────────────────────┐
                      │         Client (HTTP)        │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │     FastAPI Application      │
                      │   (app/main.py — lifespan)   │
                      └──────────────┬──────────────┘
                                     │
                      ┌──────────────┴──────────────┐
                      │        V1 API Router         │
                      │      /api/v1/*               │
                      └──────────────┬──────────────┘
                                     │
            ┌────────────────────────┼───────────────────────┐
            │                        │                       │
   ┌────────▼────────┐    ┌─────────▼────────┐    ┌────────▼────────┐
   │    users/        │    │     fiat/         │    │   cards/crypto/ │
   │  (Auth domain)   │    │  (Ledger domain)  │    │   (Planned)    │
   │   ✅ Active      │    │   🚧 Stubs        │    │   ⏳ Empty     │
   └────────┬────────┘    └─────────┬────────┘    └────────────────┘
            │                       │
            ▼                       ▼
   ┌─────────────────────────────────────────┐
   │              core/                      │
   │  config · database · security · audit   │
   │  outbox · dependencies · exceptions     │
   └───────────────────┬─────────────────────┘
                       │
          ┌────────────┼──────────────┐
          ▼            ▼              ▼
   ┌───────────┐ ┌──────────┐ ┌────────────┐
   │ PostgreSQL│ │  Redis   │ │   SMTP     │
   │  (asyncpg)│ │ (reserved)│ │(aiosmtplib)│
   └───────────┘ └──────────┘ └────────────┘
```

---

## Module Boundaries

### `app/core/` — Shared Infrastructure

| File | Responsibility |
|---|---|
| `config.py` | `pydantic-settings` based env config (`Settings` singleton) |
| `database.py` | `DatabasePool` singleton — asyncpg connection pool lifecycle |
| `security.py` | Custom HMAC-SHA256 signed tokens, Fernet encryption, CSPRNG, opaque token hashing |
| `audit.py` | `log_audit_event()` — single INSERT into `audit_logs`, called within existing transactions |
| `outbox.py` | `OutboxRepository` — transactional outbox pattern (enqueue, fetch_pending, mark_done/failed) |
| `dependencies.py` | FastAPI `Depends()` — `get_db`, `get_current_user` (OAuth2 bearer → UUID) |
| `exceptions.py` | Empty — the real hierarchy lives in `users/exception.py` (known issue) |

### `app/users/` — Identity & Auth Domain

```
users/
├── exception.py          # AppError → AuthError → 15+ domain exceptions + EXCEPTION_REGISTRY
├── security.py           # Argon2 password hashing, access/refresh/purpose tokens, TOTP, backup codes, lockout
├── repository.py         # UserRepository, SessionRepository, VerificationTokenRepository (dataclasses + raw SQL)
├── router/
│   ├── auth.py           # POST /register, /login, /logout, /refresh
│   ├── session_auth.py   # POST /verify-email, /resend-verification, /forgot-password, /reset-password; GET/DELETE /sessions
│   └── profile.py        # GET/PATCH /me, PATCH /me/password, DELETE /me
├── services/
│   ├── auth.py           # RegisterService, LoginService, LogoutService, RefreshService
│   ├── session_auth.py   # EmailVerificationService, PasswordResetService, SessionManagementService
│   └── profile.py        # ProfileService (get, update, change password, deactivate)
└── schemas/
    ├── auth.py           # RegisterRequest/Response, LoginRequest, TokenResponse
    ├── session_auth.py   # VerifyEmail, ForgotPassword, ResetPassword, SessionOut
    └── profile.py        # UserProfileResponse, UserProfileUpdate, PasswordChangeRequest
```

### `app/notifications/` — Outbox Consumer (Separate Process)

```
notifications/
├── worker.py             # asyncio polling loop — drains outbox_events, dispatches to handlers
├── templates.py          # HTML email renderers (verification, password reset)
├── handlers/
│   └── email_handler.py  # event_type → template → email provider
└── providers/
    └── email_provider.py # aiosmtplib SMTP send (hostname, TLS, credentials)
```

### `app/fiat/`, `app/cards/`, `app/crypto/` — Future Domains

All contain empty `__init__.py` files (and empty stubs for fiat). These are placeholders for Stages 1–3.

---

## Data Flow

### Request Lifecycle

```
1. HTTP Request arrives
2. FastAPI routing → Pydantic validation (schemas)
3. Router: acquires DB connection via Depends(get_db)
4. Router: constructs Service with Repository instances
5. Service: opens async with conn.transaction()
6. Service: calls Repository methods (raw SQL, single connection)
7. Service: calls log_audit_event() within the same transaction
8. Service: calls OutboxRepository.enqueue() for side effects (same transaction)
9. Transaction commits atomically (business data + audit + outbox)
10. Router: returns Pydantic response model
```

### Token Flow (Auth)

```
Register/Login → access_token (body) + refresh_token (HttpOnly cookie)
                            │                        │
                            ▼                        ▼
               Short-lived (15 min)         Long-lived (30 days)
               HMAC-SHA256 signed           Opaque (secrets.token_urlsafe)
               Stateless verification       Stored HASHED in sessions table
                                            Rotation on every /refresh
                                            Reuse → revoke ALL user sessions
```

### Outbox Pattern (Email Delivery)

```
Service (in transaction)
  ├── INSERT INTO users ...
  ├── INSERT INTO outbox_events (event_type, payload, status='pending')
  └── COMMIT

notification_worker (separate process, polling every 2s)
  ├── SELECT ... FROM outbox_events WHERE status='pending' FOR UPDATE SKIP LOCKED
  ├── handler(payload) → send email via SMTP
  ├── mark_done(event_id)  OR  mark_failed(event_id) with retry
  └── Max 5 attempts before permanent failure
```

---

## Infrastructure

### Docker Compose Services

| Service | Image/Build | Purpose |
|---|---|---|
| `api` | `Dockerfile` (Python 3.12) | FastAPI app, hot-reload via volume mount |
| `notification_worker` | Same `Dockerfile` | `python -m app.notifications.worker` |
| `db` | `postgres:16` | Primary data store, port 5432 |
| `redis` | `redis:7` | Reserved for session cache / rate limiting (not yet consumed) |

### Database Schema (Current — 8 Migrations Applied)

```
users
├── id: UUID (PK, gen_random_uuid)
├── username, email (UNIQUE)
├── hashed_password (Argon2)
├── failed_login_count, locked_until
├── totp_enabled, totp_secret_encrypted, totp_backup_codes
├── email_verified
├── is_active, deleted_at (soft delete — migration 008)
└── created_at, updated_at

sessions
├── id: UUID (PK)
├── user_id → users(id)
├── refresh_token_hash (UNIQUE index)
├── device_info, ip_address
├── created_at, expires_at
├── revoked_at, revoked_reason
└── replaced_by_session_id → sessions(id) (rotation lineage)

verification_tokens
├── id: UUID (PK, gen_random_uuid default)
├── user_id → users(id) ON DELETE CASCADE
├── token_hash (UNIQUE), type ('email_verify' | 'password_reset')
├── ip_address, expires_at, used_at
└── created_at

audit_logs
├── id: BIGINT (PK)
├── user_id → users(id), event_type, ip_address, user_agent
├── metadata (JSONB)
└── created_at
    Indexes: (user_id, created_at), (event_type, created_at)

outbox_events
├── id: UUID (PK, gen_random_uuid)
├── event_type, payload (JSONB)
├── status ('pending'|'done'|'failed'), attempts, last_error
├── created_at, processed_at
└── Partial index: ix_outbox_events_pending WHERE status='pending'
```

---

## Security Model

### Password Security
- **Argon2id** (OWASP recommended minimums) with transparent rehash-on-login
- Length-only policy (8–128 chars) per NIST 800-63B — no forced complexity rules

### Token Security
| Token Type | Format | Storage | Lifetime | Hash |
|---|---|---|---|---|
| Access | Custom HMAC-SHA256 signed | Client memory only | 15 min | N/A (verified by signature) |
| Refresh | Opaque (`secrets.token_urlsafe`) | HttpOnly, Secure, SameSite=Strict cookie | 30 days | SHA-256 in `sessions` table |
| Email verify | Custom signed (purpose-scoped) | Sent via email | 24 hours | Stored via `verification_tokens` |
| Password reset | Opaque | DB `verification_tokens` (hashed) | 30 min | SHA-256 |

### 2FA (TOTP)
- RFC 6238 via PyOTP
- Secret encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256)
- `valid_window=1` for clock skew tolerance
- Backup codes: Argon2 hashed array in `totp_backup_codes`

### Session Security
- Refresh token rotation on every `/refresh` call
- **Reuse detection**: presenting an already-rotated token → revoke ALL sessions for that user
- `revoked_reason` and `replaced_by_session_id` create an audit trail of token lineage

### Account Lockout
- Progressive: 6 failures → 15 min lock, 10 failures → 1 hour lock
- Auto-reset after lockout expires
- Audit logged: `login_failed`, `login_blocked_locked`

---

## Design Principles

1. **Single connection per transaction** — repositories receive an `asyncpg.Connection`, not the pool. Transaction boundaries are explicit.
2. **Outbox over dual-write** — side effects (emails) are committed in the same transaction as business data.
3. **Integer minor units** — money will be stored as `bigint` (e.g., 10050 = $100.50). No floats, ever.
4. **Deterministic lock ordering** — transfers will lock wallets by ascending `id` to prevent deadlocks.
5. **Append-only ledger** — corrections are reverse entries, never edits or deletes.
6. **Soft delete** — `is_active + deleted_at` on users; hard delete abandoned after FK analysis.
