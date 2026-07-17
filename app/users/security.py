# app/users/security.py

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.security import (
    decrypt_value,
    encrypt_value,
    hash_opaque_token,
    sign_token,
    verify_token,
)

# =====================================================================
# PAROL HASH (argon2id)
# =====================================================================

_ph = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _ph.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        _ph.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False


def needs_rehash(hashed_password: str) -> bool:
    """
    Argon2-yň parametrleri wagtyň geçmegi bilen ýokarlandyrylsa (has köp
    memory/iteration), köne hash-lar "gowşak" bolup galýar. Bu funksiýa
    "bu hash täze parametrler bilen gaýtadan hash-lanmalymy" diýip barlaýar.
    Ulanylyşy: login üstünlikli bolanda, plaintext parol elmydama elde
    bolýar - şol pursaty ulanyp, arkaýyn täzeläp bolýar.
    """
    return _ph.check_needs_rehash(hashed_password)


# =====================================================================
# ACCESS TOKEN (gysga ömürli, stateless)
# =====================================================================

ACCESS_TOKEN_TTL_SECONDS = 15 * 60  # 15 min


def create_access_token(user_id: UUID) -> str:
    return sign_token({"sub": str(user_id), "type": "access"}, ACCESS_TOKEN_TTL_SECONDS)


def decode_access_token(token: str) -> UUID | None:
    payload = verify_token(token)
    if payload is None or payload.get("type") != "access":
        return None
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


# =====================================================================
# PURPOSE-SCOPED TOKEN (email verification, password reset)
# =====================================================================
#
# Näme üçin bular "access token" bilen edil şol funksiýany ulanmaýar?
# Sebäbi "purpose" claim-i BOLMASA, howply ýalňyşlyk bolup biler:
# eger email-verification token-i, ýalňyşlyk bilen access-token hökmünde
# kabul edilse, hüjümçi "email tassyklama linkini" ulanyp, hasaba giriş
# edip biler. Purpose barlagy - bu hüjümiň öňüni alýan esasy gorag.

EMAIL_VERIFICATION_TTL_SECONDS = 24 * 60 * 60  # 1 gün
PASSWORD_RESET_TTL_SECONDS = 30 * 60  # 30 min - gysga, sebäbi has howply


def password_reset_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=PASSWORD_RESET_TTL_SECONDS)


def create_email_verification_token(user_id: UUID) -> str:
    return sign_token(
        {"sub": str(user_id), "purpose": "verify_email"},
        EMAIL_VERIFICATION_TTL_SECONDS,
    )


def create_password_reset_token(user_id: UUID) -> str:
    return sign_token(
        {"sub": str(user_id), "purpose": "reset_password"},
        PASSWORD_RESET_TTL_SECONDS,
    )


def decode_purpose_token(token: str, expected_purpose: str) -> UUID | None:
    """
    Bir umumy funksiýa - purpose barlagyny merkezleşdirýär, her ýerde
    "if payload['purpose'] != ..." diýip gaýtalanmaz ýaly.
    """
    payload = verify_token(token)
    if payload is None or payload.get("purpose") != expected_purpose:
        return None
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


# =====================================================================
# REFRESH TOKEN (opaque, DB-de hash görnüşinde saklanýar)
# =====================================================================

REFRESH_TOKEN_TTL = timedelta(days=30)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + REFRESH_TOKEN_TTL


# hash_opaque_token core-dan gaýtadan eksport edilýär - repository/service
# gatlagy "users/security" import etse ýeterlik, core-a göni degmez.
# Bu, "users domeni öz security funksiýalaryny nireden alýandygyny gizlin
# saklaýar" diýen encapsulation ýörelgesi.
hash_refresh_token = hash_opaque_token


# =====================================================================
# TOTP (2FA)
# =====================================================================


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_totp_secret(raw_secret: str) -> str:
    return encrypt_value(raw_secret)


def decrypt_totp_secret(encrypted_secret: str) -> str | None:
    return decrypt_value(encrypted_secret)


def verify_totp_code(raw_secret: str, code: str) -> bool:
    return pyotp.TOTP(raw_secret).verify(code, valid_window=1)


def generate_provisioning_uri(raw_secret: str, user_email: str) -> str:
    return pyotp.TOTP(raw_secret).provisioning_uri(
        name=user_email, issuer_name="SuperWallet"
    )


# =====================================================================
# BACKUP KODLAR
# =====================================================================


def generate_backup_codes(count: int = 10) -> list[str]:
    return [secrets.token_hex(4) for _ in range(count)]


def hash_backup_codes(codes: list[str]) -> list[str]:
    return [_ph.hash(code) for code in codes]


def verify_backup_code(code: str, hashed_codes: list[str]) -> tuple[bool, int | None]:
    for i, hashed in enumerate(hashed_codes):
        try:
            _ph.verify(hashed, code)
            return True, i
        except VerifyMismatchError:
            continue
    return False, None


# =====================================================================
# ACCOUNT LOCKOUT
# =====================================================================

_LOCKOUT_THRESHOLDS: dict[int, timedelta] = {
    6: timedelta(minutes=15),
    10: timedelta(hours=1),
}


def compute_lockout(failed_count: int) -> datetime | None:
    applicable = [
        d for threshold, d in _LOCKOUT_THRESHOLDS.items() if failed_count >= threshold
    ]
    if not applicable:
        return None
    return datetime.now(timezone.utc) + max(applicable)
