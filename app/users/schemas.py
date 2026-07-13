import re
from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from typing_extensions import Self


class UserRegisterSchema(BaseModel):
    # 1. Username: Trims leading/trailing whitespace, max 50 chars (DB constraint)
    username: str = Field(
        ..., min_length=3, max_length=50, description="Unique username of the user"
    )

    # 2. Email: Pydantic's EmailStr automatically validates the email format
    email: EmailStr = Field(
        ..., max_length=100, description="Official email address of the user"
    )

    # 3. Password: DB stores 'hashed_password', but user inputs plain 'password'.
    # SecretStr is used for security.
    password: SecretStr = Field(
        ...,
        min_length=8,
        max_length=100,
        description="User password (minimum 8 characters)",
    )

    # 4. Confirm Password: To verify the password was typed correctly (not saved to DB)
    confirm_password: SecretStr = Field(..., description="Password confirmation")

    # --- ADVANCED CONFIGURATION ---
    model_config = {
        "str_strip_whitespace": True,  # Trims leading and trailing whitespace from all strings
        "extra": "forbid",  # Rejects extra fields not defined in the schema (for security)
    }

    # --- ADVANCED VALIDATORS ---

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: SecretStr) -> SecretStr:
        """Validates that the password contains at least 1 uppercase letter and 1 digit."""
        raw_pwd = value.get_secret_value()
        if not any(char.isupper() for char in raw_pwd):
            raise ValueError(
                "Password must contain at least one uppercase letter (A-Z)!"
            )
        if not any(char.isdigit() for char in raw_pwd):
            raise ValueError("Password must contain at least one digit (0-9)!")
        return value

    @model_validator(mode="after")
    def verify_passwords_match(self) -> Self:
        """Verifies that the Password and Confirm Password fields are identical."""
        if self.password.get_secret_value() != self.confirm_password.get_secret_value():
            raise ValueError("Passwords do not match!")
        return self

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if not (3 <= len(v) <= 50):
            raise ValueError("Username must be 3-50 characters")
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username can only contain letters, digits, underscore")
        return v


class UserLoginSchema(BaseModel):
    email: EmailStr
    password: SecretStr


class TokenRefreshSchema(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True
