# app/core/security.py

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from app.core.config import settings

from cryptography.fernet import Fernet, InvalidToken

# =====================================================================
# JWT-ÝALY SIGNED TOKEN (HMAC-SHA256 esasynda, ýörite kitaphanasyz)
# =====================================================================
#
# Näme üçin pyjwt/python-jose ulanman, özümiz ýazýarys?
# Sebäbi bize diňe "HS256 sign + verify + expiry" gerek, RS256, JWKS,
# audience-multi-issuer ýaly zatlar gerek däl. Az bagly kitaphana =
# az attack-surface, az dependency-update ýüki. Emma eger geljekde
# üçünji tarap (mysal, mobil app aýratyn service hökmünde) tokeni
# özi barlamaly bolsa, standart JWT-e geçmek maslahat berilýär.
# Häzirki ýapyk monolith üçin bu ýeterlik.

_SECRET_KEY = settings.TOKEN_SIGNING_KEY


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def sign_token(payload: dict[str, Any], expires_in_seconds: int) -> str:
    """
    Berlen payload-y HMAC-SHA256 bilen gol çekilen token-e öwürýär.
    Format: base64(payload_json).base64(signature)
    """
    body = {**payload, "exp": int(time.time()) + expires_in_seconds}
    body_json = json.dumps(body, separators=(",", ":"), sort_keys=True)
    body_b64 = _b64url_encode(body_json.encode())

    signature = hmac.new(
        _SECRET_KEY.encode(), body_b64.encode(), hashlib.sha256
    ).digest()
    sig_b64 = _b64url_encode(signature)

    return f"{body_b64}.{sig_b64}"


def verify_token(token: str) -> dict[str, Any] | None:
    """
    Token-iň gol çekişini we möhletini barlaýar.
    Nädogry/möhleti geçen bolsa None gaýtarýar - exception atmaýar,
    sebäbi "token nädogry" - beklenilýän ýagdaý, exception-a mynasyp däl.
    """
    try:
        body_b64, sig_b64 = token.split(".")
    except ValueError:
        return None

    expected_sig = hmac.new(
        _SECRET_KEY.encode(), body_b64.encode(), hashlib.sha256
    ).digest()
    actual_sig = _b64url_decode(sig_b64)

    # hmac.compare_digest - constant-time comparison, timing attack-dan goraýar.
    # Adaty "==" ulanylsa, hüjümçi jogap wagtyndan gol çekişiň
    # baýtlaryny kem-kemden çak edip biler (timing side-channel).
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None

    try:
        body = json.loads(_b64url_decode(body_b64))
    except (ValueError, UnicodeDecodeError):
        return None

    if body.get("exp", 0) < time.time():
        return None

    return body


# =====================================================================
# SYMMETRIC ENCRYPTION (Fernet) - PCI-ýaly gizlin maglumat üçin
# =====================================================================
#
# Näme üçin core-da? Sebäbi bu diňe TOTP secret üçin däl -
# geljekde `cards` modulynda kart maglumatyny şifrlemek üçin-de
# edil şu mehanizm gerek bolar. Domen bilimini talap etmeýän arassa
# tehniki gural bolany üçin, bu ýerde ýaşamaly.

_ENCRYPTION_KEY = settings.ENCRYPTION_KEY
_fernet = Fernet(_ENCRYPTION_KEY.encode())


def encrypt_value(raw: str) -> str:
    return _fernet.encrypt(raw.encode()).decode()


def decrypt_value(encrypted: str) -> str | None:
    """Nädogry/köne açar bilen şifrlenen bolsa None gaýtarýar, exception atmaýar."""
    try:
        return _fernet.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return None


# =====================================================================
# KRIPTOGRAFIK TAÝDAN HOWPSUZ RANDOM
# =====================================================================


def generate_secure_random_string(length_bytes: int = 32) -> str:
    """
    Session token, backup kod ýaly "predictable bolmaly däl" zatlar üçin.
    secrets moduly OS-yň CSPRNG-ini ulanýar (Linux-da /dev/urandom).
    """
    return secrets.token_urlsafe(length_bytes)


def hash_opaque_token(raw_token: str) -> str:
    """
    Refresh token/session token ýaly, DB-de PLAINTEXT saklanmaly DÄL
    zatlar üçin. Bu argon2 DÄL - sebäbi bu token eýýäm ýokary entropiýaly
    (secrets bilen gener edilen), brute-force howpy ýok, diňe DB syzsa-da
    token-iň özi paş bolmasyn diýen maksat. Şonuň üçin ýönekeý-de çalt
    SHA-256 ýeterlik (argon2-yň "haýal bolmak" aýratynlygy bu ýerde
    gerek däl, sebäbi hüjümçi eýýäm gysga parollary "çaklap" synanyşmaýar,
    ol eýýäm 256-bitlik random setiri "çaklap" bilmez).
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()
