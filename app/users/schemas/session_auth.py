from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ---- Email verification ----

class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


# ---- Password reset ----

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


# ---- Session management ----

class SessionOut(BaseModel):
    id: UUID
    device_info: str | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionOut]


# ---- Umumy "generic" jogaplar ----

class MessageResponse(BaseModel):
    """
    forgot-password, resend-verification ýaly enumeration-a garşy
    endpoint-ler üçin - hemişe SHOL BIR jogap gaýtarylýar, user
    tapylan-tapylmadygyna garamazdan.
    """
    message: str