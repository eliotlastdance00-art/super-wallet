"""
core/exceptions.py — Auth domain-specific exceptions for SuperWallet.

Design principles:
- HTTP-agnostic: the service layer never imports fastapi.HTTPException.
    Each exception carries a stable `error_code` (for the client / i18n)
    and a `details` dict (for structured logging).
- `http_status` is only a *hint* consumed by the global exception handler
    in main.py — it lives here purely to avoid a giant if/elif chain there,
    it does not mean this module depends on HTTP concepts.
- `EXCEPTION_REGISTRY` lets the handler resolve error_code -> class in O(1)
    and is handy in tests when you want to assert "this error_code was raised".
"""

from __future__ import annotations

import datetime
import enum
from typing import Any, ClassVar


class AppError(Exception):
    """Base class for every domain-level exception in SuperWallet."""

    error_code: ClassVar[str] = "internal_error"
    http_status: ClassVar[int] = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(error_code={self.error_code!r}, "
            f"message={self.message!r}, details={self.details!r})"
        )

    def to_log_dict(self) -> dict[str, Any]:
        """Structured payload for logger.error(..., extra=exc.to_log_dict())."""
        return {"error_code": self.error_code, "message": self.message, **self.details}


class AuthError(AppError):
    """Base class for the auth bounded context. Lets the handler do
    `except AuthError` if it wants one broad branch instead of nine."""

    error_code: ClassVar[str] = "auth_error"
    http_status: ClassVar[int] = 401


# ── Registration (uniqueness) ────────────────────────────────────────────


class EmailAlreadyExistsError(AuthError):
    error_code: ClassVar[str] = "email_already_exists"
    http_status: ClassVar[int] = 409

    def __init__(self, email: str) -> None:
        super().__init__(
            "An account with this email already exists.", details={"email": email}
        )


class UsernameAlreadyExistsError(AuthError):
    error_code: ClassVar[str] = "username_already_exists"
    http_status: ClassVar[int] = 409

    def __init__(self, username: str) -> None:
        super().__init__(
            "This username is already taken.", details={"username": username}
        )


# ── Login ─────────────────────────────────────────────────────────────────


class LoginError(AuthError):
    """Wrong email or password. Message is deliberately generic — never
    reveal *which* field was wrong, that's a user-enumeration vector."""

    error_code: ClassVar[str] = "invalid_credentials"
    http_status: ClassVar[int] = 401

    def __init__(self, *, email: str | None = None) -> None:
        # email kept only in `details` for server-side logs, never surfaced to the client
        super().__init__(
            "Invalid email or password.", details={"email": email} if email else {}
        )


class AccountLockedError(AuthError):
    """Raised after N consecutive failed logins (brute-force protection)."""

    error_code: ClassVar[str] = "account_locked"
    http_status: ClassVar[int] = 423  # 423 Locked

    def __init__(
        self,
        *,
        locked_until: datetime.datetime | None = None,
        failed_attempts: int | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if locked_until is not None:
            details["locked_until"] = locked_until.isoformat()
        if failed_attempts is not None:
            details["failed_attempts"] = failed_attempts
        super().__init__(
            "Account is temporarily locked due to repeated failed login attempts.",
            details=details,
        )


# ── TOTP / 2FA ───────────────────────────────────────────────────────────


class TotpRequiredError(AuthError):
    """Password was correct but account has 2FA enabled — client must
    submit a second request with the TOTP code (usually alongside a
    short-lived `partial_token` issued for this purpose)."""

    error_code: ClassVar[str] = "totp_required"
    http_status: ClassVar[int] = 401

    def __init__(self, *, user_id: str | None = None) -> None:
        super().__init__(
            "Two-factor authentication code required.",
            details={"user_id": user_id} if user_id else {},
        )


class InvalidTotpError(AuthError):
    error_code: ClassVar[str] = "invalid_totp"
    http_status: ClassVar[int] = 401

    def __init__(self, *, attempts_remaining: int | None = None) -> None:
        details = (
            {"attempts_remaining": attempts_remaining}
            if attempts_remaining is not None
            else {}
        )
        super().__init__("Invalid two-factor authentication code.", details=details)


# ── Refresh tokens ───────────────────────────────────────────────────────


class RefreshTokenInvalidReason(str, enum.Enum):
    """Why a refresh token was rejected. `REUSED` matters most: in a
    rotating-refresh-token scheme, reuse of an already-rotated token is a
    signal of theft, not just an ordinary expiry, and should trigger
    revocation of the *whole* token family, not just this one."""

    EXPIRED = "expired"
    REVOKED = "revoked"
    REUSED = "reused"
    MALFORMED = "malformed"
    MISSING ="missing"


class InvalidRefreshTokenError(AuthError):
    error_code: ClassVar[str] = "invalid_refresh_token"
    http_status: ClassVar[int] = 401

    def __init__(
        self,
        reason: RefreshTokenInvalidReason,
        *,
        user_id: str | None = None,
        token_family_id: str | None = None,
    ) -> None:
        self.reason = reason
        details: dict[str, Any] = {"reason": reason.value}
        if user_id:
            details["user_id"] = user_id
        if token_family_id:
            details["token_family_id"] = token_family_id
        super().__init__(f"Refresh token is invalid: {reason.value}.", details=details)

    @property
    def is_reuse_attack(self) -> bool:
        """Convenience flag the service layer can check to decide whether
        to nuke the whole token family (session hijack response)."""
        return self.reason is RefreshTokenInvalidReason.REUSED


# ── Sessions ─────────────────────────────────────────────────────────────


class SessionExpiredError(AuthError):
    error_code: ClassVar[str] = "session_expired"
    http_status: ClassVar[int] = 401

    def __init__(
        self, *, session_id: str, expired_at: datetime.datetime | None = None
    ) -> None:
        details: dict[str, Any] = {"session_id": session_id}
        if expired_at is not None:
            details["expired_at"] = expired_at.isoformat()
        super().__init__("Session has expired.", details=details)


class SessionNotFoundError(AuthError):
    error_code: ClassVar[str] = "session_not_found"
    http_status: ClassVar[int] = 404

    def __init__(self, session_id: str) -> None:
        super().__init__("Session not found.", details={"session_id": session_id})


# ── Registry ─────────────────────────────────────────────────────────────

EXCEPTION_REGISTRY: dict[str, type[AuthError]] = {
    cls.error_code: cls  # type: ignore[misc]
    for cls in (
        EmailAlreadyExistsError,
        UsernameAlreadyExistsError,
        LoginError,
        AccountLockedError,
        TotpRequiredError,
        InvalidTotpError,
        InvalidRefreshTokenError,
        SessionExpiredError,
        SessionNotFoundError,
    )
}

__all__ = [
    "AppError",
    "AuthError",
    "EmailAlreadyExistsError",
    "UsernameAlreadyExistsError",
    "LoginError",
    "AccountLockedError",
    "TotpRequiredError",
    "InvalidTotpError",
    "RefreshTokenInvalidReason",
    "InvalidRefreshTokenError",
    "SessionExpiredError",
    "SessionNotFoundError",
    "EXCEPTION_REGISTRY",
]


class InvalidVerificationTokenError(Exception):
    """Email-verify JWT bozuk/expire/purpose ýalňyş bolanda."""
    def __init__(self, reason: str = "invalid_token"):
        self.reason = reason


class PasswordResetTokenInvalidError(Exception):
    """Password-reset opaque token tapylmady/eýýäm ulanyldy/expire boldy."""
    def __init__(self, reason: str = "invalid_or_used"):
        self.reason = reason