# app/users/schemas/profile.py

import re
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

# =====================================================================
# RESPONSE
# =====================================================================


class UserProfileResponse(BaseModel):
    """
    GET /users/me we PATCH /users/me-iň jogaby. hashed_password,
    totp_secret_encrypted, failed_login_count ýaly içki meýdanlar
    BILKASTLAÝYN goşulmady - bular "response" modeli, "database
    record" modeli däl. Registration-daky UserPublic bilen edil
    şol bir ýörelge.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    totp_enabled: bool
    email_verified: bool


# =====================================================================
# UPDATE (PATCH /users/me)
# =====================================================================


class UserProfileUpdate(BaseModel):
    """
    Ikisi-de Optional - PATCH semantikasy: iberilmedik meýdan
    "üýtgetme" diýmek. Field(None, ...) ýerine Field(default=None)
    ulanýarys, sebäbi exclude_unset router-de "iberildimi ýa-da
    diňe default-my" diýip tapawutlandyrmak üçin gerek - eger client
    {"username": null} iberse, bu "None-a üýtget" diýmek, iberilmese
    "degme" diýmek. İkisi hem pydantic-de "None" bolup görünýär,
    ýöne exclude_unset muny tapawutlandyrýar.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    username: Annotated[
        str | None,
        Field(default=None, min_length=3, max_length=32),
    ] = None
    email: Annotated[EmailStr | None, Field(default=None)] = None

    @field_validator("username")
    @classmethod
    def username_charset(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.fullmatch(r"[a-zA-Z0-9_.]+", v):
            raise ValueError(
                "Username may only contain letters, digits, underscores, and dots."
            )
        if v[0] in "._" or v[-1] in "._":
            raise ValueError("Username cannot start or end with '.' or '_'.")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserProfileUpdate":
        """
        Boş PATCH ({} body) mümkin, ýöne muny 422 bilen ret etmek
        has aýdyň - "sen hiç zat üýtgetjek bolmadyň" diýip client-e
        derrew aýtmak, service gatlagynda dymyp "return" etmekden
        gowy (fail-fast).
        """
        if self.username is None and self.email is None:
            raise ValueError("At least one field (username or email) must be provided.")
        return self


# =====================================================================
# PASSWORD CHANGE (PATCH /users/me/password)
# =====================================================================


_PASSWORD_MIN_LENGTH = 12


class PasswordChangeRequest(BaseModel):
    """
    SecretStr - registration-daky RegisterRequest bilen edil şol bir
    ýörelge: repr()/log-da plaintext görünmesin diýip. Router-de
    .get_secret_value() bilen açylýar, diňe service-e girmezden öň.
    """

    current_password: SecretStr
    new_password: SecretStr

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        if len(raw) < _PASSWORD_MIN_LENGTH:
            raise ValueError(
                f"Password must be at least {_PASSWORD_MIN_LENGTH} characters."
            )
        if not re.search(r"[A-Z]", raw):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", raw):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", raw):
            raise ValueError("Password must contain at least one digit.")
        return v

    @model_validator(mode="after")
    def new_differs_from_current(self) -> "PasswordChangeRequest":
        """
        Bu, service-daky verify_password() barlagynyň ORNUNA DÄL -
        goşmaça. Bu ýerdäki barlag diňe "iki plaintext string edil
        deňmi" diýip tekst taýdan deňeşdirýär (ucuz, hash-lamazdan
        derrew 422 gaýtaryp bolýar). Emma current_password DOGRUMY
        diýen barlag diňe service-de bolup biler, sebäbi diňe şol
        ýerde hakyky hash bar. Şonuň üçin SamePasswordError henizem
        service-de galýar - bu ýerki barlag diňe "aýdyň ýalňyşlyklary
        irräk tutmak" üçin, howpsuzlyk gatlagy däl.
        """
        if (
            self.current_password.get_secret_value()
            == self.new_password.get_secret_value()
        ):
            raise ValueError(
                "New password must be different from the current password."
            )
        return self
