# app/users/schemas/auth.py

import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# =====================================================================
# Umumy walidasiýa kadalary - birnäçe schema-da gaýtalanýar bolsa,
# bir ýerde jemläp, DRY saklaýarys.
# =====================================================================

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,32}$")

# NIST 800-63B maslahaty: minimum uzynlyk möhüm, "hökman-uly-harp-belgi"
# ýaly düzgünler köplenç ulanyjyny "Password1!" ýaly gowşak-emma-kada-gabat-gelýän
# parollara iterýär. Şonuň üçin biz diňe UZYNLYK bilen "iň köp ýaýran
# gowşak parollar" sanawyny barlaýarys, ýöne çylşyrymlylyk mejbur etmeýäris.
_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_LENGTH = (
    128  # DoS-dan gorag: çäksiz uzyn parol argon2-ni haýalladyp biler
)

_COMMON_WEAK_PASSWORDS = {
    "password123",
    "12345678910",
    "qwertyuiop12",
    "letmein12345",
    # önümçilikde bu sanaw "Have I Been Pwned" API-sinden ýa-da
    # rockyou.txt ýaly sanawdan has giň bolmaly
}


def _validate_password_strength(value: str) -> str:
    if len(value) < _MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Parol azyndan {_MIN_PASSWORD_LENGTH} belgiden ybarat bolmaly"
        )
    if len(value) > _MAX_PASSWORD_LENGTH:
        raise ValueError(f"Parol {_MAX_PASSWORD_LENGTH} belgiden köp bolmaly däl")
    if value.lower() in _COMMON_WEAK_PASSWORDS:
        raise ValueError("Bu parol gaty ýönekeý, başga parol saýlaň")
    return value


# =====================================================================
# REGISTER
# =====================================================================


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(
        min_length=_MIN_PASSWORD_LENGTH, max_length=_MAX_PASSWORD_LENGTH
    )

    @field_validator("username")
    @classmethod
    def validate_username_format(cls, value: str) -> str:
        if not _USERNAME_PATTERN.match(value):
            raise ValueError("Ulanyjy ady diňe harp, san we '_' bolmaly (3-32 belgi)")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class RegisterResponse(BaseModel):
    user_id: UUID
    email: str
    message: str = "Hasabyňyzy tassyklamak üçin e-poçtaňyzy barlaň"


# =====================================================================
# LOGIN
# =====================================================================


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr
    password: str = Field(min_length=1, max_length=_MAX_PASSWORD_LENGTH)
    totp_code: str | None = Field(
        default=None, min_length=6, max_length=6, pattern=r"^\d{6}$"
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = (
        900  # security.py-daky ACCESS_TOKEN_TTL_SECONDS bilen SINHRON saklanmaly
    )
